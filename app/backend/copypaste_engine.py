"""Motor de detección de Copy/Paste de DoctorPlagio.

El motor usa PostgreSQL como índice persistente del corpus. ChromaDB y
GPT-OSS quedan separados: este módulo busca evidencia textual mediante
fingerprints tipo Winnowing.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import psycopg2
from psycopg2.extras import execute_values

from .config import DATABASE_URL

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CORPUS_ROOT = PROJECT_ROOT / "data" / "corpus"

NGRAM_SIZE = 8
WINDOW_SIZE = 5
# Longitud mínima de una evidencia textual fuerte.
# Se mantiene en 20 para producción, pero las coincidencias exactas
# de fingerprints pueden producir evidencia aun cuando el texto de
# prueba sea más corto; esto evita falsos "sin coincidencias" en
# fragmentos cortos.
MIN_MATCH_TOKENS = 20
MAX_CANDIDATES = 20
MAX_EVIDENCES = 30
SQL_BATCH_SIZE = 1000

TOKEN_RE = re.compile(
    r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ0-9]+(?:[-'][A-Za-zÁÉÍÓÚÜÑáéíóúüñ0-9]+)*",
    re.UNICODE,
)
PAGE_RE = re.compile(r"\[\[PAGE:(\d+)\]\]")


@dataclass(frozen=True)
class Token:
    text: str
    page: int | None = None


def normalize_tokens(text: str) -> list[Token]:
    """Convierte texto a tokens comparables y conserva la página."""
    current_page: int | None = None
    result: list[Token] = []
    for line in (text or "").replace("\r\n", "\n").replace("\r", "\n").splitlines():
        marker = PAGE_RE.search(line)
        if marker:
            current_page = int(marker.group(1))
            line = PAGE_RE.sub("", line)
        for token in TOKEN_RE.findall(line):
            result.append(Token(token.lower(), current_page))
    return result


def _hash_ngram(tokens: list[str]) -> str:
    return hashlib.blake2b("\x1f".join(tokens).encode("utf-8"), digest_size=8).hexdigest()


def winnow(tokens: list[str], k: int = NGRAM_SIZE, window: int = WINDOW_SIZE):
    """Devuelve fingerprints (hash, posición inicial)."""
    if len(tokens) < k:
        return []
    grams = [_hash_ngram(tokens[i:i + k]) for i in range(len(tokens) - k + 1)]
    if not grams:
        return []
    selected: list[tuple[str, int]] = []
    last_selected = -1
    starts = [0] if len(grams) <= window else range(len(grams) - window + 1)
    for start in starts:
        end = min(len(grams), start + window)
        chosen_hash, chosen_pos = min(
            ((grams[i], i) for i in range(start, end)),
            key=lambda item: (item[0], -item[1]),
        )
        if chosen_pos != last_selected:
            selected.append((chosen_hash, chosen_pos))
            last_selected = chosen_pos
    return selected


def _connect():
    """Abre una conexión directa a PostgreSQL para consultas masivas."""
    return psycopg2.connect(DATABASE_URL)


def initialize_index(db_path: Path | None = None) -> None:
    """Verifica que las tablas del corpus existan en PostgreSQL.

    No crea ni modifica una base SQLite. Las tablas fueron migradas a
    PostgreSQL y este módulo trabaja exclusivamente contra ellas.
    """
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT to_regclass('public.corpus_documents')")
            documents_table = cur.fetchone()[0]
            cur.execute("SELECT to_regclass('public.corpus_fingerprints')")
            fingerprints_table = cur.fetchone()[0]
    if not documents_table or not fingerprints_table:
        raise RuntimeError(
            "No se encontraron las tablas PostgreSQL corpus_documents y/o "
            "corpus_fingerprints en la base de datos configurada."
        )


def _metadata_text(metadata: dict[str, Any] | None) -> dict[str, str]:
    metadata = metadata or {}
    return {
        "source": str(metadata.get("source") or "corpus_local"),
        "relative_path": str(metadata.get("relative_path") or ""),
        "title": str(metadata.get("title") or ""),
        "language": str(metadata.get("language") or "es"),
        "license": str(metadata.get("license") or ""),
        "source_url": str(metadata.get("source_url") or ""),
        "source_file": str(metadata.get("source_file") or ""),
        "source_locator": str(metadata.get("source_locator") or ""),
    }


def _next_document_id(cur) -> int:
    cur.execute("SELECT COALESCE(MAX(id), 0) + 1 FROM corpus_documents")
    return int(cur.fetchone()[0])


def index_document(
    text: str,
    metadata: dict[str, Any] | None = None,
    db_path: Path | None = None,
    replace: bool = False,
) -> int:
    """Indexa un documento nuevo directamente en PostgreSQL."""
    initialize_index(db_path)
    meta = _metadata_text(metadata)
    tokens = normalize_tokens(text)
    token_texts = [item.text for item in tokens]
    if not token_texts:
        return 0

    content_hash = hashlib.sha256("\n".join(token_texts).encode("utf-8")).hexdigest()

    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, content_hash
                FROM corpus_documents
                WHERE source = %s AND relative_path = %s
                """,
                (meta["source"], meta["relative_path"]),
            )
            existing = cur.fetchone()

            if existing:
                if not replace and existing[1] == content_hash:
                    return int(existing[0])
                cur.execute("DELETE FROM corpus_documents WHERE id = %s", (existing[0],))

            document_id = _next_document_id(cur)
            cur.execute(
                """
                INSERT INTO corpus_documents
                (id, source, relative_path, title, language, license, source_url,
                 source_file, source_locator, content_hash, token_count)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    document_id, meta["source"], meta["relative_path"], meta["title"],
                    meta["language"], meta["license"], meta["source_url"],
                    meta["source_file"], meta["source_locator"], content_hash,
                    len(token_texts),
                ),
            )

            rows = [
                (fingerprint, document_id, position)
                for fingerprint, position in winnow(token_texts)
            ]
            if rows:
                execute_values(
                    cur,
                    """
                    INSERT INTO corpus_fingerprints (fingerprint, document_id, position)
                    VALUES %s
                    ON CONFLICT (fingerprint, document_id, position) DO NOTHING
                    """,
                    rows,
                    page_size=1000,
                )
    return document_id


def _candidate_document_counts(cur, hashes: list[str], limit: int) -> Counter:
    counts: Counter = Counter()
    for start in range(0, len(hashes), SQL_BATCH_SIZE):
        batch = hashes[start:start + SQL_BATCH_SIZE]
        cur.execute(
            """
            SELECT document_id, COUNT(*)
            FROM corpus_fingerprints
            WHERE fingerprint = ANY(%s)
            GROUP BY document_id
            ORDER BY COUNT(*) DESC
            LIMIT %s
            """,
            (batch, limit),
        )
        counts.update({int(doc_id): int(count) for doc_id, count in cur.fetchall()})
    return counts


def _query_fingerprint_rows(cur, hashes: list[str], candidate_ids: list[int]):
    rows: list[tuple[str, int, int]] = []
    if not candidate_ids:
        return rows
    for start in range(0, len(hashes), SQL_BATCH_SIZE):
        batch = hashes[start:start + SQL_BATCH_SIZE]
        cur.execute(
            """
            SELECT fingerprint, document_id, position
            FROM corpus_fingerprints
            WHERE fingerprint = ANY(%s)
              AND document_id = ANY(%s)
            """,
            (batch, candidate_ids),
        )
        rows.extend((str(fp), int(doc_id), int(pos)) for fp, doc_id, pos in cur.fetchall())
    return rows


def _covered_intervals(positions: list[int], k: int = NGRAM_SIZE) -> list[tuple[int, int]]:
    if not positions:
        return []
    intervals = sorted((position, position + k - 1) for position in set(positions))
    merged: list[list[int]] = []
    for start, end in intervals:
        if not merged or start > merged[-1][1] + 1:
            merged.append([start, end])
        else:
            merged[-1][1] = max(merged[-1][1], end)
    return [(start, end) for start, end in merged]


def _best_covered_run(
    positions: list[int],
    k: int = NGRAM_SIZE,
    min_len: int = MIN_MATCH_TOKENS,
    allow_short: bool = False,
):
    """Obtiene el tramo continuo mejor cubierto por fingerprints.

    En producción se exige MIN_MATCH_TOKENS para considerar una evidencia
    fuerte. Sin embargo, cuando PostgreSQL ya confirmó fingerprints
    compartidos, permitimos recuperar el tramo mínimo cubierto por un
    n-grama (k tokens). Esto evita que una coincidencia real desaparezca
    simplemente porque el texto consultado es corto.
    """
    intervals = _covered_intervals(positions, k)
    if not intervals:
        return None

    candidates = [
        interval for interval in intervals
        if interval[1] - interval[0] + 1 >= min_len
    ]

    if candidates:
        return max(candidates, key=lambda pair: pair[1] - pair[0])

    if allow_short:
        # Un fingerprint de Winnowing ya representa k tokens coincidentes.
        short_candidates = [
            interval for interval in intervals
            if interval[1] - interval[0] + 1 >= k
        ]
        if short_candidates:
            return max(
                short_candidates,
                key=lambda pair: pair[1] - pair[0],
            )

    return None


def _extract_evidence(
    query_tokens: list[Token],
    source_text: str,
    query_positions: list[int],
    offset: int,
) -> dict[str, Any] | None:
    if not query_positions:
        return None
    run = _best_covered_run(query_positions, allow_short=True)
    if not run:
        return None
    best_start, best_end = run
    run_len = best_end - best_start + 1
    source_start = best_start + offset
    source_end = best_end + offset
    source_tokens = normalize_tokens(source_text)
    if source_start < 0 or source_end >= len(source_tokens):
        return None

    query_fragment = " ".join(t.text for t in query_tokens[best_start:best_end + 1])
    source_fragment = " ".join(t.text for t in source_tokens[source_start:source_end + 1])
    page_values = [t.page for t in query_tokens[best_start:best_end + 1] if t.page is not None]
    source_page_values = [t.page for t in source_tokens[source_start:source_end + 1] if t.page is not None]

    return {
        "tipo": "copia_directa",
        "tokens_coincidentes": run_len,
        "posicion_documento": best_start,
        "posicion_fuente": source_start,
        "pagina_documento": page_values[0] if page_values else None,
        "pagina_fuente": source_page_values[0] if source_page_values else None,
        "fragmento_documento": query_fragment[:1500],
        "fragmento_fuente": source_fragment[:1500],
    }


def _load_source_text(source_file_name: str, source_locator: str, relative_path: str) -> str:
    """Recupera texto fuente si el archivo original sigue disponible localmente."""
    candidate = source_file_name or relative_path
    path = CORPUS_ROOT / candidate

    # Algunas cargas antiguas guardan el archivo con un prefijo de
    # directorio en metadata aunque físicamente esté directamente bajo
    # data/corpus. Primero intentamos la ruta exacta y luego una ruta
    # alternativa segura basada en el nombre del archivo.
    if not path.is_file():
        candidate_name = Path(candidate).name
        fallback_path = CORPUS_ROOT / candidate_name
        if fallback_path.is_file():
            path = fallback_path
        else:
            return ""
    locator = source_locator or ""

    if locator.startswith("line:") or locator.startswith("jsonl:"):
        try:
            line_number = int(locator.split(":", 1)[1])
        except ValueError:
            line_number = 0
        if line_number > 0:
            with path.open("r", encoding="utf-8", errors="ignore") as handle:
                for index, line in enumerate(handle, start=1):
                    if index == line_number:
                        if locator.startswith("jsonl:"):
                            try:
                                payload = json.loads(line)
                            except json.JSONDecodeError:
                                return ""
                            return str(payload.get("text") or "") if isinstance(payload, dict) else ""
                        return line.strip()
        return ""

    if path.suffix.lower() == ".pdf":
        try:
            import pymupdf
            with pymupdf.open(path) as pdf:
                return "\n\n".join(
                    f"[[PAGE:{page_number}]]\n{page.get_text('text')}"
                    for page_number, page in enumerate(pdf, start=1)
                )
        except Exception:
            return ""

    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""


def search_copy_paste(
    text: str,
    db_path: Path | None = None,
    max_candidates: int = MAX_CANDIDATES,
    max_evidences: int = MAX_EVIDENCES,
) -> dict[str, Any]:
    """Busca Copy/Paste contra el corpus almacenado en PostgreSQL."""
    initialize_index(db_path)
    query_tokens = normalize_tokens(text)
    token_texts = [item.text for item in query_tokens]

    if len(token_texts) < NGRAM_SIZE:
        return {
            "disponible": False,
            "mensaje": "El texto es demasiado corto para la búsqueda de Copy/Paste.",
            "porcentaje_copypaste": 0.0,
            "fuentes": [], "evidencias": [], "documentos_corpus": 0,
        }

    query_fingerprints = winnow(token_texts)
    if not query_fingerprints:
        return {
            "disponible": False,
            "mensaje": "No se pudieron generar fingerprints para el texto.",
            "porcentaje_copypaste": 0.0,
            "fuentes": [], "evidencias": [], "documentos_corpus": 0,
        }

    hashes = list(dict.fromkeys(fp for fp, _ in query_fingerprints))
    query_positions_by_hash = defaultdict(list)
    for fingerprint, position in query_fingerprints:
        query_positions_by_hash[fingerprint].append(position)

    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM corpus_documents")
            total_docs = int(cur.fetchone()[0])

            candidate_counts = _candidate_document_counts(cur, hashes, max_candidates)
            candidate_ids = [doc_id for doc_id, _ in candidate_counts.most_common(max_candidates)]

            if not candidate_ids:
                return {
                    "disponible": True,
                    "mensaje": "No se encontraron fingerprints compartidos en el corpus local.",
                    "porcentaje_copypaste": 0.0,
                    "fuentes": [], "evidencias": [], "documentos_corpus": total_docs,
                    "fingerprints_consultados": len(query_fingerprints),
                }

            placeholders = ",".join(["%s"] * len(candidate_ids))
            cur.execute(
                f"""
                SELECT id, source, relative_path, title, language, license,
                       source_url, source_file, source_locator
                FROM corpus_documents
                WHERE id IN ({placeholders})
                """,
                candidate_ids,
            )
            docs = cur.fetchall()
            docs_by_id = {int(row[0]): row for row in docs}

            rows = _query_fingerprint_rows(cur, hashes, candidate_ids)

    shared_by_doc_offset: dict[int, dict[int, list[int]]] = defaultdict(lambda: defaultdict(list))
    for fingerprint, doc_id, source_position in rows:
        for query_position in query_positions_by_hash.get(fingerprint, []):
            offset = source_position - query_position
            shared_by_doc_offset[doc_id][offset].append(query_position)

    evidences: list[dict[str, Any]] = []
    covered_query_positions: set[int] = set()

    for doc_id in candidate_ids:
        row = docs_by_id.get(doc_id)
        if not row:
            continue
        source_name, relative_path, title = row[1], row[2], row[3]
        source_url, source_file_name, source_locator = row[6], row[7], row[8]
        source_text = _load_source_text(source_file_name, source_locator, relative_path)

        for offset, q_positions in shared_by_doc_offset[doc_id].items():
            evidence = _extract_evidence(query_tokens, source_text, q_positions, offset) if source_text else None
            if evidence is None:
                run = _best_covered_run(q_positions, allow_short=True)
                if not run:
                    continue
                best_start, best_end = run
                run_len = best_end - best_start + 1
                page_values = [t.page for t in query_tokens[best_start:best_end + 1] if t.page is not None]
                evidence = {
                    "tipo": "copia_directa",
                    "tokens_coincidentes": run_len,
                    "posicion_documento": best_start,
                    "posicion_fuente": best_start + offset,
                    "pagina_documento": page_values[0] if page_values else None,
                    "pagina_fuente": None,
                    "fragmento_documento": " ".join(t.text for t in query_tokens[best_start:best_end + 1])[:1500],
                    "fragmento_fuente": "",
                }

            evidence.update({
                "fuente": source_name,
                "archivo_fuente": relative_path,
                "titulo_fuente": title or relative_path,
                "url_fuente": source_url,
                "cobertura_fragmento": round(evidence["tokens_coincidentes"] / max(len(token_texts), 1) * 100, 2),
            })
            evidences.append(evidence)
            start = evidence["posicion_documento"]
            end = start + evidence["tokens_coincidentes"]
            covered_query_positions.update(range(start, end))

    evidences.sort(key=lambda item: item["tokens_coincidentes"], reverse=True)
    unique_evidences: list[dict[str, Any]] = []
    seen = set()
    for evidence in evidences:
        key = (
            evidence["fuente"], evidence["archivo_fuente"],
            evidence["posicion_documento"], evidence["posicion_fuente"],
        )
        if key in seen:
            continue
        seen.add(key)
        unique_evidences.append(evidence)
        if len(unique_evidences) >= max_evidences:
            break

    coverage = len(covered_query_positions) / max(len(token_texts), 1) * 100.0
    sources = []
    seen_sources = set()
    for evidence in unique_evidences:
        key = (evidence["fuente"], evidence["archivo_fuente"])
        if key not in seen_sources:
            seen_sources.add(key)
            sources.append({
                "fuente": evidence["fuente"],
                "archivo": evidence["archivo_fuente"],
                "titulo": evidence["titulo_fuente"],
                "url": evidence["url_fuente"],
            })

    return {
        "disponible": True,
        "mensaje": (
            "Se encontraron coincidencias textuales."
            if unique_evidences else
            (
                "Se encontraron fingerprints compartidos, pero no fue posible "
                "construir evidencia textual recuperable."
                if candidate_ids and rows
                else
                "No se encontraron bloques con evidencia textual suficiente."
            )
        ),
        "porcentaje_copypaste": round(min(100.0, coverage), 2),
        "fuentes": sources,
        "evidencias": unique_evidences,
        "documentos_corpus": total_docs,
        "fingerprints_consultados": len(query_fingerprints),
    }


def estadisticas_corpus(db_path: Path | None = None) -> dict[str, Any]:
    initialize_index(db_path)
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM corpus_documents")
            documents = int(cur.fetchone()[0])
            cur.execute("SELECT COUNT(*) FROM corpus_fingerprints")
            fingerprints = int(cur.fetchone()[0])
            cur.execute(
                "SELECT source, COUNT(*) FROM corpus_documents GROUP BY source ORDER BY COUNT(*) DESC"
            )
            sources = cur.fetchall()
    return {
        "documentos": documents,
        "fingerprints": fingerprints,
        "fuentes": [{"fuente": row[0], "documentos": int(row[1])} for row in sources],
        "base_datos": DATABASE_URL.split("@")[-1],
        "motor": "PostgreSQL",
    }
