import json
import re
from pathlib import Path
import sys
import httpx

path_actual = Path(__file__).resolve()
raiz_proyecto = path_actual.parents[2]
if str(raiz_proyecto) not in sys.path:
    sys.path.insert(0, str(raiz_proyecto))

from backend.config import OLLAMA_BASE_URL, OLLAMA_MODEL
from backend.vector_store import get_chroma_client, get_collection
from backend.similarity_engine import (
    get_model,
    sentence_chunks,
    analyze_fragment_against_candidate,
    SEMANTIC_CANDIDATE_MIN,
    TOP_K,
)


def _clean_for_embedding(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


async def get_embeddings(text: str):
    """Generate a normalized local embedding with Sentence Transformers."""
    clean_text = _clean_for_embedding(text)
    if not clean_text:
        return None
    model = get_model()
    vector = model.encode(
        [clean_text],
        normalize_embeddings=True,
        convert_to_numpy=True,
        show_progress_bar=False,
    )[0]
    return vector.astype("float32").tolist()


async def detect_ai_text(text: str):
    """Existing AI-analysis feature. Kept separate from plagiarism evidence."""
    ollama_url = f"{OLLAMA_BASE_URL}/api/generate"
    truncated_text = text[:1500]
    prompt = f"""
[SISTEMA: ANALISTA DE LINGÜÍSTICA FORENSE ACADÉMICA]
Analiza el siguiente fragmento de una tesis universitaria. Tu objetivo es diferenciar entre redacción formal humana y generación sintética.

REGLAS DE RESPUESTA:
- ai_score: 0.0 a 1.0.
- RESPONDE ÚNICAMENTE EN JSON.
{{
  "ai_score": float,
  "label": "string",
  "reasoning": "string"
}}

TEXTO:
{truncated_text}
"""
    fallback_response = {
        "ai_score": 0.0,
        "human_score": 1.0,
        "label": "Human-written",
        "reasoning": "No fue posible completar el análisis de IA.",
    }
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                ollama_url,
                json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False, "format": "json"},
            )
        if response.status_code != 200:
            return fallback_response
        raw_result = response.json()
        ai_data = json.loads(raw_result.get("response", "{}"))
        score = max(0.0, min(1.0, float(ai_data.get("ai_score", 0.0))))
        return {
            "ai_score": round(score, 4),
            "human_score": round(1.0 - score, 4),
            "label": "AI-generated" if score > 0.5 else "Human-written",
            "reasoning": ai_data.get("reasoning", "Análisis completado"),
        }
    except Exception as exc:
        print(f"⚠️ Error en detección de IA: {exc}")
        return fallback_response


async def analyze_plagiarism(document_content: str, db_session=None):
    """Analyze a document against the V1.1 Chroma collection.

    The returned plagiarism percentage is an evidence-coverage metric: the
    percentage of input chunks with at least one strong textual/semantic match.
    It is NOT a probability that the document contains plagiarism.
    """
    text = _clean_for_embedding(document_content)
    fragments = sentence_chunks(text)
    if not fragments:
        return {"plagiarism_percentage": 0.0, "details": [], "ai_analysis": {}}

    collection = get_collection()
    model = get_model()
    details = []
    flagged_fragments = 0

    for fragment in fragments:
        embedding = model.encode(
            [fragment], normalize_embeddings=True, convert_to_numpy=True, show_progress_bar=False
        )[0].astype("float32").tolist()
        results = collection.query(
            query_embeddings=[embedding],
            n_results=min(TOP_K, max(1, collection.count())),
            include=["documents", "metadatas", "distances"],
        )
        docs = (results.get("documents") or [[]])[0]
        metas = (results.get("metadatas") or [[]])[0]
        distances = (results.get("distances") or [[]])[0]
        best_for_fragment = None

        for candidate, metadata, distance in zip(docs, metas, distances):
            # Cosine distance in the V1.1 collection = 1 - cosine similarity.
            semantic = max(0.0, min(1.0, 1.0 - float(distance)))
            if semantic < SEMANTIC_CANDIDATE_MIN:
                continue
            evidence = analyze_fragment_against_candidate(fragment, candidate, semantic)
            evidence["source"] = (metadata or {}).get("source", "Desconocido")
            evidence["fragment"] = fragment[:500]
            evidence["matched_fragment"] = candidate[:500]
            if best_for_fragment is None or evidence["evidence_score"] > best_for_fragment["evidence_score"]:
                best_for_fragment = evidence

        if best_for_fragment:
            # Only strong textual evidence contributes to coverage.
            if best_for_fragment["classification"] in {"probable_copy", "probable_paraphrase", "textual_overlap"} and best_for_fragment["evidence_score"] >= 0.50:
                flagged_fragments += 1
                details.append(best_for_fragment)

    coverage = (flagged_fragments / len(fragments)) * 100.0
    try:
        ai_report = await detect_ai_text(text[:2000])
    except Exception:
        ai_report = {}

    return {
        "plagiarism_percentage": round(min(100.0, coverage), 2),
        "details": details,
        "ai_analysis": ai_report,
        "analysis_meta": {
            "chunks_analyzed": len(fragments),
            "chunks_with_strong_evidence": flagged_fragments,
            "metric": "cosine distance on normalized embeddings",
            "model": "paraphrase-multilingual-mpnet-base-v2",
            "interpretation": "evidence coverage, not probability of plagiarism",
        },
    }
