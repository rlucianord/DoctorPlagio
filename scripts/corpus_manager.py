"""Gestor del corpus de Copy/Paste de DoctorPlagio.

Uso desde la raíz del proyecto:

    python scripts/corpus_manager.py init
    python scripts/corpus_manager.py stats
    python scripts/corpus_manager.py ingest-file data/corpus/DoctorPlagio/documento.pdf --source doctorplagio
    python scripts/corpus_manager.py ingest-dir data/corpus/DoctorPlagio --source doctorplagio
    python scripts/corpus_manager.py ingest-csic data/corpus/CSIC/csic_es.txt
    python scripts/corpus_manager.py ingest-jsonl data/corpus/USC --source usc_cientifico

El programa es reanudable: un documento que ya está indexado con el mismo
contenido no se vuelve a procesar.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.backend.copypaste_engine import (  # noqa: E402
    CORPUS_ROOT,
    COPYPASTE_DB,
    estadisticas_corpus,
    index_document,
    initialize_index,
)


def _read_file(path: Path) -> str:
    suffix = path.suffix.lower()

    if suffix in {".txt", ".md", ".text"}:
        return path.read_text(encoding="utf-8", errors="ignore")

    if suffix == ".pdf":
        import pymupdf

        parts = []
        with pymupdf.open(path) as pdf:
            for page_number, page in enumerate(pdf, start=1):
                parts.append(
                    f"[[PAGE:{page_number}]]\n{page.get_text('text')}"
                )
        return "\n\n".join(parts)

    if suffix == ".docx":
        try:
            from docx import Document
        except ImportError as exc:
            raise RuntimeError(
                "Para DOCX instala python-docx: pip install python-docx"
            ) from exc

        doc = Document(path)
        return "\n\n".join(
            paragraph.text
            for paragraph in doc.paragraphs
            if paragraph.text.strip()
        )

    raise ValueError(f"Formato no soportado: {path.suffix}")


def ingest_file(
    path: Path,
    source: str,
    license_name: str = "",
    source_url: str = "",
) -> int:
    text = _read_file(path)

    try:
        relative = path.resolve().relative_to(CORPUS_ROOT.resolve())
    except ValueError:
        relative = Path(path.name)

    return index_document(
        text,
        {
            "source": source,
            "relative_path": str(relative).replace("\\", "/"),
            "title": path.stem,
            "language": "es",
            "license": license_name,
            "source_url": source_url,
            "source_file": str(relative).replace("\\", "/"),
            "source_locator": "",
        },
    )


def ingest_directory(
    directory: Path,
    source: str,
    license_name: str = "",
    source_url: str = "",
) -> int:
    supported = {".txt", ".md", ".text", ".pdf", ".docx"}
    count = 0

    for path in sorted(directory.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in supported:
            continue

        try:
            document_id = ingest_file(
                path,
                source=source,
                license_name=license_name,
                source_url=source_url,
            )
            if document_id:
                count += 1
                print(f"✅ {count}: {path}")
        except Exception as exc:
            print(f"⚠️ No se pudo indexar {path}: {exc}")

    return count


def ingest_csic(path: Path) -> int:
    """CSIC Spanish Corpus: un documento por línea."""
    source = "csic_es"
    source_file = str(
        path.resolve().relative_to(CORPUS_ROOT.resolve())
    ).replace("\\", "/")

    count = 0
    with path.open("r", encoding="utf-8", errors="ignore") as handle:
        for line_number, line in enumerate(handle, start=1):
            text = line.strip()
            if not text:
                continue

            try:
                index_document(
                    text,
                    {
                        "source": source,
                        "relative_path": f"{source_file}#linea={line_number}",
                        "title": text[:160],
                        "language": "es",
                        "license": "CC BY 4.0 (paquete del corpus; revisar derechos del contenido original)",
                        "source_url": "https://doi.org/10.5281/zenodo.7313126",
                        "source_file": source_file,
                        "source_locator": f"line:{line_number}",
                    },
                )
                count += 1
                if count % 500 == 0:
                    print(f"📚 CSIC: {count:,} documentos indexados...")
            except Exception as exc:
                print(f"⚠️ CSIC línea {line_number}: {exc}")

    return count


def _title_from_json(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return str(value.get("es") or value.get("en") or "")
    return ""


def ingest_jsonl(path: Path, source: str, language: str = "es") -> int:
    """Indexa JSONL con un objeto/documento por línea y un campo 'text'."""
    try:
        source_file = str(
            path.resolve().relative_to(CORPUS_ROOT.resolve())
        ).replace("\\", "/")
    except ValueError:
        source_file = path.name

    count = 0
    with path.open("r", encoding="utf-8", errors="ignore") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue

            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue

            if not isinstance(payload, dict):
                continue

            lang = str(
                payload.get("lang")
                or payload.get("language")
                or language
            ).lower()

            if language and lang != language.lower():
                continue

            text = str(payload.get("text") or "").strip()
            if not text:
                continue

            title = _title_from_json(payload.get("title"))
            source_url = str(
                payload.get("source_url")
                or payload.get("url")
                or ""
            )

            relative_id = str(
                payload.get("doc_id")
                or payload.get("id")
                or f"linea-{line_number}"
            )

            try:
                index_document(
                    text,
                    {
                        "source": source,
                        "relative_path": f"{source_file}#linea={line_number}#{relative_id}",
                        "title": title[:300],
                        "language": lang,
                        "license": str(
                            payload.get("license")
                            or "Revisar licencia de la fuente original"
                        ),
                        "source_url": source_url,
                        "source_file": source_file,
                        "source_locator": f"jsonl:{line_number}",
                    },
                )
                count += 1
                if count % 500 == 0:
                    print(f"📚 {source}: {count:,} documentos indexados...")
            except Exception as exc:
                print(f"⚠️ {source} línea {line_number}: {exc}")

    return count


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Gestor del corpus Copy/Paste de DoctorPlagio"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init", help="Crear la base del índice")

    sub.add_parser("stats", help="Mostrar estadísticas del corpus")

    p_file = sub.add_parser("ingest-file", help="Indexar un archivo")
    p_file.add_argument("path", type=Path)
    p_file.add_argument("--source", default="doctorplagio")
    p_file.add_argument("--license", default="")
    p_file.add_argument("--url", default="")

    p_dir = sub.add_parser("ingest-dir", help="Indexar una carpeta")
    p_dir.add_argument("path", type=Path)
    p_dir.add_argument("--source", default="doctorplagio")
    p_dir.add_argument("--license", default="")
    p_dir.add_argument("--url", default="")

    p_csic = sub.add_parser("ingest-csic", help="Indexar CSIC Spanish Corpus")
    p_csic.add_argument("path", type=Path)

    p_jsonl = sub.add_parser("ingest-jsonl", help="Indexar JSONL académico")
    p_jsonl.add_argument("path", type=Path)
    p_jsonl.add_argument("--source", required=True)
    p_jsonl.add_argument("--language", default="es")

    args = parser.parse_args()

    if args.command == "init":
        initialize_index()
        print(f"✅ Índice creado: {COPYPASTE_DB}")
        return 0

    if args.command == "stats":
        print(json.dumps(estadisticas_corpus(), ensure_ascii=False, indent=2))
        return 0

    if args.command == "ingest-file":
        if not args.path.exists():
            print(f"❌ No existe: {args.path}")
            return 1
        print(
            f"✅ Documento indexado con ID "
            f"{ingest_file(args.path, args.source, args.license, args.url)}"
        )
        return 0

    if args.command == "ingest-dir":
        if not args.path.exists():
            print(f"❌ No existe: {args.path}")
            return 1
        total = ingest_directory(
            args.path,
            args.source,
            args.license,
            args.url,
        )
        print(f"✅ Total procesado: {total:,}")
        return 0

    if args.command == "ingest-csic":
        if not args.path.exists():
            print(f"❌ No existe: {args.path}")
            return 1
        total = ingest_csic(args.path)
        print(f"✅ CSIC procesado: {total:,}")
        return 0

    if args.command == "ingest-jsonl":
        if not args.path.exists():
            print(f"❌ No existe: {args.path}")
            return 1
        total = ingest_jsonl(
            args.path,
            args.source,
            args.language,
        )
        print(f"✅ JSONL procesado: {total:,}")
        return 0

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
