import httpx
import json
import sys
from pathlib import Path
sys.path[0] = str(Path(sys.path[0]).parent)
print(sys.path[1])

from backend.config import OLLAMA_BASE_URL, OLLAMA_MODEL
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np

async def get_embeddings(text: str, model=OLLAMA_MODEL,response_model="None"):
    url = f"{OLLAMA_BASE_URL}/api/embeddings"
    data = {
        "model": model,
        "prompt": text
    }
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(url, json=data, timeout=10)
            response.raise_for_status()
            return response.json()["embedding"]
        except httpx.HTTPError as e:
            print(f"Error al obtener embeddings de Ollama: {e}")
            return None

async def ask_ollama(prompt: str, model=OLLAMA_MODEL, response_model="None"):
    url = f"{OLLAMA_BASE_URL}/api/chat"
    data = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}]
    }
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(url, json=data, timeout=20)
            response.raise_for_status()
            return response.json()["message"]["content"]
        except httpx.HTTPError as e:
            print(f"Error al preguntar a Ollama: {e}")
            return None

async def detect_ai_text(text: str,response_model="None"):
    prompt = f"¿El siguiente texto parece haber sido generado por una inteligencia artificial?\n\n{text}\n\nResponde 'sí' o 'no' y explica brevemente por qué."
    response = await ask_ollama(prompt)
    return response

async def analyze_plagiarism(document_content: str, db,response_model="None"):
    # Simulación de una base de datos de referencia (aquí deberías tener acceso a documentos reales)
    # Por ahora, compararemos fragmentos del mismo documento para demostrar la lógica
    fragments = [document_content[i:i+500] for i in range(0, len(document_content), 500)]
    plagiarism_details = []
    total_plagiarized_length = 0

    for i, frag1 in enumerate(fragments):
        embedding1 = await get_embeddings(frag1)
        if embedding1:
            for j, frag2 in enumerate(fragments):
                if i != j: # No comparar el fragmento consigo mismo
                    embedding2 = await get_embeddings(frag2)
                    if embedding2:
                        similarity = cosine_similarity([embedding1], [embedding2])[0][0]
                        if similarity > 0.85: # Umbral de similitud (ajustar)
                            plagiarism_details.append({
                                "fragment": frag1[:100] + "...",
                                "compared_with": frag2[:100] + "...",
                                "similarity": float(similarity)
                            })
                            total_plagiarized_length += len(frag1)
            ai_detection_result = await detect_ai_text(frag1)
            print(f"Fragmento: {frag1[:50]}..., Detección IA: {ai_detection_result}")

    plagiarism_percentage = (total_plagiarized_length / len(document_content)) * 100 if document_content else 0
    ai_detection_percentage = 50 # Esto es un placeholder, la detección real sería más compleja

    return {
        "plagiarism_percentage_text": int(plagiarism_percentage),
        "plagiarism_details_text": json.dumps(plagiarism_details),
        "ai_detection_percentage": int(ai_detection_percentage),
        "ai_detection_details": "Detalles de la detección de IA irían aquí."
    }