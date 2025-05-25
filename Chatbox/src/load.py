from datasets import load_dataset
from sentence_transformers import SentenceTransformer
# __import__('pysqlite3')
import sys
from PIL import Image
# sys.modules['sqlite3'] = sys.modules.pop('pysqlite3')
from chromadb import Client 
from chromadb.config import Settings
 
from chromadb.utils import embedding_functions
from PyPDF2 import PdfReader
import os,re,shutil,chromadb,pickle,glob,pytesseract,pdf2image,cv2,ocrmypdf
from sentence_transformers import SentenceTransformer
from pdf2image import convert_from_path
import pymupdf,fitz
from transformers import AutoModelForCausalLM, AutoTokenizer, TrainingArguments, Trainer,AutoModelForMaskedLM
from datasets import Dataset
import pytesseract

# pytesseract.pytesseract.tesseract_cmd = r"./poppler-24.08.0/Tesseract-OCR/tesseract.exe" 
OPPLER_PATH = r"./poppler-24.08.0/Library/bin"  # Asegúrate de que esta ruta es correct


lista_textos = []
#AIzaSyBg0e7H81UZDs-U-f6-bWXnWOiNQquD5C8
hf_token = "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"

modelo_embeddings = SentenceTransformer('paraphrase-multilingual-mpnet-base-v2')

pytesseract.pytesseract.tesseract_cmd = "poppler-24.08.0/Tesseract-OCR/tesseract.exe"
POPPLER_PATH = r"./poppler-24.08.0/Library/bin"  # Asegúrate de que esta ruta es correcta
# from db.database import create_database, insert_document, search_rnc, delete_database, list_documents  
nombre_coleccion = "mis_documentos_pdf"
ruta_persistencia_chroma = os.path.join("data", "chroma_db")
cliente_chroma = chromadb.PersistentClient(path=ruta_persistencia_chroma)
coleccion_chroma = cliente_chroma.get_or_create_collection(nombre_coleccion)




def clean_text(text):
    """Limpia el texto eliminando espacios innecesarios y caracteres especiales."""
    text = text.lower()
    text = re.sub(r'\s+', ' ', text)
    return text

def cargar_pdfs(filelist,rnc=None,datadir="data/pdfs"):
   
    """Carga el texto de todos los archivos PDF en una carpeta."""
    textos = []
    nombres_archivos = []
    nombre_archivo=None
    data_a_guardar = {}
    n=1
    for file in filelist:    
        nombre_archivo = file
        if file:
            proceso= os.path.dirname(file).split('\\')[-1]
            if( "data" not  in file):
                archivo =  f"{proceso}-{rnc}-{os.path.basename( file)}"
                nombre_archivo = f"{datadir}/{archivo}"
            nombre_archivo= nombre_archivo.replace(" ", "_")
            if(os.path.exists(nombre_archivo)or rnc is None ):
                print(f"Archivo ya existe: {nombre_archivo}")
                
            else: 
                shutil.copy( file,nombre_archivo)
                print(f"Archivo copiado: {nombre_archivo}")

            try:
                with pymupdf.open(nombre_archivo) as lector_pdf:
                    
                    texto_pagina = ""
                    for pagina in  lector_pdf:
                       
                        texto_pagina += clean_text(pagina.get_text("text"))

                        if texto_pagina:
                            textos.append(texto_pagina)
                            nombres_archivos.append(nombre_archivo)
                        if not textos:
                            print(f"⚠️ OCR activado para {archivo_pdf}")
                            images = convert_from_path(file, poppler_path=POPPLER_PATH)
                            texto_pagina = " ".join([pytesseract.image_to_string(img) for img in images])
                            texto_pagina = clean_text(texto_pagina)
                            textos.append(texto_pagina)
                    
            except FileNotFoundError:
                print(f"Archivo no encontrado: {nombre_archivo}")            

            except Exception as e:
                print(f"Error al leer {nombre_archivo}: {e}")
   
    
    
    crear_dataset(textos)
    main(textos)
    return textos, nombres_archivos,data_a_guardar



def just_extract_text(pdf_path):
    """Extrae texto de un PDF y usa OCR si es necesario."""
    
    
    for pdf_file in pdf_path:
        
            pdf_document = fitz.open(pdf_file)
            text=""            
            try:        
                for page_num in range((pdf_document.page_count)):
                    page=pdf_document.load_page(page_num)
                    text = text.join(page.get_text())
                    page_num +=1
               
                if text:
                    lista_textos .append(text)
                else:
                        
                    print(f"⚠️ OCR activado para {pdf_file}")
#                     page = pdf_document.load_page(page_number)

#                     # Get images on the page
#                     image_list = page.get_images(full=True)
#                     print(f'Found {len(image_list)} images on page {page_number + 1}.')

