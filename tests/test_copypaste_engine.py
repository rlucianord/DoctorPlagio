from pathlib import Path
import shutil
import tempfile

from app.backend import copypaste_engine as cp


def test_winnow():
    tokens = [f"palabra{i}" for i in range(100)]
    fingerprints = cp.winnow(tokens)
    assert fingerprints
    assert all(0 <= pos < len(tokens) for _, pos in fingerprints)


def test_copy_paste_local_corpus():
    base = cp.CORPUS_ROOT / "_test_copypaste"
    base.mkdir(parents=True, exist_ok=True)
    source = base / "fuente.txt"
    source.write_text(
        " ".join(
            f"palabra{i}"
            for i in range(80)
        ),
        encoding="utf-8",
    )

    db = Path(tempfile.gettempdir()) / "doctorplagio_test_copypaste.sqlite3"
    if db.exists():
        db.unlink()

    try:
        cp.index_document(
            source.read_text(encoding="utf-8"),
            {
                "source": "_test_copypaste",
                "relative_path": "_test_copypaste/fuente.txt",
                "title": "Fuente de prueba",
                "language": "es",
                "license": "prueba",
                "source_file": "_test_copypaste/fuente.txt",
            },
            db_path=db,
        )

        result = cp.search_copy_paste(
            source.read_text(encoding="utf-8"),
            db_path=db,
        )

        assert result["disponible"] is True
        assert result["porcentaje_copypaste"] > 80
        assert result["evidencias"]

    finally:
        if db.exists():
            db.unlink()
        shutil.rmtree(base, ignore_errors=True)
