"""Academic, chapter-aware AI-writing analysis for DoctorPlagio V2."""
from __future__ import annotations
import asyncio
import hashlib
import json
import re
from collections import defaultdict
from typing import Any

from .local_llm import generate_json
from .ai_metrics import calculate_metrics, merge_metrics
from .ai_prompts import segment_prompt, chapter_prompt, document_prompt
from .memory_monitor import log_memory, collect_garbage

PAGE_RE = re.compile(r"\[\[PAGE:(\d+)\]\]")

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

def _confidence(results: list[dict], chars: int) -> str:
    if len(results) < 2 or chars < 5000:
        return "bajo"
    scores = [float(x.get("ai_score", 0)) for x in results if x.get("available")]
    if not scores:
        return "bajo"
    spread = max(scores) - min(scores)
    if len(results) >= 5 and spread < 0.25:
        return "alto"
    if len(results) >= 3:
        return "medio"
    return "bajo"

def _text_key(text: str) -> str:
    return hashlib.sha256(_strip_pages(text).encode("utf-8")).hexdigest()


def _candidate_priority(metrics: dict) -> float:
    """Cheap triage score; used only to choose LLM samples, never as AI proof."""
    cv = float(metrics.get("sentence_length_cv", 0.0))
    rep2 = float(metrics.get("repeated_bigram_rate", 0.0))
    rep3 = float(metrics.get("repeated_trigram_rate", 0.0))
    conn = float(metrics.get("connector_total", 0.0)) / max(float(metrics.get("sentences", 0)), 1.0)
    lex = float(metrics.get("lexical_diversity", 0.0))
    # These are weak linguistic signals only. They decide sampling, not classification.
    uniformity = max(0.0, 1.0 - min(cv, 1.0))
    return round(0.35 * uniformity + 0.25 * min(rep2 * 20, 1.0) +
                 0.20 * min(rep3 * 40, 1.0) + 0.10 * min(conn * 5, 1.0) +
                 0.10 * max(0.0, 1.0 - lex), 4)


def _select_llm_segments(prepared: list[dict], previous_keys: set[str] | None = None) -> set[int]:
    """Select bounded representative segments, prioritizing changed content."""
    if not prepared:
        return set()
    previous_keys = previous_keys or set()
    max_calls = min(8, max(2, round(len(prepared) ** 0.5) + 1))
    ranked = []
    for i, c in enumerate(prepared):
        text = _strip_pages(c.get("text", ""))
        key = _text_key(c.get("text", ""))
        priority = _candidate_priority(calculate_metrics(text))
        if previous_keys and key not in previous_keys:
            priority += 0.75  # changed/new content gets priority
        ranked.append((i, priority))
    ranked.sort(key=lambda x: x[1], reverse=True)

    selected: set[int] = set()
    # Guarantee at least one representative segment per chapter while budget allows.
    chapters = defaultdict(list)
    for i, c in enumerate(prepared):
        chapters[c.get("chapter", "Documento")].append(i)
    for indices in chapters.values():
        best = max(indices, key=lambda i: dict(ranked).get(i, 0.0))
        selected.add(best)
        if len(selected) >= max_calls:
            break
    for i, _ in ranked:
        if len(selected) >= max_calls:
            break
        selected.add(i)
    return selected