# # Process each image
#                     for img_index, img in enumerate(image_list, start=1):
#                         xref = img[0]
#                         base_image = pdf_document.extract_image(xref)
#                         image_bytes = base_image["image"]
#                         tt= pymupdf.open("pdf", image_bytes)
#                         for paget in tt.pages:
#                             texto=paget.get_text()
                                            # lista_textos.append(texto_pagina)
                print(f"⚠️ Completado {pdf_file}")
                pdf_document.close()          
            except Exception as e:
                print(f"❌ Error al procesar {pdf_file}: {e}")
                continue            
                   

    return  lista_textos
    

   





def crear_dataset(lista_textos):
    """Crea un dataset de Hugging Face a partir de una lista de textos."""
    raw_datasets = Dataset.from_list([{"text": t} for t in lista_textos])
    return raw_datasets

def tokenizar_dataset(dataset, tokenizer):
    """Tokeniza un dataset de texto y crea las etiquetas para el modelo causal."""
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    def tokenize_function(examples):
        tokenized_inputs = tokenizer(examples["text"], truncation=True, padding="max_length", max_length=512)
        # Crear etiquetas: desplazar los input_ids un paso a la derecha
        labels = tokenized_inputs["input_ids"][:]
        # Para que el modelo ignore los tokens de padding en la pérdida
        labels = [[-100 if token == tokenizer.pad_token_id else token for token in label] for label in labels]
        tokenized_inputs["labels"] = labels
        return tokenized_inputs

    tokenized_datasets = dataset.map(tokenize_function, batched=True)
    return tokenized_datasets


def entrenar_modelo(modelo, tokenized_datasets, training_args, tokenizer):
    """Entrena (fine-tune) el modelo."""
    trainer = Trainer(
        model=modelo,
        args=training_args,
        train_dataset=tokenized_datasets,
        tokenizer=tokenizer,
    )
    trainer.train()
    return trainer

def guardar_modelo_entrenado(trainer, ruta_guardado):
    """Guarda el modelo y el tokenizer entrenados."""
    trainer.save_model(ruta_guardado)
    trainer.tokenizer.save_pretrained(ruta_guardado)
    print(f"Modelo y tokenizer guardados en {ruta_guardado}")
def finaltrain(files):
    
    textos=just_extract_text(files)
    crear_dataset(textos)
    modelo_nombre ="EleutherAI/pythia-410m"  # "unsloth/claude-3.7-sonnet-reasoning-gemma3-12B"#unsloth/gemma-3-4b-it-bnb-4bit-- google/gemma-7b-it"  # Nombre del modelo preentrenado
    ruta_guardado_modelo = "data/modelo_fine_tuned_pythia"  # Ruta donde se guardará el modelo fine-tuneado
    ruta_checkpoint = f"{ruta_guardado_modelo}/checkpoint-01000"
    num_epochs = 3
    batch_size = 4

    # 1. Cargar textos desde los PDFs

    if not textos:
        print("No se encontraron textos para entrenar.")
        exit()

    # 2. Crear el dataset
    raw_datasets = crear_dataset(textos)
    if os.path.exists(ruta_checkpoint):    
        modelo = AutoModelForCausalLM.from_pretrained(ruta_checkpoint)
    else:
        # 3. Cargar el modelo y el tokenizer
        modelo = AutoModelForCausalLM.from_pretrained(modelo_nombre,device_map="auto")
        #modelo.resize_token_embeddings(len(tokenizer))
    tokenizer = AutoTokenizer.from_pretrained(modelo_nombre,token=hf_token)
    # tokenizer = AutoTokenizer.from_pretrained("distilbert/distilbert-base-uncased")
    # model = AutoModelForMaskedLM.from_pretrained("distilbert/distilbert-base-uncased")
    


    # 4. Tokenizar el dataset
    tokenized_datasets = tokenizar_dataset(raw_datasets, tokenizer)

    # 5. Configurar los argumentos de entrenamiento
    training_args = TrainingArguments(
        output_dir= ruta_guardado_modelo, 
        overwrite_output_dir=True,
        num_train_epochs=num_epochs,
        per_device_train_batch_size=batch_size,
        save_steps=10_000,
        save_total_limit=2,
        # Very low batch size for CPU
        gradient_accumulation_steps=8, # Accumulate gradients
    )

    # 6. Entrenar el modelo
    trainer = entrenar_modelo(modelo, tokenized_datasets, training_args, tokenizer)

    # 7. Guardar el modelo entrenado
    guardar_modelo_entrenado(trainer, ruta_guardado_modelo)##ruta_checkpoint
    guardar_modelo_entrenado(trainer, ruta_checkpoint)##ruta_checkpoint
    

    print("Proceso de fine-tuning completado.")   
    
    
if __name__ == "__main__":
    # cd= './poppler-24.08.0/Library/bin'
    # ps= os.environ['PATH'] + cd
    # #ps= os.environ['PATH'] + cd    
    # os.environ['PATH'] = ps
    #
    cd='./'
    files=glob.glob(f"{cd}/**/*.pdf", recursive=True)[:10]
       
    finaltrain(files)



