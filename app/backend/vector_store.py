"""Vector store for DoctorPlagio V1.1.

Uses one embedding space: Sentence Transformers paraphrase-multilingual-mpnet-base-v2,
with normalized vectors and a Chroma collection configured for cosine distance.
"""

from pathlib import Path
import os
import chromadb

try:
    from chromadb.config import Settings  # noqa: F401
except Exception:
    pass

PROJECT_ROOT = Path(__file__).resolve().parents[2]

DEFAULT_CHROMA_PATH = PROJECT_ROOT / "chatbox" / "db" / "chroma_data"

CHROMA_PATH = Path(
    os.environ.get("CHROMA_PATH", str(DEFAULT_CHROMA_PATH))
)

COLLECTION_NAME = os.environ.get(
    "CHROMA_COLLECTION",
    "tesis_universitarias_v11"
)


def get_chroma_client():
    return chromadb.PersistentClient(path=str(CHROMA_PATH))


def get_collection(name: str | None = None):
    client = get_chroma_client()

    return client.get_or_create_collection(
        name=name or COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )