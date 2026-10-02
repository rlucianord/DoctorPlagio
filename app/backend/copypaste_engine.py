"""Motor local de detección de Copy/Paste para DoctorPlagio.

El motor está separado de MPNet y GPT-OSS. Su objetivo es detectar
coincidencias textuales fuertes contra un corpus local que puede crecer
con nuevos documentos.

Utiliza fingerprints tipo winnowing almacenados en SQLite. No intenta
decidir autoría ni similitud semántica.
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CORPUS_ROOT = PROJECT_ROOT / "data" / "corpus"
COPYPASTE_DB = PROJECT_ROOT / "data" / "copypaste" / "copypaste_index.sqlite3"

# Parámetros conservadores para Copy/Paste.
NGRAM_SIZE = 8
WINDOW_SIZE = 5
MIN_MATCH_TOKENS = 20
MAX_CANDIDATES = 20
MAX_EVIDENCES = 30
SQL_BATCH_SIZE = 400


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
    """Convierte texto a tokens comparables y conserva página cuando existe."""
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
    payload = "\x1f".join(tokens).encode("utf-8")
    return hashlib.blake2b(payload, digest_size=8).hexdigest()


def winnow(tokens: list[str], k: int = NGRAM_SIZE, window: int = WINDOW_SIZE):
    """Devuelve fingerprints (hash, posición inicial)."""
    if len(tokens) < k:
        return []

    grams = [
        _hash_ngram(tokens[i : i + k])
        for i in range(len(tokens) - k + 1)
    ]

    if not grams:
        return []

    selected: list[tuple[str, int]] = []
    last_selected = -1

    # Hashes hex se pueden comparar lexicográficamente de forma estable.
    if len(grams) <= window:
        starts = [0]
    else:
        starts = range(len(grams) - window + 1)

    for start in starts:
        end = min(len(grams), start + window)
        window_items = [(grams[i], i) for i in range(start, end)]
        chosen_hash, chosen_pos = min(
            window_items,
            key=lambda item: (item[0], -item[1]),
        )
        if chosen_pos != last_selected:
            selected.append((chosen_hash, chosen_pos))
            last_selected = chosen_pos

    return selected


def _connect(db_path: Path = COPYPASTE_DB) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA temp_store=MEMORY")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def initialize_index(db_path: Path = COPYPASTE_DB) -> None:
    """Crea el índice si no existe."""
    CORPUS_ROOT.mkdir(parents=True, exist_ok=True)
    (PROJECT_ROOT / "data" / "copypaste").mkdir(parents=True, exist_ok=True)
    with _connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS corpus_documents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source TEXT NOT NULL,
                relative_path TEXT NOT NULL,
                title TEXT,
                language TEXT,
                license TEXT,
                source_url TEXT,
                source_file TEXT,
                source_locator TEXT,
                content_hash TEXT NOT NULL,
                token_count INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(source, relative_path)
            );

            CREATE TABLE IF NOT EXISTS fingerprints (
                fingerprint TEXT NOT NULL,
                document_id INTEGER NOT NULL,
                position INTEGER NOT NULL,
                PRIMARY KEY (fingerprint, document_id, position),
                FOREIGN KEY(document_id) REFERENCES corpus_documents(id)
                    ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_fingerprints_hash
                ON fingerprints(fingerprint);

            CREATE INDEX IF NOT EXISTS idx_fingerprints_document
                ON fingerprints(document_id);

            CREATE TABLE IF NOT EXISTS corpus_meta (
                key TEXT PRIMARY KEY,
                value TEXT
            );
            """
        )

        columns = {
            row[1]
            for row in conn.execute("PRAGMA table_info(corpus_documents)").fetchall()
        }
        for name, definition in {
            "source_file": "TEXT",
            "source_locator": "TEXT",
        }.items():
            if name not in columns:
                conn.execute(
                    f"ALTER TABLE corpus_documents ADD COLUMN {name} {definition}"
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


def index_document(
    text: str,
    metadata: dict[str, Any] | None = None,
    db_path: Path = COPYPASTE_DB,
    replace: bool = False,
) -> int:
    """Indexa un documento individual y devuelve su ID."""
    initialize_index(db_path)
    meta = _metadata_text(metadata)
    tokens = normalize_tokens(text)
    token_texts = [item.text for item in tokens]

    if not token_texts:
        return 0

    content_hash = hashlib.sha256(
        "\n".join(token_texts).encode("utf-8")
    ).hexdigest()

    with _connect(db_path) as conn:
        existing = conn.execute(
            """
            SELECT id, content_hash
            FROM corpus_documents
            WHERE source = ? AND relative_path = ?
            """,
            (meta["source"], meta["relative_path"]),
        ).fetchone()

        if existing:
            if not replace and existing[1] == content_hash:
                return int(existing[0])
            conn.execute(
                "DELETE FROM corpus_documents WHERE id = ?",
                (existing[0],),
            )

        cur = conn.execute(
            """
            INSERT INTO corpus_documents
            (source, relative_path, title, language, license, source_url,
             source_file, source_locator, content_hash, token_count)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                meta["source"],
                meta["relative_path"],
                meta["title"],
                meta["language"],
                meta["license"],
                meta["source_url"],
                meta["source_file"],
                meta["source_locator"],
                content_hash,
                len(token_texts),
            ),
        )
        document_id = int(cur.lastrowid)

        rows = [
            (fingerprint, document_id, position)
            for fingerprint, position in winnow(token_texts)
        ]

        conn.executemany(
            """
            INSERT OR IGNORE INTO fingerprints
            (fingerprint, document_id, position)
            VALUES (?, ?, ?)
            """,
            rows,
        )
        conn.commit()

    return document_id


def _query_fingerprint_rows(
    conn: sqlite3.Connection,
    hashes: list[str],
) -> list[tuple[str, int, int]]:
    rows: list[tuple[str, int, int]] = []
    for start in range(0, len(hashes), SQL_BATCH_SIZE):
        batch = hashes[start : start + SQL_BATCH_SIZE]
        placeholders = ",".join("?" for _ in batch)
        rows.extend(
            conn.execute(
                f"""
                SELECT fingerprint, document_id, position
                FROM fingerprints
                WHERE fingerprint IN ({placeholders})
                """,
                batch,
            ).fetchall()
        )
    return rows


def _covered_intervals(positions: list[int], k: int = NGRAM_SIZE) -> list[tuple[int, int]]:
    """Une los intervalos cubiertos por fingerprints coincidentes."""
    if not positions:
        return []

    intervals = sorted(
        (position, position + k - 1)
        for position in set(positions)
    )

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
) -> tuple[int, int] | None:
    intervals = _covered_intervals(positions, k)
    candidates = [
        interval
        for interval in intervals
        if interval[1] - interval[0] + 1 >= min_len
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda pair: pair[1] - pair[0])


def _extract_evidence(
    query_tokens: list[Token],
    source_text: str,
    source_positions: list[int],
    query_positions: list[int],
    offset: int,
) -> dict[str, Any] | None:
    if not query_positions:
        return None

    run = _best_covered_run(query_positions)
    if not run:
        return None

    best_start, best_end = run
    run_len = best_end - best_start + 1

    source_start = best_start + offset
    source_end = best_end + offset

    source_tokens = normalize_tokens(source_text)
    if source_start < 0 or source_end >= len(source_tokens):
        return None

    query_fragment = " ".join(
        token.text
        for token in query_tokens[best_start : best_end + 1]
    )
    source_fragment = " ".join(
        token.text
        for token in source_tokens[source_start : source_end + 1]
    )

    page_values = [
        token.page
        for token in query_tokens[best_start : best_end + 1]
        if token.page is not None
    ]

    source_fragment_tokens = source_tokens[source_start : source_end + 1]
    source_page_values = [
        token.page
        for token in source_fragment_tokens
        if token.page is not None
    ]

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


def _load_source_text(
    source_file_name: str,
    source_locator: str,
    relative_path: str,
) -> str:
    """Recupera el texto fuente sin cargar un corpus gigante completo."""
    candidate = source_file_name or relative_path
    path = CORPUS_ROOT / candidate

    if not path.is_file():
        return ""

    locator = source_locator or ""

    if locator.startswith("line:"):
        try:
            line_number = int(locator.split(":", 1)[1])
        except ValueError:
            line_number = 0

        if line_number > 0:
            with path.open("r", encoding="utf-8", errors="ignore") as handle:
                for index, line in enumerate(handle, start=1):
                    if index == line_number:
                        return line.strip()
            return ""

    if locator.startswith("jsonl:"):
        try:
            line_number = int(locator.split(":", 1)[1])
        except ValueError:
            line_number = 0

        if line_number > 0:
            with path.open("r", encoding="utf-8", errors="ignore") as handle:
                for index, line in enumerate(handle, start=1):
                    if index == line_number:
                        try:
                            payload = json.loads(line)
                        except json.JSONDecodeError:
                            return ""
                        return str(payload.get("text") or "") if isinstance(payload, dict) else ""
            return ""

    if path.suffix.lower() == ".pdf":
        try:
            import pymupdf
            with pymupdf.open(path) as pdf:
                parts = []
                for page_number, page in enumerate(pdf, start=1):
                    parts.append(f"[[PAGE:{page_number}]]\n{page.get_text('text')}")
                return "\n\n".join(parts)
        except Exception:
            return ""

    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""


def search_copy_paste(
    text: str,
    db_path: Path = COPYPASTE_DB,
    max_candidates: int = MAX_CANDIDATES,
    max_evidences: int = MAX_EVIDENCES,
) -> dict[str, Any]:
    """Busca bloques de Copy/Paste en el corpus local."""
    initialize_index(db_path)

    query_tokens = normalize_tokens(text)
    token_texts = [item.text for item in query_tokens]

    if len(token_texts) < NGRAM_SIZE:
        return {
            "disponible": False,
            "mensaje": "El texto es demasiado corto para la búsqueda de Copy/Paste.",
            "porcentaje_copypaste": 0.0,
            "fuentes": [],
            "evidencias": [],
            "documentos_corpus": 0,
        }

    query_fingerprints = winnow(token_texts)
    if not query_fingerprints:
        return {
            "disponible": False,
            "mensaje": "No se pudieron generar fingerprints para el texto.",
            "porcentaje_copypaste": 0.0,
            "fuentes": [],
            "evidencias": [],
            "documentos_corpus": 0,
        }

    hashes = [item[0] for item in query_fingerprints]
    query_positions_by_hash = defaultdict(list)
    for fingerprint, position in query_fingerprints:
        query_positions_by_hash[fingerprint].append(position)

    with _connect(db_path) as conn:
        total_docs = conn.execute(
            "SELECT COUNT(*) FROM corpus_documents"
        ).fetchone()[0]

        rows = _query_fingerprint_rows(conn, list(dict.fromkeys(hashes)))

        candidate_counts = Counter(row[1] for row in rows)
        candidate_ids = [
            doc_id
            for doc_id, _ in candidate_counts.most_common(max_candidates)
        ]

        if not candidate_ids:
            return {
                "disponible": True,
                "mensaje": "No se encontraron fingerprints compartidos en el corpus local.",
                "porcentaje_copypaste": 0.0,
                "fuentes": [],
                "evidencias": [],
                "documentos_corpus": int(total_docs),
            }

        placeholders = ",".join("?" for _ in candidate_ids)
        docs = conn.execute(
            f"""
            SELECT id, source, relative_path, title, language, license, source_url, source_file, source_locator
            FROM corpus_documents
            WHERE id IN ({placeholders})
            """,
            candidate_ids,
        ).fetchall()

        docs_by_id = {int(row[0]): row for row in docs}

        shared_by_doc_offset: dict[int, dict[int, list[int]]] = defaultdict(lambda: defaultdict(list))

        for fingerprint, doc_id, source_position in rows:
            if doc_id not in docs_by_id:
                continue
            for query_position in query_positions_by_hash.get(fingerprint, []):
                offset = int(source_position) - int(query_position)
                shared_by_doc_offset[int(doc_id)][offset].append(int(query_position))

        evidences: list[dict[str, Any]] = []
        covered_query_positions: set[int] = set()

        for doc_id in candidate_ids:
            row = docs_by_id.get(doc_id)
            if not row:
                continue

            source_name = row[1]
            relative_path = row[2]
            title = row[3]
            source_url = row[6]
            source_file_name = row[7]
            source_locator = row[8]

            source_text = _load_source_text(
                source_file_name,
                source_locator,
                relative_path,
            )

            if not source_text:
                # El resultado sigue siendo válido como candidato, pero sin
                # fragmento fuente hasta que el archivo original esté disponible.
                continue

            for offset, q_positions in shared_by_doc_offset[doc_id].items():
                evidence = _extract_evidence(
                    query_tokens,
                    source_text,
                    [],
                    q_positions,
                    offset,
                )
                if evidence:
                    evidence.update(
                        {
                            "fuente": source_name,
                            "archivo_fuente": relative_path,
                            "titulo_fuente": title or relative_path,
                            "url_fuente": source_url,
                            "cobertura_fragmento": round(
                                evidence["tokens_coincidentes"]
                                / max(len(token_texts), 1)
                                * 100,
                                2,
                            ),
                        }
                    )
                    evidences.append(evidence)

                    start = evidence["posicion_documento"]
                    end = start + evidence["tokens_coincidentes"]
                    covered_query_positions.update(range(start, end))

        evidences.sort(
            key=lambda item: item["tokens_coincidentes"],
            reverse=True,
        )

        unique_evidences: list[dict[str, Any]] = []
        seen = set()
        for evidence in evidences:
            key = (
                evidence["fuente"],
                evidence["archivo_fuente"],
                evidence["posicion_documento"],
                evidence["posicion_fuente"],
            )
            if key in seen:
                continue
            seen.add(key)
            unique_evidences.append(evidence)
            if len(unique_evidences) >= max_evidences:
                break

        # Recalcular cobertura sin doble conteo usando todos los bloques.
        coverage = len(covered_query_positions) / max(len(token_texts), 1) * 100.0

        source_counter = Counter(
            item["fuente"] for item in unique_evidences
        )

        sources = []
        for source, count in source_counter.most_common():
            sources.append(
                {
                    "fuente": source,
                    "evidencias": count,
                }
            )

        return {
            "disponible": True,
            "mensaje": (
                "Se encontraron coincidencias de texto en el corpus local."
                if unique_evidences
                else "No se encontraron bloques de Copy/Paste con evidencia suficiente."
            ),
            "porcentaje_copypaste": round(min(100.0, coverage), 2),
            "fuentes": sources,
            "evidencias": unique_evidences,
            "documentos_corpus": int(total_docs),
            "fingerprints_consultados": len(query_fingerprints),
        }


def estadisticas_corpus(db_path: Path = COPYPASTE_DB) -> dict[str, Any]:
    initialize_index(db_path)
    with _connect(db_path) as conn:
        documents = conn.execute("SELECT COUNT(*) FROM corpus_documents").fetchone()[0]
        fingerprints = conn.execute("SELECT COUNT(*) FROM fingerprints").fetchone()[0]
        sources = conn.execute(
            "SELECT source, COUNT(*) FROM corpus_documents GROUP BY source ORDER BY COUNT(*) DESC"
        ).fetchall()
    return {
        "documentos": int(documents),
        "fingerprints": int(fingerprints),
        "fuentes": [
            {"fuente": row[0], "documentos": int(row[1])}
            for row in sources
        ],
        "base_datos": str(db_path),
    }