def _normalize_result(data: dict[str, Any], metrics: dict) -> dict:
    score = data.get("ai_score")
    try:
        score = max(0.0, min(1.0, float(score)))
    except (TypeError, ValueError):
        return {"available": False, "error": "ai_score inválido", "metrics": metrics}
    label = "bajo" if score < .40 else "intermedio" if score < .70 else "alto"
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
    text = _strip_pages(raw)
    metrics = calculate_metrics(text)
    pages = _pages(raw)
    section = chunk.get("section", "Documento")
    chapter = chunk.get("chapter", "Documento")
    if cached is not None:
        reused = dict(cached)
        reused.update({"segment": number, "chapter": chapter, "section": section, "pages": pages, "characters": len(text), "text_preview": text[:350], "reused_from_previous": True, "metrics": metrics})
        return reused
    prompt = segment_prompt(text, section, chapter, metrics)
    print(f"🧠 IA: segmento {number}/{total} | capítulo: {chapter} | sección: {section} | caracteres: {len(text):,} | LLM={call_llm}")
    if not call_llm:
        return {"available": True, "segment": number, "chapter": chapter, "section": section, "pages": pages, "characters": len(text), "metrics": metrics, "ai_score": None, "human_score": None, "label": "no_evaluado", "reused_from_previous": False, "sampling": True, "reasoning": "Segmento no seleccionado para inferencia local; se conserva para cobertura y análisis global.", "text_preview": text[:350], "evidence_sentences": []}
    try:
        data = await asyncio.to_thread(generate_json, prompt, 700, 0.0, 42)
        if not isinstance(data, dict) or "error" in data:
            return {"available": False, "segment": number, "chapter": chapter, "section": section, "pages": pages, "characters": len(text), "metrics": metrics, "reasoning": "El modelo no devolvió JSON válido."}
        result = _normalize_result(data, metrics)
        result.update({"segment": number, "chapter": chapter, "section": section, "pages": pages, "characters": len(text), "text_preview": text[:350]})
        return result
    except Exception as exc:
        return {"available": False, "segment": number, "chapter": chapter, "section": section, "pages": pages, "characters": len(text), "metrics": metrics, "reasoning": str(exc)}

async def _chapter_analysis(chapter: str, segments: list[dict]) -> dict:
    valid = [s for s in segments if s.get("available")]
    chars = sum(s.get("characters", 0) for s in valid)
    metrics = merge_metrics([s.get("metrics", {}) for s in valid])
    pages = sorted({p for s in segments for p in s.get("pages", [])})
    pages_text = f"{pages[0]}–{pages[-1]}" if pages else "No disponible"
    summaries = [{
        "segment": s.get("segment"), "section": s.get("section"), "pages": s.get("pages"),
        "characters": s.get("characters"), "ai_score": s.get("ai_score"),
        "label": s.get("label"), "ai_signals": s.get("ai_signals", []),
        "human_signals": s.get("human_signals", []), "reasoning": s.get("reasoning", "")
    } for s in valid]
    try:
        data = await asyncio.to_thread(generate_json, chapter_prompt(chapter, pages_text, metrics, summaries), 1600, 0.0, 42)
        if isinstance(data, dict) and "error" not in data:
            score = max(0.0, min(1.0, float(data.get("ai_score", 0))))
            return {"chapter": chapter, "pages": pages, "characters": chars, "ai_score": round(score,4), "human_score": round(1-score,4), "confidence": data.get("confidence", _confidence(valid, chars)), "main_patterns": data.get("main_patterns", []), "ai_signals": data.get("ai_signals", []), "human_signals": data.get("human_signals", []), "page_evidence": data.get("page_evidence", []), "reasoning": data.get("reasoning", ""), "metrics": metrics, "segments": segments}
    except Exception as exc:
        pass
    score = sum(s["ai_score"]*s["characters"] for s in valid)/chars if chars else 0.0
    return {"chapter": chapter, "pages": pages, "characters": chars, "ai_score": round(score,4), "human_score": round(1-score,4), "confidence": _confidence(valid, chars), "main_patterns": [], "ai_signals": [], "human_signals": [], "page_evidence": pages, "reasoning": "Resultado agregado de los segmentos; análisis narrativo de capítulo no disponible.", "metrics": metrics, "segments": segments}

