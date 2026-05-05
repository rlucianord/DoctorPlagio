import os
import sys
import asyncio
import fitz  # PyMuPDF
import httpx # <--- ESTA ES LA QUE FALTA
import json
from pathlib import Path

# 1. Ajuste de Path
raiz_proyecto = Path(__file__).resolve().parents[2]
if str(raiz_proyecto) not in sys.path:
    sys.path.insert(0, str(raiz_proyecto))

from chatbox.db.database import get_collection
# Asumiendo que get_embeddings está en backend.plagiarism
OLLAMA_BASE_URL="http://localhost:11434"
async def get_embeddings(text: str):
    """
    Genera el vector numérico (embedding) del texto usando Ollama.
    """
    # Limpiamos el texto para evitar errores de JSON
    clean_text = text.replace("\n", " ").strip()
    
    payload = {
        "model":"nomic-embed-text",
        "prompt": clean_text
    }
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            # Llamamos al endpoint de embeddings de Ollama
            response = await client.post(
                f"{OLLAMA_BASE_URL}/api/embeddings",
                json=payload
            )
            
            if response.status_code == 200:
                # Extraemos el vector de la respuesta
                return response.json().get("embedding")
            else:
                print(f"⚠️ Error de Ollama ({response.status_code}): {response.text}")
                return None
                
    except Exception as e:
        print(f"❌ Error de conexión con Ollama: {str(e)}")
        return None
 

async def analyze_plagiarism(document_content: str, db_session):
    """
    Integra la búsqueda semántica en ChromaDB con la detección de Ollama.
    """
    chroma_collection = get_chroma_client().get_collection("tesis_universitarias")
    fragments = [document_content[i:i+1000] for i in range(0, len(document_content), 1000)]
    
    plagiarism_results = []
    
    for frag in fragments:
        embedding = await get_embeddings(frag)
        if not embedding: continue

        # BUSQUEDA REAL: Consultamos ChromaDB por fragmentos similares
        results = chroma_collection.query(
            query_embeddings=[embedding],
            n_results=3
        )
        
        # Si la distancia es muy baja (alta similitud), lo marcamos
        for i, dist in enumerate(results['distances'][0]):
            if dist < 0.4: # Ajustar según el modelo de embedding
                plagiarism_results.append({
                    "fragment": frag[:150],
                    "source": results['metadatas'][0][i]['source'],
                    "similarity": 1 - dist
                })

    # Detección de IA con tu función actual
    ai_report = await detect_ai_text(document_content[:2000]) 
    
    return {
        "plagiarism_percentage": len(plagiarism_results) / len(fragments) * 100,
        "details": plagiarism_results,
        "ai_analysis": ai_report
    }

def extraer_texto_pdf(path_archivo):
    """Extrae todo el texto de un archivo PDF."""
    texto_completo = ""
    try:
        with fitz.open(path_archivo) as doc:
            for pagina in doc:
                texto_completo += pagina.get_text()
    except Exception as e:
        print(f"❌ Error leyendo PDF {path_archivo}: {e}")
    return texto_completo

async def cargar_tesis_locales():
    # Ruta absoluta: /home/theprofessor/DoctorPlagio/app/backend/tesis_input
    directorio_tesis = raiz_proyecto / "app" / "backend" / "tesis_input"
    
    if not directorio_tesis.exists():
        directorio_tesis.mkdir(parents=True, exist_ok=True)
        print(f"📁 Carpeta creada en {directorio_tesis}. Sube tus PDFs ahí.")
        return

    collection = get_collection("tesis_universitarias")
    
    # Filtramos archivos .pdf (ignorando mayúsculas/minúsculas)
    archivos = [f for f in os.listdir(directorio_tesis) if f.lower().endswith(".pdf")]
    
    if not archivos:
        print(f"ℹ️ No hay archivos .pdf en {directorio_tesis}")
        return

    print(f"🚀 Iniciando ingesta de {len(archivos)} tesis...")

    for archivo in archivos:
        path = directorio_tesis / archivo
        print(f"📖 Procesando PDF: {archivo}")
        
        # Extraemos el texto real del binario PDF
        contenido = extraer_texto_pdf(path)
        
        if not contenido.strip():
            print(f"⚠️ {archivo} parece estar vacío o ser solo imágenes.")
            continue

        # Segmentar en fragmentos de 1000 caracteres
        chunks = [contenido[i:i+1000] for i in range(0, len(contenido), 1000)]
        
        print(f"   - Generando {len(chunks)} vectores para {archivo}...")
        
        for idx, chunk in enumerate(chunks):
            # Tu lógica de embeddings vía Ollama
            embedding = await get_embeddings(chunk)
            if embedding:
                collection.add(
                    embeddings=[embedding],
                    documents=[chunk],
                    metadatas=[{"source": archivo, "universidad": "Dominicana"}],
                    ids=[f"{archivo}_{idx}"]
                )
                
    print("✅ Ingesta de PDFs completada con éxito.")

if __name__ == "__main__":
    asyncio.run(cargar_tesis_locales())