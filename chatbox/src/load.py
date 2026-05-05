import os
import re
import shutil
import glob
import sys
import pickle
import cv2
import chromadb
import pytesseract
import pymupdf
import fitz # Alias de pymupdf
from PIL import Image
from pdf2image import convert_from_path
from sentence_transformers import SentenceTransformer
from datasets import Dataset
from transformers import (
    AutoModelForCausalLM, 
    AutoTokenizer, 
    TrainingArguments, 
    Trainer
)

# --- PARCHE PARA CHROMADB EN LINUX ---
try:
    __import__('pysqlite3')
    sys.modules['sqlite3'] = sys.modules.pop('pysqlite3')
except ImportError:
    pass

# --- CONFIGURACIÓN DE RUTAS (Actualizado para Linux) ---
# Ya no usamos .exe, usamos los binarios del sistema instalados via apt
hf_token = "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"
nombre_coleccion = "mis_documentos_pdf"
ruta_persistencia_chroma = os.path.join("data", "chroma_db")

# Inicialización de clientes
cliente_chroma = chromadb.PersistentClient(path=ruta_persistencia_chroma)
coleccion_chroma = cliente_chroma.get_or_create_collection(nombre_coleccion)
modelo_embeddings = SentenceTransformer('paraphrase-multilingual-mpnet-base-v2')

lista_textos = []

def clean_text(text):
    """Limpia el texto eliminando espacios innecesarios y caracteres especiales."""
    if not text: return ""
    text = text.lower()
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

def just_extract_text(pdf_path):
    """Extrae texto de un PDF y usa OCR si es necesario (Fallback robusto)."""
    global lista_textos
    for pdf_file in pdf_path:
        try:
            # Plan A: PyMuPDF (fitz)
            pdf_document = fitz.open(pdf_file)
            text = ""            
            for page_num in range(pdf_document.page_count):
                page = pdf_document.load_page(page_num)
                text += page.get_text()
            
            # Plan B: OCR si no hay texto extraído
            if not text.strip():
                print(f"⚠️ OCR activado para {pdf_file}")
                # En Ubuntu, convert_from_path usa el poppler del sistema
                images = convert_from_path(pdf_file)
                text = " ".join([pytesseract.image_to_string(img) for img in images])
            
            if text.strip():
                lista_textos.append(text)
                print(f"✅ Completado {pdf_file}")
            
            pdf_document.close()          
        except Exception as e:
            print(f"❌ Error al procesar {pdf_file}: {e}")
            continue            
    return lista_textos

def crear_dataset(textos):
    """Crea un dataset de Hugging Face."""
    return Dataset.from_list([{"text": t} for t in textos])

def tokenizar_dataset(dataset, tokenizer):
    """Tokeniza con labels para entrenamiento causal."""
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    def tokenize_function(examples):
        tokenized_inputs = tokenizer(
            examples["text"], 
            truncation=True, 
            padding="max_length", 
            max_length=512
        )
        labels = tokenized_inputs["input_ids"].copy()
        # Ignorar tokens de padding en el cálculo de pérdida (-100)
        labels = [[-100 if token == tokenizer.pad_token_id else token for token in label] for label in labels]
        tokenized_inputs["labels"] = labels
        return tokenized_inputs

    return dataset.map(tokenize_function, batched=True)

def finaltrain(files):
    textos = just_extract_text(files)
    
    if not textos:
        print("No se encontraron textos para entrenar.")
        return

    raw_datasets = crear_dataset(textos)
    modelo_nombre = "EleutherAI/pythia-410m"
    ruta_guardado_modelo = "data/modelo_fine_tuned_pythia"
    ruta_checkpoint = f"{ruta_guardado_modelo}/checkpoint-01000"
    
    # Parámetros ajustados para tu Latitude (CPU/RAM friendly)
    num_epochs = 3
    batch_size = 1 # Reducido para evitar OOM (Out of Memory)
    grad_steps = 8

    tokenizer = AutoTokenizer.from_pretrained(modelo_nombre, token=hf_token)
    
    if os.path.exists(ruta_checkpoint):    
        print(f"Cargando desde checkpoint: {ruta_checkpoint}")
        modelo = AutoModelForCausalLM.from_pretrained(ruta_checkpoint)
    else:
        print(f"Cargando modelo base: {modelo_nombre}")
        modelo = AutoModelForCausalLM.from_pretrained(modelo_nombre)

    tokenized_datasets = tokenizar_dataset(raw_datasets, tokenizer)

    training_args = TrainingArguments(
        output_dir=ruta_guardado_modelo, 
        overwrite_output_dir=True,
        num_train_epochs=num_epochs,
        per_device_train_batch_size=batch_size,
        gradient_accumulation_steps=grad_steps,
        save_steps=500,
        save_total_limit=2,
        logging_steps=100,
        report_to="none"
    )

    trainer = Trainer(
        model=modelo,
        args=training_args,
        train_dataset=tokenized_datasets,
        tokenizer=tokenizer,
    )

    print("🚀 Iniciando entrenamiento...")
    trainer.train()
    
    trainer.save_model(ruta_guardado_modelo)
    tokenizer.save_pretrained(ruta_guardado_modelo)
    print(f"✅ Proceso completado. Modelo guardado en {ruta_guardado_modelo}")

if __name__ == "__main__":
    # Buscar los primeros 10 PDFs en el proyecto
    files = glob.glob("./**/*.pdf", recursive=True)[:10]
    finaltrain(files)