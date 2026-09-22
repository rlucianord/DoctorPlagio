"""Migrate the existing thesis chunks into the V1.1 cosine collection.

This does NOT delete the old collection. It reads the existing documents and
re-embeds them with the single V1.1 model so the vector space is explicit and consistent.
"""
from pathlib import Path
import sys
import numpy as np
from sentence_transformers import SentenceTransformer
import chromadb

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.backend.vector_store import CHROMA_PATH, COLLECTION_NAME
from app.backend.similarity_engine import MODEL_NAME

OLD_COLLECTION = "tesis_universitarias"
BATCH = 64


def main():
    client = chromadb.PersistentClient(path=str(CHROMA_PATH))
    old = client.get_collection(OLD_COLLECTION)
    new = client.get_or_create_collection(COLLECTION_NAME, metadata={"hnsw:space": "cosine"})
    model = SentenceTransformer(MODEL_NAME)

    total = old.count()
    print(f"Colección antigua: {OLD_COLLECTION} ({total} chunks)")
    print(f"Colección nueva: {COLLECTION_NAME}")
    if total == 0:
        print("No hay documentos para migrar.")
        return

    for offset in range(0, total, BATCH):
        data = old.get(
            limit=BATCH,
            offset=offset,
            include=["documents", "metadatas"],
        )
        docs = data.get("documents") or []
        ids = data.get("ids") or []
        metas = data.get("metadatas") or [{} for _ in docs]
        if not docs:
            continue
        embeddings = model.encode(
            docs,
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
        ).astype("float32")
        enriched = []
        for meta in metas:
            m = dict(meta or {})
            m["model"] = MODEL_NAME
            m["embedding_normalized"] = True
            enriched.append(m)
        new.upsert(
            ids=ids,
            embeddings=embeddings.tolist(),
            documents=docs,
            metadatas=enriched,
        )
        print(f"Migrados {min(offset+BATCH,total)}/{total}")

    print("✅ Migración completada. La colección antigua NO fue eliminada.")


if __name__ == "__main__":
    main()
