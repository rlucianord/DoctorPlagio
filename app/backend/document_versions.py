"""Document version tracking for DoctorPlagio.

Uses deterministic fingerprints plus sentence-level comparison to detect
re-uploads of the same document and preserve the last evaluation.
"""
from __future__ import annotations

import hashlib
import json
import re
from difflib import SequenceMatcher
from typing import Any

PAGE_MARKER_RE = re.compile(r"\[\[PAGE:\d+\]\]")
SPACE_RE = re.compile(r"\s+")

# High enough to identify a likely revision of the same academic document,
# but not used to skip analysis. Exact/text fingerprints are used for that.
SAME_DOCUMENT_SIMILARITY = 0.92


def normalize_document_text(text: str) -> str:
    """Normalize text for content identity; preserve words but ignore layout."""
    text = PAGE_MARKER_RE.sub("\n", text or "")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = []
    for line in text.split("\n"):
        line = SPACE_RE.sub(" ", line).strip()
        if line:
            lines.append(line)
    return "\n".join(lines).strip()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def fingerprint(text: str, raw_bytes: bytes | None = None) -> dict[str, Any]:
    normalized = normalize_document_text(text)
    return {
        "file_hash": sha256_bytes(raw_bytes) if raw_bytes is not None else None,
        "text_hash": sha256_text(normalized),
        "normalized_chars": len(normalized),
        "normalized_text": normalized,
    }


def document_similarity(a: str, b: str) -> float:
    a_norm = normalize_document_text(a)
    b_norm = normalize_document_text(b)
    if not a_norm or not b_norm:
        return 0.0
    return round(SequenceMatcher(None, a_norm, b_norm).ratio(), 6)


def split_sentences(text: str) -> list[str]:
    clean = normalize_document_text(text)
    if not clean:
        return []
    parts = re.split(r"(?<=[.!?])\s+|\n+", clean)
    return [p.strip() for p in parts if len(p.strip()) >= 20]


def sentence_diff(old_text: str, new_text: str) -> dict[str, Any]:
    """Produce a compact sentence-level diff for the report."""
    old = split_sentences(old_text)
    new = split_sentences(new_text)
    matcher = SequenceMatcher(None, old, new, autojunk=False)
    changes: list[dict[str, Any]] = []

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        if tag == "replace":
            n = max(i2 - i1, j2 - j1)
            for k in range(n):
                before = old[i1 + k] if i1 + k < i2 else ""
                after = new[j1 + k] if j1 + k < j2 else ""
                changes.append({
                    "change_type": "MODIFIED",
                    "old_text": before,
                    "new_text": after,
                    "old_sentence": i1 + k + 1 if before else None,
                    "new_sentence": j1 + k + 1 if after else None,
                })
        elif tag == "delete":
            for idx in range(i1, i2):
                changes.append({
                    "change_type": "REMOVED",
                    "old_text": old[idx],
                    "new_text": "",
                    "old_sentence": idx + 1,
                    "new_sentence": None,
                })
        elif tag == "insert":
            for idx in range(j1, j2):
                changes.append({
                    "change_type": "ADDED",
                    "old_text": "",
                    "new_text": new[idx],
                    "old_sentence": None,
                    "new_sentence": idx + 1,
                })

    old_set = set(old)
    new_set = set(new)
    unchanged = len(old_set & new_set)
    total = max(len(old_set | new_set), 1)

    return {
        "similarity": document_similarity(old_text, new_text),
        "old_sentences": len(old),
        "new_sentences": len(new),
        "unchanged_unique_sentences": unchanged,
        "change_count": len(changes),
        "changes": changes[:500],
        "changes_truncated": len(changes) > 500,
        "same_document_likelihood": round(unchanged / total, 4),
    }


def serialize_results(results: dict[str, Any]) -> str:
    return json.dumps(results, ensure_ascii=False, default=str)


def deserialize_results(value: str | None) -> dict[str, Any] | None:
    if not value:
        return None
    try:
        obj = json.loads(value)
        return obj if isinstance(obj, dict) else None
    except Exception:
        return None
