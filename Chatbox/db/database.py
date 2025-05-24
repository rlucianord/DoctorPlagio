import sqlite3
import os

DB_PATH = "Dataset.db"

def create_database():
    """Crea la base de datos y la tabla si no existen."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS documents (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        filename TEXT,
        text TEXT,
        rnc TEXT, 
         companies TEXT,
         amounts real,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    
    conn.commit()
    conn.close()

def insert_document(filename, text, rnc, companies, amounts):
    """Inserta un documento en la base de datos."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("INSERT INTO documents (filename, text) VALUES (?, ?)", (filename, text))
    
    conn.commit()
    conn.close()

def search_text(query):
    """Busca documentos que contienen una palabra clave."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("SELECT filename, text FROM documents WHERE text LIKE ?", ('%' + query + '%',))
    results = cursor.fetchall()
    
    conn.close()
    return results
def delete_database():
    """Elimina la base de datos si existe."""
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
        print(f"Base de datos {DB_PATH} eliminada.")
    else:
        print("La base de datos no existe.")

# def delete_document(filename):
#     """Elimina un documento específico de la base de datos."""
#     conn = sqlite3.connect(DB_PATH)
#     cursor = conn.cursor()
    
#     cursor.execute("DELETE FROM documents WHERE filename = ?", (filename,))
    
#     conn.commit()
#     conn.close()
def list_documents():
    """Lista todos los documentos en la base de datos."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("SELECT text FROM documents")
    results = cursor.fetchall()
    
    conn.close()
    return [filename for (filename,) in results]
def search_rnc(rnc):
    """Busca documentos que contienen un RNC específico."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("SELECT filename, text FROM documents WHERE text LIKE ?", ('%' + rnc + '%',))
    results = cursor.fetchall()
    
    conn.close()
    return results
