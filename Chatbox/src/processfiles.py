import os
import csv
import glob
__import__('pysqlite3')
import sys
sys.modules['sqlite3'] = sys.modules.pop('pysqlite3')

import chromadb
import pymupdf
import load
import pickle
from sentence_transformers import SentenceTransformer
import fitz  # PyMuPDF for PDF processing

directory_path = './data/pdfs'
pdfdirectory = os.path.join("./data/pdfs")  
data_a_guardar = {}
textos, nombres_archivos = [], []

def copyfiles(directory):
    """Recorre un directorio y carga los archivos PDF en una lista."""     
    for  root,dirs, files in  os.walk(directory) :  
        newdirs=dirs[1:3]
    
         
        for dirs1 in newdirs:
            rnc=dirs1.split('-')[1]
            nextdir=root+'\\'+dirs1
            files=glob.glob(f"{nextdir}/**/*", recursive=True)[3:]
            files = [f for f in files if os.path.isfile(f)]
            textos1, nombres_archivos1,data_a_guardar1=load.finaltrain(files,rnc,pdfdirectory)
            textos.extend(textos1)
            nombres_archivos.extend(nombres_archivos1)
            data_a_guardar.update(data_a_guardar1)
            embeddings= crear_embeddings(nombres_archivos)
            guardar_embeddings(embeddings, list(nombres_archivos))
  
def crear_embeddings(documentos):
    """Crea embeddings usando Sentence Transformers."""
    modelo_embeddings = SentenceTransformer('paraphrase-multilingual-mpnet-base-v2')
    embeddings = modelo_embeddings.encode(documentos)
    return embeddings

def guardar_embeddings(embeddings, nombres_archivos, ruta_archivo="embeddings_pdf.pkl"):
    """Guarda los embeddings y los nombres de los archivos en un archivo."""
    ruta_guardado_embeddings = os.path.join("data", ruta_archivo)
    data_a_guardar = {"embeddings": embeddings, "archivos_procesados": nombres_archivos}
    with open(ruta_guardado_embeddings, 'wb') as f:
        pickle.dump(data_a_guardar, f)
    print(f"Embeddings y archivos procesados guardados en {ruta_guardado_embeddings}")


def cargar_embeddings_documentos_chroma(ruta_documentos="documentos_pdf.pkl", ruta_embeddings="embeddings_pdf.pkl", ruta_persistencia="chroma_db", nombre_coleccion="mis_documentos"):
    ruta_persistencia_chroma = os.path.join("data", ruta_persistencia)
    ruta_documentos = os.path.join(ruta_persistencia_chroma, ruta_documentos)
    documentos = None
    embeddings = None
    nombre_coleccion = "mis_documentos_pdf"

    # Cargar documentos
    try:
        with open(ruta_documentos, 'rb') as f:
            documentos = pickle.load(f)
    except FileNotFoundError:
        print(f"Error: No se encontró el archivo de documentos en {ruta_documentos}.")

    # Cargar embeddings
    try:
        with open(ruta_embeddings, 'rb') as f:
            embeddings = pickle.load(f)
    except FileNotFoundError:
        print(f"Error: No se encontró el archivo de embeddings en {ruta_embeddings}.")

    # Inicializar ChromaDB
    cliente = chromadb.PersistentClient(path=ruta_persistencia)
    coleccion = cliente.get_or_create_collection(nombre_coleccion)

    return documentos, embeddings, coleccion

if __name__ == "__main__":
    # Cambia el directorio a la ruta deseada
    copyfiles(directory_path)
    