async def analyze_ai_document_v2(text: str, academic_chunks_func, previous_report: dict | None = None) -> dict:
    log_memory("inicio análisis IA")
    clean = text.strip()
    if not clean:
        return {"available": False, "ai_score": None, "human_score": None, "label": "No disponible", "reasoning": "El documento no contiene texto.", "chapters": [], "segments": []}

    chunks = academic_chunks_func(clean)
    log_memory(f"después de academic_chunks: {len(chunks)} bloques")
    current = "Documento"
    prepared = []
    for c in chunks:
        current = _chapter_name(c.get("section", "Documento"), current)
        item = dict(c)
        item["chapter"] = current
        prepared.append(item)

    # Reuse segment analyses whose normalized text is unchanged. This is the
    # main optimization for revised documents.
    cache = {}
    if isinstance(previous_report, dict):
        for old in previous_report.get("segments", []):
            preview = old.get("text_preview", "")
            # text_preview is not enough for identity; use a stable key when present.
            if old.get("text_key"):
                cache[old["text_key"]] = old

    selected = _select_llm_segments(prepared, set(cache.keys()))
    segments = []
    for i, chunk in enumerate(prepared):
        key = _text_key(chunk.get("text", ""))
        cached = cache.get(key)
        result = await analyze_segment(chunk, i + 1, len(prepared), call_llm=(i in selected), cached=cached)
        result["text_key"] = key
        if i in selected:
            collect_garbage(f"segmento IA {i+1}")
        result["llm_sampled"] = i in selected
        segments.append(result)

    # If there is no previous report and the document is short, analyze every
    # segment. For long documents, bounded sampling prevents dozens of 20B calls.
    llm_results = [s for s in segments if s.get("available") and s.get("ai_score") is not None]
    grouped = defaultdict(list)
    for s in segments:
        grouped[s.get("chapter", "Documento")].append(s)
    chapters = []
    for name, segs in grouped.items():
        valid = [s for s in segs if s.get("ai_score") is not None]
        chars = sum(s.get("characters", 0) for s in valid)
        if valid:
            metrics = merge_metrics([s.get("metrics", {}) for s in valid])
            score = sum(float(s.get("ai_score", 0)) * s.get("characters", 0) for s in valid) / max(chars, 1)
        else:
            metrics = merge_metrics([s.get("metrics", {}) for s in segs])
            score = 0.0
        pages = sorted({p for s in segs for p in s.get("pages", [])})
        chapters.append({
            "chapter": name, "pages": pages, "characters": sum(s.get("characters", 0) for s in segs),
            "ai_score": round(score, 4) if valid else None,
            "human_score": round(1-score, 4) if valid else None,
            "confidence": _confidence(valid, chars),
            "main_patterns": [x for s in valid for x in s.get("ai_signals", [])][:8],
            "ai_signals": [x for s in valid for x in s.get("ai_signals", [])][:8],
            "human_signals": [x for s in valid for x in s.get("human_signals", [])][:8],
            "page_evidence": pages,
            "reasoning": "Agregado ponderado de segmentos evaluados; se redujeron inferencias para controlar consumo de recursos.",
            "metrics": metrics, "segments": segs
        })

    collect_garbage("fin inferencias de segmentos")
    valid_chapters = [c for c in chapters if c.get("ai_score") is not None]
    total_chars = sum(c["characters"] for c in valid_chapters)
    global_score = sum(c["ai_score"] * c["characters"] for c in valid_chapters) / max(total_chars, 1) if valid_chapters else 0.0
    global_metrics = merge_metrics([c.get("metrics", {}) for c in chapters])
    chapter_summaries = [{k: c.get(k) for k in ["chapter", "pages", "characters", "ai_score", "human_score", "confidence", "main_patterns", "ai_signals", "human_signals", "page_evidence", "reasoning"]} for c in valid_chapters]
    try:
        cross = await asyncio.to_thread(generate_json, document_prompt(chapter_summaries, global_metrics), 1100, 0.0, 42)
    except Exception:
        cross = {}
    if not isinstance(cross, dict) or "error" in cross:
        cross = {}

    log_memory("fin análisis IA")
    return {
        "available": bool(segments), "ai_score": round(global_score, 4), "human_score": round(1-global_score, 4),
        "label": "bajo" if global_score < .40 else "intermedio" if global_score < .70 else "alto",
        "confidence": cross.get("confidence", _confidence(llm_results, total_chars)),
        "reasoning": cross.get("reasoning", "Estimación ponderada por los segmentos seleccionados y reutilizados."),
        "characterization": cross.get("characterization", "indeterminado"),
        "recurring_patterns": cross.get("recurring_patterns", []), "strongest_pages": cross.get("strongest_pages", []),
        "human_evidence": cross.get("human_evidence", []),
        "limitations": cross.get("limitations", ["La detección de características lingüísticas no demuestra autoría.", "Los segmentos no seleccionados no recibieron una nueva inferencia del modelo local."]),
        "segments_analyzed": len(segments), "segments_successful": len(llm_results), "segments_reused": sum(1 for s in segments if s.get("reused_from_previous")),
        "segments_llm_sampled": sum(1 for s in segments if s.get("llm_sampled")), "chapters_analyzed": len(chapters),
        "chapters": chapters, "segments": segments, "global_metrics": global_metrics,
        "methodology": "Métricas lingüísticas determinísticas + muestreo adaptativo de GPT-OSS + reutilización exacta de segmentos sin cambios + agregación ponderada.",
    }

