"""Hybrid evidence engine for DoctorPlagio V1.1.

This version deliberately avoids calling semantic similarity a plagiarism probability.
It combines semantic retrieval with lexical overlap and exact/near-exact evidence.
Thresholds are conservative defaults and should be calibrated with the project's test set.
"""
from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Any

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from sentence_transformers import SentenceTransformer

MODEL_NAME = "paraphrase-multilingual-mpnet-base-v2"
TOP_K = 5
SEMANTIC_CANDIDATE_MIN = 0.55
EXACT_COPY_THRESHOLD = 0.80
LEXICAL_HIGH_THRESHOLD = 0.55
SEMANTIC_HIGH_THRESHOLD = 0.82

_model: SentenceTransformer | None = None


def get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        _model = SentenceTransformer(MODEL_NAME)
    return _model


def normalize_text(text: str) -> str:
    text = text.replace("\u00ad", "")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def sentence_chunks(text: str, target_chars: int = 900, overlap_sentences: int = 1) -> list[str]:
    """Build chunks on sentence boundaries with a small sentence overlap."""
    text = normalize_text(text)
    if not text:
        return []
    sentences = re.split(r"(?<=[.!?])\s+", text)
    sentences = [s.strip() for s in sentences if s.strip()]
    if not sentences:
        return [text]

    chunks: list[str] = []
    current: list[str] = []
    current_len = 0
    for sentence in sentences:
        if current and current_len + len(sentence) + 1 > target_chars:
            chunks.append(" ".join(current))
            keep = current[-overlap_sentences:] if overlap_sentences else []
            current = keep + [sentence]
            current_len = sum(len(x) for x in current) + max(0, len(current)-1)
        else:
            current.append(sentence)
            current_len += len(sentence) + (1 if current_len else 0)
    if current:
        chunks.append(" ".join(current))
    return chunks


def token_set(text: str) -> set[str]:
    return set(re.findall(r"\b\w+\b", normalize_text(text).lower(), flags=re.UNICODE))


def shingle_set(text: str, n: int = 5) -> set[tuple[str, ...]]:
    tokens = re.findall(r"\b\w+\b", normalize_text(text).lower(), flags=re.UNICODE)
    return {tuple(tokens[i:i+n]) for i in range(max(0, len(tokens)-n+1))}


def exact_overlap_score(a: str, b: str) -> float:
    """Combines sequence similarity and token-shingle overlap."""
    seq = SequenceMatcher(None, normalize_text(a).lower(), normalize_text(b).lower()).ratio()
    sa, sb = shingle_set(a), shingle_set(b)
    if not sa or not sb:
        return seq
    jaccard = len(sa & sb) / len(sa | sb)
    return max(seq, jaccard)


def lexical_score(a: str, b: str) -> float:
    a, b = normalize_text(a), normalize_text(b)
    if not a or not b:
        return 0.0
    try:
        matrix = TfidfVectorizer(ngram_range=(1, 2), min_df=1).fit_transform([a, b])
        return float(cosine_similarity(matrix[0:1], matrix[1:2])[0, 0])
    except ValueError:
        return 0.0


def classify_match(exact: float, lexical: float, semantic: float) -> str:
    if exact >= EXACT_COPY_THRESHOLD:
        return "probable_copy"
    if lexical >= LEXICAL_HIGH_THRESHOLD and semantic >= 0.70:
        return "probable_paraphrase"
    if semantic >= SEMANTIC_HIGH_THRESHOLD and lexical < 0.45 and exact < 0.55:
        return "same_topic"
    if lexical >= 0.40 or exact >= 0.45:
        return "textual_overlap"
    return "weak_match"


def combined_evidence_score(exact: float, lexical: float, semantic: float, label: str) -> float:
    """Evidence score, not a calibrated probability of plagiarism."""
    # Exact textual evidence is intentionally dominant. Semantic similarity alone
    # cannot push a result into the high-evidence range.
    score = 0.45 * exact + 0.35 * lexical + 0.20 * semantic
    if label == "same_topic" and exact < 0.55 and lexical < 0.45:
        score *= 0.60
    return float(max(0.0, min(1.0, score)))


def analyze_fragment_against_candidate(fragment: str, candidate: str, semantic: float) -> dict[str, Any]:
    exact = exact_overlap_score(fragment, candidate)
    lexical = lexical_score(fragment, candidate)
    label = classify_match(exact, lexical, semantic)
    evidence = combined_evidence_score(exact, lexical, semantic, label)
    return {
        "semantic_similarity": round(float(semantic), 4),
        "exact_overlap": round(float(exact), 4),
        "lexical_similarity": round(float(lexical), 4),
        "evidence_score": round(evidence, 4),
        "classification": label,
    }
