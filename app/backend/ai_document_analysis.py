"""Academic, chapter-aware AI-writing analysis for DoctorPlagio V2."""
from __future__ import annotations
import asyncio
import hashlib
import re
from collections import defaultdict
from typing import Any
from .local_llm import generate_json
from .ai_metrics import calculate_metrics, merge_metrics
from .ai_prompts import segment_prompt, document_prompt
from .memory_monitor import log_memory, collect_garbage
PAGE_RE = re.compile(r"\\[\\[PAGE:(\d+)\\]\\]")
def _pages(text: str) -> list[int]:

    return [int(x) for x in PAGE_RE.findall(text)]

def _strip_pages(text: str) -> str:

    return PAGE_RE.sub("", text).strip()
def _chapter_name(section: str, current: str) -> str:

    s = section.strip()

    if re.match(r"^(?:CAP[IÍ]TULO|CHAPTER)\s+(?:[IVXLCDM]+|\d+)\b", s, re.I):

        return s

    if re.match(r"^\d+[\.\)]\s+", s) and not re.match(r"^\d+\.\d+", s):

        return s

    return current

EXCLUDED_AI_SECTIONS = (
    "referencias bibliográficas",
    "referencias bibliografica",
    "bibliografía",
    "bibliografia",
    "references",
    "bibliography",
    "fuentes bibliográficas",
    "fuentes bibliograficas",
    "CAPITULO",
    "capitulo",
)

def _normalize_heading_name(name: str) -> str:
    """Normaliza un nombre de capítulo/sección para aplicar reglas académicas."""
    normalized = re.sub(r"\s+", " ", str(name or "").strip().lower())
    normalized = re.sub(
        r"^(?:capítulo|chapter)?\s*\d+(?:\.\d+)*[\.\)]?\s*",
        "",
        normalized,
        flags=re.I,
    ).strip()
    return normalized


def _is_ai_excluded_chapter(name: str) -> bool:
    """Excluye referencias/bibliografía del cálculo de características de IA."""
    normalized = _normalize_heading_name(name)
    return any(
        normalized == excluded or normalized.startswith(excluded + " ")
        for excluded in EXCLUDED_AI_SECTIONS
    )
def _confidence(results: list[dict], chars: int) -> str:

    scores = [float(x.get("ai_score", 0)) for x in results if x.get("available") and x.get("ai_score") is not None]

    if len(scores) < 2 or chars < 5000:

        return "bajo"

    spread = max(scores) - min(scores)

    if len(scores) >= 5 and spread < 0.25:

        return "alto"

    if len(scores) >= 3:

        return "medio"

    return "bajo"

def _analysis_text(chunk: dict) -> str:

    """Devuelve solo el contenido evaluable; excluye encabezados estructurales."""

    return _strip_pages(chunk.get("analysis_text", chunk.get("text", "")))

def _text_key(text: str) -> str:

    return hashlib.sha256(_strip_pages(text).encode("utf-8")).hexdigest()

def _candidate_priority(metrics: dict) -> float:

    cv = float(metrics.get("sentence_length_cv", 0.0))

    rep2 = float(metrics.get("repeated_bigram_rate", 0.0))

    rep3 = float(metrics.get("repeated_trigram_rate", 0.0))

    conn = float(metrics.get("connector_total", 0.0)) / max(float(metrics.get("sentences", 0)), 1.0)

    lex = float(metrics.get("lexical_diversity", 0.0))

    uniformity = max(0.0, 1.0 - min(cv, 1.0))

    return round(0.35 * uniformity + 0.25 * min(rep2 * 20, 1.0) +

                 0.20 * min(rep3 * 40, 1.0) + 0.10 * min(conn * 5, 1.0) +

                 0.10 * max(0.0, 1.0 - lex), 4)

