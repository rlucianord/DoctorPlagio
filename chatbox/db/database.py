# chatbox/db/database.py
import os
from pathlib import Path

# --- PARCHE OBLIGATORIO PARA CHROMADB ---
try:
    __import__('pysqlite3')
    import sys
    sys.modules['sqlite3'] = sys.modules.pop('pysqlite3')
except ImportError:
    print("⚠️ pysqlite3-binary no instalado. Usando sqlite3 del sistema.")

import chromadb
from chromadb.config import Settings

# Definimos la ruta de persistencia (Donde se guardarán tus tesis)
DB_PATH = os.path.join(os.path.dirname(__file__), "chroma_data")

def get_chroma_client():
    """
    Retorna un cliente persistente de ChromaDB.
    """
    return chromadb.PersistentClient(path=DB_PATH)

def get_collection(collection_name="tesis_universitarias"):
    """
    Obtiene o crea la colección de tesis.
    """
    client = get_chroma_client()
    return client.get_or_create_collection(name=collection_name)