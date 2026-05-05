import os
from pathlib import Path
import sys
import httpx
import json
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np
import asyncio
from transformers import pipeline

path_actual = Path(__file__).resolve()
raiz_proyecto = path_actual.parents[2] 

if str(raiz_proyecto) not in sys.path:
    sys.path.insert(0, str(raiz_proyecto))
from chatbox.db.database import get_chroma_client # Asegúrate de que este import exista
from backend.config import OLLAMA_BASE_URL, OLLAMA_MODEL
import torch
__import__('pysqlite3')
sys.modules['sqlite3'] = sys.modules.pop('pysqlite3')
# Este import ya debería funcionar al tener la raíz en sys.path

print("Cargando modelo académico de Hugging Face...")
# detector_pipe = pipeline(
#     "text-classification", 
#     model="roberta-base-openai-detector",
#     device=-1 # Usa -1 para CPU (HP Mini) o 0 si tuvieras GPU
# )
 #from transformers import pipeline

#pipe = pipeline("fill-mask", model="egumasa/roberta-base-academic")

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
async def detect_ai_text(text: str):
    """
    Llama a Ollama con el prompt académico validado y asegura el retorno del label.
    """
    OLLAMA_URL = "http://localhost:11434/api/generate"
    OLLAMA_MODEL = "llama3" 
    truncated_text = text[:1500] 
    
    # RESTAURADO: El prompt con todas las instrucciones académicas y técnicas
    prompt = f"""
    [SISTEMA: ANALISTA DE LINGÜÍSTICA FORENSE ACADÉMICA]
    Analiza el siguiente fragmento de una tesis universitaria. Tu objetivo es diferenciar entre redacción formal humana y generación sintética.

    CONSIDERACIONES TÉCNICAS:
    1. El texto académico es naturalmente estructurado y formal; NO clasifiques esto como IA por defecto.
    2. Busca "estallidos" (variación en la longitud de oraciones) y "perplejidad" (elección de palabras no lineales).
    3. La IA tiende a ser demasiado equilibrada; el humano, incluso en tesis, tiene matices de estilo únicos.
    4. El texto formal es parte del trabajo de un humano, no puedes tomarlo como fraude, pero busca lo que sea particularmente hecho por IA y sin mejorar.

    REGLAS DE RESPUESTA:
    - ai_score: 0.0 (Humano Puro) a 1.0 (IA Pura).
    - Si el texto es una tesis legítima muy bien escrita, el score debe estar entre 0.05 y 0.20.

    RESPONDE ÚNICAMENTE EN JSON:
    {{
      "ai_score": float,
      "label": "string",
      "reasoning": "string"
    }}

    TEXTO:
    {truncated_text}
    """

    fallback_response = {
        "ai_score": 0.0, 
        "human_score": 1.0, 
        "label": "Human-written", 
        "reasoning": "Error de respaldo o análisis por defecto"
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(OLLAMA_URL, json={
                "model": OLLAMA_MODEL, 
                "prompt": prompt,
                "stream": False,
                "format": "json"
            })
            
            if response.status_code == 200:
                raw_result = response.json()
                try:
                    ai_data = json.loads(raw_result['response'])
                    
                    # 1. Extraemos el score del modelo
                    score = float(ai_data.get("ai_score", 0.0))
                    
                    # 2. Reconstruimos el objeto para asegurar que el frontend reciba TODO
                    return {
                        "ai_score": round(score, 4),
                        "human_score": round(1.0 - score, 4),
                        "label": "AI-generated" if score > 0.5 else "Human-written",
                        "reasoning": ai_data.get("reasoning", "Análisis completado")
                    }
                except (json.JSONDecodeError, KeyError):
                    return fallback_response
            
            return fallback_response
            
    except Exception as e:
        print(f"⚠️ Error: {str(e)}")
        return fallback_responsexe

async def detect_ai_text_hf(text: str):
    # Definimos un tamaño de ventana y un solapamiento (stride)
    max_length = 1500  # Caracteres aprox para ~512 tokens
    stride = 300       # 300 caracteres de solapamiento para no perder el hilo
    
    parts = []
    # Creamos ventanas que se solapan entre sí
    for i in range(0, len(text), max_length - stride):
        parts.append(text[i : i + max_length])
        if i + max_length >= len(text):
            break

    all_scores = []
    
    try:
        # Analizamos cada parte y promediamos
        for part in parts:
            if len(part.strip()) < 100: continue # Ignoramos fragmentos muy cortos
            
            result = detector_pipe(part)[0]
            label = result['label']
            confianza = result['score']
            
            # Mapeo de score
            current_ai_score = confianza if (label == 'Label_1' or label.upper() == 'AI') else (1.0 - confianza)
            all_scores.append(current_ai_score)

        # PROMEDIO PONDERADO: Da un resultado mucho más estable que un solo chunk
        final_ai_score = sum(all_scores) / len(all_scores) if all_scores else 0.0
        
        # AJUSTE DE SENSIBILIDAD: Si es una tesis académica humana, 
        # aplicamos una pequeña reducción de ruido (bias)
        if final_ai_score < 0.6:
            final_ai_score *= 0.85 # Factor de "Indulgencia Académica"

        return {
            "ai_score": round(final_ai_score, 4),
            "human_score": round(1.0 - final_ai_score, 4),
            "label": "AI-generated" if final_ai_score > 0.5 else "Human-written"
        }
    except Exception as e:
        print(f"❌ Error interno en analyze_plagiarism: {str(e)}")
        raise e # Re-lanzamos para que el 500 muestre el rastro en consola     
async def analyze_plagiarism(document_content: str, db_session):
    try:
        # 1. Obtener colección (Validación de seguridad)
        client = get_chroma_client()
        chroma_collection = client.get_collection("tesis_universitarias")
        
        # 2. Segmentación (Chunks)[cite: 2]
        fragments = [document_content[i:i+1000] for i in range(0, len(document_content), 1000)]
        plagiarism_results = []
        
        if not fragments:
            return {"plagiarism_percentage": 0, "details": [], "ai_analysis": {}}

        for frag in fragments:
            embedding = await get_embeddings(frag)
            if not embedding: continue

            # 3. Consulta a ChromaDB[cite: 2]
            results = chroma_collection.query(
                query_embeddings=[embedding],
                n_results=3
            )
            
            # 4. Cálculo de distancias[cite: 2]
            if results and 'distances' in results and len(results['distances']) > 0:
                for i, dist in enumerate(results['distances'][0]):
                    dist_factor=dist/100
                    if dist_factor < 0.8: # Umbral de similitud[cite: 2]
                        plagiarism_results.append({
                            "fragment": frag[:150],
                            "source": results['metadatas'][0][i]['source'],
                            "similarity": round(1 - dist, 4)
                        })

        # 5. Detección de IA[cite: 2]
        ai_report = await detect_ai_text(document_content[:2000]) 
        
        # 6. Cálculo final (Evitar división por cero)
        total_frags = len(fragments)
        percentage = (len(plagiarism_results) / total_frags * 100) if total_frags > 0 else 0
        procentaje100=percentage/total_frags
        resultado_final = {
        "plagiarism_percentage": round(procentaje100, 2),
        "details": plagiarism_results, # Aquí 'plagiarism_results' debe ser la lista de fragmentos detectados
        "ai_analysis": ai_report
        }
        return resultado_final    
    except Exception as e:
        print(f"❌ Error interno en analyze_plagiarism: {str(e)}")
        raise e # Re-lanzamos para que el 500 muestre el rastro en consola   