def _select_llm_segments(prepared: list[dict], previous_keys: set[str] | None = None) -> set[int]:

    """Selecciona muestras de forma estratificada por capítulo y por tamaño."""

    if not prepared:

        return set()

    previous_keys = previous_keys or set()
    # Mantiene el consumo de GPT-OSS acotado, pero distribuye las inferencias    # entre capítulos. Cada capítulo recibe al menos una muestra cuando el    # presupuesto lo permite.
    chapters = defaultdict(list)

    for i, c in enumerate(prepared):

        chapters[c.get("chapter", "Documento")].append(i)

    budget = min(12, max(4, round(len(prepared) ** 0.5) + len(chapters)))

    ranked = []

    for i, c in enumerate(prepared):

        text = _analysis_text(c)

        key = _text_key(text)

        priority = _candidate_priority(calculate_metrics(text))

        if previous_keys and key not in previous_keys:

            priority += 0.75

        priority += min(len(text) / 9000.0, 1.0) * 0.15

        ranked.append((i, priority))



    rank_map = dict(ranked)

    selected = set()
    # Primero: al menos un bloque por capítulo.
    for indices in chapters.values():

        best = max(indices, key=lambda i: rank_map.get(i, 0.0))

        selected.add(best)

        if len(selected) >= budget:

            break
    # Después: bloques adicionales proporcionalmente a la disponibilidad.
    for i, _ in sorted(ranked, key=lambda x: x[1], reverse=True):

        if len(selected) >= budget:

            break

        selected.add(i)

    return selected

def _normalize_result(data: dict[str, Any], metrics: dict) -> dict:

    score = data.get("ai_score")

    try:

        score = max(0.0, min(1.0, float(score)))

    except (TypeError, ValueError):

        return {"available": False, "error": "ai_score inválido", "metrics": metrics}

    label = "bajo" if score < .30 else "intermedio" if score < .70 else "alto"

    return {

        "available": True,

        "ai_score": round(score, 4),

        "human_score": round(1-score, 4),

        "label": label,

        "syntactic_uniformity": float(data.get("syntactic_uniformity", 0)),

        "repetitive_patterns": float(data.get("repetitive_patterns", 0)),

        "vocabulary_uniformity": float(data.get("vocabulary_uniformity", 0)),

        "transition_regularity": float(data.get("transition_regularity", 0)),

        "semantic_redundancy": float(data.get("semantic_redundancy", 0)),

        "ai_signals": data.get("ai_signals", [])[:8] if isinstance(data.get("ai_signals", []), list) else [],

        "human_signals": data.get("human_signals", [])[:8] if isinstance(data.get("human_signals", []), list) else [],

        "reasoning": str(data.get("reasoning", ""))[:800],

        "evidence_sentences": data.get("evidence_sentences", [])[:5] if isinstance(data.get("evidence_sentences", []), list) else [],

        "metrics": metrics,

    }

async def analyze_segment(chunk: dict, number: int, total: int, call_llm: bool = True, cached: dict | None = None) -> dict:

    raw = chunk.get("text", "")

    text = _analysis_text(chunk)

    metrics = calculate_metrics(text)

    pages = _pages(raw)

    section = chunk.get("section", "Documento")

    chapter = chunk.get("chapter", "Documento")

    if cached is not None and cached.get("ai_score") is not None:

        reused = dict(cached)

        reused.update({

            "segment": number, "chapter": chapter, "section": section,

            "pages": pages, "characters": len(text), "text_preview": text[:350],

            "reused_from_previous": True, "metrics": metrics

        })

        return reused



    prompt = segment_prompt(text, section, chapter, metrics)

    print(f"🧠 IA: segmento {number}/{total} | capítulo: {chapter} | sección: {section} | caracteres: {len(text):,} | LLM={call_llm}")

    if not call_llm:

        return {

            "available": True, "segment": number, "chapter": chapter, "section": section,

            "pages": pages, "characters": len(text), "metrics": metrics,

            "ai_score": None, "human_score": None, "label": "no_evaluado",

            "reused_from_previous": False, "sampling": True,

            "reasoning": "Segmento no seleccionado para inferencia local; se conserva para cobertura.",

            "text_preview": text[:350], "evidence_sentences": []

        }

    try:

        data = await asyncio.to_thread(generate_json, prompt, 700, 0.0, 42)

        if not isinstance(data, dict) or "error" in data:

            return {

                "available": False, "segment": number, "chapter": chapter,

                "section": section, "pages": pages, "characters": len(text),

                "metrics": metrics, "reasoning": "El modelo no devolvió JSON válido."

            }

        result = _normalize_result(data, metrics)

        result.update({

            "segment": number, "chapter": chapter, "section": section,

            "pages": pages, "characters": len(text), "text_preview": text[:350]

        })

        return result

    except Exception as exc:

        return {

            "available": False, "segment": number, "chapter": chapter,

            "section": section, "pages": pages, "characters": len(text),

            "metrics": metrics, "reasoning": str(exc)

        }

