"""Deterministic linguistic metrics for DoctorPlagio AI Analysis V2."""
from __future__ import annotations
import math
import re
from collections import Counter
from statistics import mean, pstdev

CONNECTORS = [
    "por ello", "en consecuencia", "de este modo", "esta distinción",
    "no se trata de", "no basta con", "la lógica", "el presente capítulo",
    "el alcance comprende", "este capítulo tiene por propósito",
    "en este contexto", "asimismo", "finalmente", "por tanto",
    "en términos prácticos", "de igual modo", "en cuanto a", "por otra parte",
]

TOKEN_RE = re.compile(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ0-9]+(?:[-'][A-Za-zÁÉÍÓÚÜÑáéíóúüñ0-9]+)*", re.UNICODE)
SENTENCE_RE = re.compile(r"(?<=[.!?])\s+(?=[A-ZÁÉÍÓÚÜÑ0-9¿¡\"'])", re.UNICODE)


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in SENTENCE_RE.split(text.strip()) if s.strip()]


def _tokens(text: str) -> list[str]:
    return [t.lower() for t in TOKEN_RE.findall(text)]


def _safe_cv(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    m = mean(values)
    return pstdev(values) / m if m else 0.0


def _repetition_rate(tokens: list[str], n: int = 2) -> float:
    if len(tokens) < n:
        return 0.0
    grams = [tuple(tokens[i:i+n]) for i in range(len(tokens)-n+1)]
    counts = Counter(grams)
    repeated = sum(c - 1 for c in counts.values() if c > 1)
    return repeated / len(grams) if grams else 0.0


def calculate_metrics(text: str) -> dict:
    sentences = _sentences(text)
    tokens = _tokens(text)
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    sentence_lengths = [len(_tokens(s)) for s in sentences]
    paragraph_lengths = [len(_tokens(p)) for p in paragraphs]
    lower = text.lower()

    connector_counts = {
        phrase: len(re.findall(r"(?<!\w)" + re.escape(phrase) + r"(?!\w)", lower))
        for phrase in CONNECTORS
    }
    connector_counts = {k: v for k, v in connector_counts.items() if v}

    counts = Counter(tokens)
    repeated_words = {w: c for w, c in counts.items() if c >= 4}
    repeated_words = dict(sorted(repeated_words.items(), key=lambda x: (-x[1], x[0]))[:20])

    lexical_diversity = len(set(tokens)) / len(tokens) if tokens else 0.0
    avg_sentence = mean(sentence_lengths) if sentence_lengths else 0.0
    avg_paragraph = mean(paragraph_lengths) if paragraph_lengths else 0.0

    return {
        "characters": len(text),
        "words": len(tokens),
        "sentences": len(sentences),
        "paragraphs": len(paragraphs),
        "sentence_length_mean_words": round(avg_sentence, 2),
        "sentence_length_std_words": round(pstdev(sentence_lengths), 2) if len(sentence_lengths) > 1 else 0.0,
        "sentence_length_cv": round(_safe_cv(sentence_lengths), 4),
        "paragraph_length_mean_words": round(avg_paragraph, 2),
        "lexical_diversity": round(lexical_diversity, 4),
        "repeated_bigram_rate": round(_repetition_rate(tokens, 2), 4),
        "repeated_trigram_rate": round(_repetition_rate(tokens, 3), 4),
        "connector_counts": connector_counts,
        "connector_total": sum(connector_counts.values()),
        "repeated_words": repeated_words,
    }


def merge_metrics(metrics_list: list[dict]) -> dict:
    if not metrics_list:
        return calculate_metrics("")
    keys = [
        "characters", "words", "sentences", "paragraphs", "connector_total"
    ]
    out = {k: sum(float(m.get(k, 0)) for m in metrics_list) for k in keys}
    total_words = max(out["words"], 1.0)
    out["sentence_length_mean_words"] = round(
        sum(m.get("sentence_length_mean_words", 0) * m.get("sentences", 0) for m in metrics_list)
        / max(out["sentences"], 1.0), 2)
    out["sentence_length_std_words"] = round(mean(m.get("sentence_length_std_words", 0) for m in metrics_list), 2)
    out["sentence_length_cv"] = round(mean(m.get("sentence_length_cv", 0) for m in metrics_list), 4)
    out["paragraph_length_mean_words"] = round(
        sum(m.get("paragraph_length_mean_words", 0) * m.get("paragraphs", 0) for m in metrics_list)
        / max(out["paragraphs"], 1.0), 2)
    out["lexical_diversity"] = round(mean(m.get("lexical_diversity", 0) for m in metrics_list), 4)
    out["repeated_bigram_rate"] = round(mean(m.get("repeated_bigram_rate", 0) for m in metrics_list), 4)
    out["repeated_trigram_rate"] = round(mean(m.get("repeated_trigram_rate", 0) for m in metrics_list), 4)
    connectors = Counter()
    repeated_words = Counter()
    for m in metrics_list:
        connectors.update(m.get("connector_counts", {}))
        repeated_words.update(m.get("repeated_words", {}))
    out["connector_counts"] = dict(connectors.most_common(30))
    out["repeated_words"] = dict(repeated_words.most_common(30))
    for k in keys:
        if isinstance(out[k], float) and out[k].is_integer():
            out[k] = int(out[k])
    return out
