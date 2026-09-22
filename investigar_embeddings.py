"""
INVESTIGACIÓN DE EMBEDDINGS EN CHROMADB
Determina qué modelo se usó para la ingesta actual.
"""

import sys
from pathlib import Path
import numpy as np

# Ajuste de path
raiz_proyecto = Path(__file__).resolve().parent
if str(raiz_proyecto) not in sys.path:
    sys.path.insert(0, str(raiz_proyecto))

try:
    __import__('pysqlite3')
    sys.modules['sqlite3'] = sys.modules.pop('pysqlite3')
except ImportError:
    print("⚠️ pysqlite3-binary no instalado")

import chromadb
from chatbox.db.database import get_chroma_client

def investigate_embeddings():
    """Investiga los embeddings almacenados en ChromaDB."""
    print("="*80)
    print("INVESTIGACIÓN DE EMBEDDINGS EN CHROMADB")
    print("="*80)
    
    client = get_chroma_client()
    collection = client.get_collection("tesis_universitarias")
    
    count = collection.count()
    print(f"\nTotal de documentos en ChromaDB: {count}")
    
    if count == 0:
        print("❌ La colección está vacía")
        return
    
    # Obtener sample de embeddings
    print("\nObteniendo sample de embeddings...")
    try:
        sample = collection.get(
            limit=5, 
            include=['embeddings', 'documents', 'metadatas']
        )
        
        print(f"\nSample de {len(sample['ids'])} documentos:")
        
        for i in range(len(sample['documents'])):
            print(f"\n--- Documento {i+1} ---")
            print(f"Source: {sample['metadatas'][i].get('source', 'N/A')}")
            print(f"Documento (primeros 150 chars): {sample['documents'][i][:150] if sample['documents'][i] else 'N/A'}...")
            
            if len(sample['embeddings']) > i and sample['embeddings'][i] is not None:
                embedding = np.array(sample['embeddings'][i])
                print(f"Embedding dimensión: {len(embedding)}")
                print(f"Embedding tipo: {type(embedding[0])}")
                print(f"Valores min/max: {embedding.min():.4f} / {embedding.max():.4f}")
                print(f"Norma L2: {np.linalg.norm(embedding):.4f}")
                print(f"Primeros 10 valores: {embedding[:10]}")
                
                # Intentar identificar el modelo por la dimensión
                dimension = len(embedding)
                print(f"\n🔍 Posible modelo según dimensión ({dimension}):")
                
                if dimension == 768:
                    print("   - paraphrase-multilingual-mpnet-base-v2 (768 dims) ✅")
                    print("   - all-mpnet-base-v2 (768 dims)")
                elif dimension == 384:
                    print("   - all-MiniLM-L6-v2 (384 dims)")
                    print("   - nomic-embed-text (384 dims) - si estuviera instalado")
                elif dimension == 512:
                    print("   - paraphrase-MiniLM-L6-v2 (512 dims)")
                else:
                    print(f"   - Desconocido (dimensión {dimension})")
            else:
                print("❌ No hay embedding para este documento")
    
    except Exception as e:
        print(f"❌ Error obteniendo sample: {e}")
    
    # Verificar si hay información de configuración
    print("\n" + "="*80)
    print("VERIFICACIÓN DE CONFIGURACIÓN DE COLECCIÓN")
    print("="*80)
    
    try:
        # ChromaDB no expone fácilmente la métrica usada, pero podemos inferir
        print("⚠️ ChromaDB no expone la métrica de distancia usada directamente")
        print("   Métricas comunes: cosine, euclidean, manhattan")
        print("   Por defecto: cosine similarity")
        
    except Exception as e:
        print(f"❌ Error verificando configuración: {e}")

def test_sentence_transformers():
    """Prueba si Sentence Transformers funciona."""
    print("\n" + "="*80)
    print("PRUEBA DE SENTENCE TRANSFORMERS")
    print("="*80)
    
    try:
        from sentence_transformers import SentenceTransformer
        
        model_name = 'paraphrase-multilingual-mpnet-base-v2'
        print(f"Cargando modelo: {model_name}")
        
        model = SentenceTransformer(model_name)
        print(f"✅ Modelo cargado exitosamente")
        
        test_text = "El cambio climático afecta la biodiversidad."
        embedding = model.encode(test_text)
        
        print(f"   Dimensión: {len(embedding)}")
        print(f"   Tipo: {type(embedding[0])}")
        print(f"   Norma L2: {np.linalg.norm(embedding):.4f}")
        print(f"   Primeros 10 valores: {embedding[:10]}")
        
        return embedding
        
    except Exception as e:
        print(f"❌ Error con Sentence Transformers: {e}")
        return None

def compare_embeddings():
    """Compara embeddings de ChromaDB con Sentence Transformers."""
    print("\n" + "="*80)
    print("COMPARACIÓN DE EMBEDDINGS")
    print("="*80)
    
    # Obtener embedding de ChromaDB
    client = get_chroma_client()
    collection = client.get_collection("tesis_universitarias")
    
    sample = collection.get(limit=1, include=['embeddings', 'documents', 'metadatas'])
    
    if len(sample['embeddings']) == 0 or sample['embeddings'][0] is None:
        print("❌ No hay embeddings en ChromaDB para comparar")
        return
    
    chroma_embedding = np.array(sample['embeddings'][0])
    print(f"Embedding de ChromaDB: dimensión {len(chroma_embedding)}")
    
    # Generar embedding con Sentence Transformers
    st_embedding = test_sentence_transformers()
    
    if st_embedding is not None:
        print(f"\nEmbedding de Sentence Transformers: dimensión {len(st_embedding)}")
        
        if len(chroma_embedding) == len(st_embedding):
            print("✅ LAS DIMENSIONES COINCIDEN")
            print("   → Probablemente ChromaDB usa Sentence Transformers")
        else:
            print("❌ LAS DIMENSIONES NO COINCIDEN")
            print(f"   → ChromaDB: {len(chroma_embedding)}, ST: {len(st_embedding)}")
            print("   → Los sistemas usan modelos diferentes")

if __name__ == "__main__":
    investigate_embeddings()
    compare_embeddings()