def _aggregate_scores(items: list[dict]) -> tuple[float | None, int, int]:

    """Promedio ponderado por caracteres de los bloques realmente evaluados."""

    valid = [x for x in items if x.get("ai_score") is not None]

    evaluated_chars = sum(int(x.get("characters", 0)) for x in valid)

    total_chars = sum(int(x.get("characters", 0)) for x in items)

    if not valid or evaluated_chars <= 0:

        return None, evaluated_chars, total_chars

    score = sum(float(x["ai_score"]) * int(x.get("characters", 0)) for x in valid) / evaluated_chars

    return round(score, 4), evaluated_chars, total_chars

async def analyze_ai_document_v2(text: str, academic_chunks_func, previous_report: dict | None = None) -> dict:

    log_memory("inicio análisis IA")

    clean = text.strip()

    if not clean:

        return {

            "available": False, "ai_score": None, "human_score": None,

            "label": "No disponible", "reasoning": "El documento no contiene texto.",

            "chapters": [], "segments": []

        }

    chunks = academic_chunks_func(clean)
    log_memory(f"después de academic_chunks: {len(chunks)} bloques")
    current = "Documento"

    prepared = []

    for c in chunks:

        current = _chapter_name(c.get("section", "Documento"), current)

        item = dict(c)

        item["chapter"] = current

        prepared.append(item)

    cache = {}
    if isinstance(previous_report, dict):

        for old in previous_report.get("segments", []):

            if old.get("text_key") and old.get("ai_score") is not None:

                cache[old["text_key"]] = old



    selected = _select_llm_segments(prepared, set(cache.keys()))

    segments = []

    for i, chunk in enumerate(prepared):

        key = _text_key(_analysis_text(chunk))

        cached = cache.get(key)
    # Un bloque sin cambios se puede reutilizar. Un bloque nuevo debe ser    # evaluado si fue seleccionado por el muestreo estratificado.
        result = await analyze_segment(

            chunk, i + 1, len(prepared),

            call_llm=(i in selected),

            cached=cached

        )

        result["text_key"] = key

        result["heading_excluded_from_analysis"] = bool(chunk.get("analysis_text") is not None and chunk.get("analysis_text") != chunk.get("text"))

        result["heading_excluded_characters"] = max(0, len(_strip_pages(chunk.get("text", ""))) - len(_analysis_text(chunk)))

        result["llm_sampled"] = i in selected

        if i in selected:

            collect_garbage(f"segmento IA {i+1}")

        segments.append(result)



    grouped = defaultdict(list)

    for s in segments:

        grouped[s.get("chapter", "Documento")].append(s)



    chapters = []

    for name, segs in grouped.items():

        score, evaluated_chars, total_chars = _aggregate_scores(segs)

        valid = [s for s in segs if s.get("ai_score") is not None]

        metrics = merge_metrics([s.get("metrics", {}) for s in segs])

        pages = sorted({p for s in segs for p in s.get("pages", [])})



        if score is None:

            reasoning = "No hay inferencias IA suficientes para calcular un porcentaje de este capítulo."

        else:

            reasoning = (

                "Resultado del capítulo calculado como promedio ponderado por caracteres "

                "de los bloques evaluados o reutilizados."

            )



        excluded_from_ai = _is_ai_excluded_chapter(name)
        chapter_score = None if excluded_from_ai else score
        chapter_evaluated_chars = 0 if excluded_from_ai else evaluated_chars
        chapter_coverage = 0.0 if excluded_from_ai else (
            round(evaluated_chars / total_chars, 4) if total_chars else 0.0
        )

        if excluded_from_ai:
            reasoning = (
                "Sección excluida del cálculo de características de IA por tratarse "
                "de contenido bibliográfico/estructural no evaluable."
            )

        chapters.append({
            "chapter": name,
            "pages": pages,
            "characters": total_chars,
            "evaluated_characters": chapter_evaluated_chars,
            "coverage": chapter_coverage,
            "ai_score": chapter_score,
            "human_score": round(1 - chapter_score, 4) if chapter_score is not None else None,
            "confidence": "no evaluado" if excluded_from_ai else _confidence(valid, evaluated_chars),
            "excluded_from_ai": excluded_from_ai,
            "exclusion_reason": (
                "Referencias bibliográficas excluidas del cálculo de IA."
                if excluded_from_ai else None
            ),
            "main_patterns": [] if excluded_from_ai else [x for s in valid for x in s.get("ai_signals", [])][:8],
            "ai_signals": [] if excluded_from_ai else [x for s in valid for x in s.get("ai_signals", [])][:8],
            "human_signals": [] if excluded_from_ai else [x for s in valid for x in s.get("human_signals", [])][:8],
            "page_evidence": pages,
            "reasoning": reasoning,
            "metrics": {} if excluded_from_ai else metrics,
            "segments": segs
        })
    # Documento: SOLO se agregan capítulos con score real. El peso es el    # contenido efectivamente evaluado, no un único bloque seleccionado.
    valid_chapters = [
        c for c in chapters
        if c.get("ai_score") is not None
        and not c.get("excluded_from_ai", False)
    ]
    evaluated_total = sum(c["evaluated_characters"] for c in valid_chapters)
    document_total = sum(c["characters"] for c in valid_chapters)
    excluded_total = sum(
        int(c.get("characters", 0))
        for c in chapters
        if c.get("excluded_from_ai", False)
    )
    if evaluated_total:

        global_score = sum(c["ai_score"] * c["evaluated_characters"] for c in valid_chapters) / evaluated_total

        global_score = round(global_score, 4)

    else:

        global_score = None

    global_metrics = merge_metrics([c.get("metrics", {}) for c in chapters])

    chapter_summaries = [{

        "chapter": c["chapter"],

        "pages": c["pages"],

        "characters": c["characters"],

        "evaluated_characters": c["evaluated_characters"],

        "coverage": c["coverage"],

        "ai_score": c["ai_score"],

        "human_score": c["human_score"],

        "confidence": c["confidence"]

    } for c in chapters]



    try:

        cross = await asyncio.to_thread(

            generate_json,

            document_prompt(chapter_summaries, global_metrics),

            1100, 0.0, 42

        )

    except Exception:

        cross = {}

    if not isinstance(cross, dict) or "error" in cross:

        cross = {}



    coverage = evaluated_total / document_total if document_total else 0.0

    llm_results = [s for s in segments if s.get("ai_score") is not None]

    if global_score is None:

        label = "No disponible"

        human_score = None

    else:

        label = "bajo" if global_score < .30 else "intermedio" if global_score < .70 else "alto"

        human_score = round(1 - global_score, 4)



    limitations = cross.get("limitations", [])

    if not isinstance(limitations, list):

        limitations = []

    if coverage < 0.70:

        limitations.append(

            "La estimación global tiene cobertura parcial: no todo el contenido recibió inferencia directa de GPT-OSS."

        )

    limitations.extend([

        "La detección de características lingüísticas no demuestra autoría.",

        "Los porcentajes por capítulo y bloque pueden variar según la evidencia lingüística disponible."

    ])
    # Quitar duplicados conservando orden.
    limitations = list(dict.fromkeys(str(x) for x in limitations))

    return {

        "available": bool(segments),

        "ai_score": global_score,

        "human_score": human_score,

        "label": label,

        "confidence": cross.get("confidence", _confidence(llm_results, evaluated_total)),

        "reasoning": (

            cross.get("reasoning")

            or "Estimación global calculada a partir de capítulos y bloques evaluados, ponderada por cantidad de contenido."

        ),

        "characterization": cross.get("characterization", "indeterminado"),

        "recurring_patterns": cross.get("recurring_patterns", []),

        "strongest_pages": cross.get("strongest_pages", []),

        "human_evidence": cross.get("human_evidence", []),

        "limitations": limitations,

        "segments_analyzed": len(segments),

        "segments_successful": len(llm_results),

        "segments_reused": sum(1 for s in segments if s.get("reused_from_previous")),

        "segments_llm_sampled": sum(1 for s in segments if s.get("llm_sampled")),

        "chapters_analyzed": len(chapters),

        "evaluated_characters": evaluated_total,

        "document_characters": document_total,

        "structural_heading_policy": "Los encabezados de capítulos y subcapítulos se conservan como metadata, pero se excluyen del cálculo de métricas y del ai_score.",

        "excluded_heading_characters": sum(int(s.get("heading_excluded_characters", 0)) for s in segments),

        "coverage": round(coverage, 4),

        "chapters": chapters,

        "segments": segments,

        "global_metrics": global_metrics,

        "methodology": (

            "Métricas lingüísticas determinísticas sobre contenido evaluable, excluyendo encabezados estructurales y secciones bibliográficas "

            "+ muestreo estratificado de GPT-OSS + reutilización exacta de segmentos sin cambios + agregación jerárquica "

            "bloque → capítulo → documento, ponderada por caracteres evaluados."

        ),

    }
