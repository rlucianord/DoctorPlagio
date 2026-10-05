from pathlib import Path
import os
import chromadb

PROJECT_ROOT = Path(__file__).resolve().parents[2]

DEFAULT_CHROMA_PATH = PROJECT_ROOT / "data" / "chroma_data"

CHROMA_PATH = Path(
    os.environ.get(
        "CHROMA_PATH",
        str(DEFAULT_CHROMA_PATH)
    )
)

COLLECTION_NAME = os.environ.get(
    "CHROMA_COLLECTION",
    "tesis_universitarias_v11"
)


def get_chroma_client():
    return chromadb.PersistentClient(
        path=str(CHROMA_PATH)
    )


def get_collection(name: str | None = None):
    client = get_chroma_client()

    return client.get_or_create_collection(
        name=name or COLLECTION_NAME,
        metadata={
            "hnsw:space": "cosine"
        },
    )