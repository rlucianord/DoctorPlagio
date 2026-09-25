import os
import sys
import asyncio
from pathlib import Path

import fitz
from sentence_transformers import SentenceTransformer

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.vector_store import get_collection
from backend.similarity_engine import MODEL_NAME, sentence_chunks

MODEL = None


def get_model():
    global MODEL
    if MODEL is None:
        MODEL = SentenceTransformer(MODEL_NAME)
    return MODEL


def extraer_texto_pdf(path_archivo):
    texto_completo = ""
    try:
        with fitz.open(path_archivo) as doc:
            for pagina in doc:
                texto_completo += pagina.get_text("text") + "\n"
    except Exception as exc:
        print(f"❌ Error leyendo PDF {path_archivo}: {exc}")
    return texto_completo


async def cargar_tesis_locales():
    directorio_tesis = ROOT / "app" / "backend" / "tesis_input"
    directorio_tesis.mkdir(parents=True, exist_ok=True)
    archivos = [f for f in os.listdir(directorio_tesis) if f.lower().endswith(".pdf")]
    if not archivos:
        print(f"ℹ️ No hay PDFs en {directorio_tesis}")
        return

    collection = get_collection()
    model = get_model()
    print(f"🚀 Iniciando ingesta V1.1 de {len(archivos)} tesis en '{collection.name}'...")

    for archivo in archivos:
        path = directorio_tesis / archivo
        contenido = extraer_texto_pdf(path)
        if not contenido.strip():
            print(f"⚠️ {archivo} no contiene texto extraíble.")
            continue
        chunks = sentence_chunks(contenido)
        print(f"📖 {archivo}: {len(chunks)} chunks")
        for idx, chunk in enumerate(chunks):
            embedding = model.encode(
                [chunk], normalize_embeddings=True, convert_to_numpy=True, show_progress_bar=False
            )[0].astype("float32").tolist()
            collection.upsert(
                ids=[f"{archivo}_{idx}"],
                embeddings=[embedding],
                documents=[chunk],
                metadatas=[{"source": archivo, "universidad": "Dominicana", "model": MODEL_NAME}],
            )
    print("✅ Ingesta V1.1 completada.")


if __name__ == "__main__":
    asyncio.run(cargar_tesis_locales())
