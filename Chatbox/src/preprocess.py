import pdfplumber
from pdf2image import convert_from_path
from PIL import Image
import re
import os
import pytesseract
pytesseract.pytesseract.tesseract_cmd = "poppler-24.08.0/Tesseract-OCR/tesseract.exe"
load
POPPLER_PATH = r"./poppler-24.08.0/Library/bin"  # Asegúrate de que esta ruta es correcta
# from db.database import create_database, insert_document, search_rnc, delete_database, list_documents  
text_data = []

def main(pdf_folder,filename):
    """Procesa los PDFs, extrae información clave y los almacena en SQLite."""
    # create_database()
    
    pdf_folder = "data"
    pdf_texts = extract_text_from_pdfs(pdf_folder,filename)

def extract_text_from_pdf(pdf_path):
    """Extrae texto de un PDF y usa OCR si es necesario."""
    
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    text_data.append(text)
        
        # Si no se extrajo ningún texto, usar OCR
        if not text_data:
            print(f"⚠️ OCR activado para {pdf_path}")
            images = convert_from_path(pdf_path, poppler_path=POPPLER_PATH)
            ocr_text = " ".join([pytesseract.image_to_string(img) for img in images])
            text_data.append(ocr_text)

        return  text_data
    
    except Exception as e:
        print(f"❌ Error al procesar {pdf_path}: {e}")
        return "(Error al procesar PDF)"




def extract_text_from_pdfs(pdf_path,filename):
    """Procesa todos los PDFs en una carpeta."""
    all_texts = {}
    text = extract_text_from_pdf(pdf_path,filename)
    all_texts[filename] = text
    return all_texts






def find_rnc_company_amount(text):
    """Busca el número de RNC, nombre de empresa y montos de dinero en el texto."""
    rnc_pattern = r"\bRNC\s*:\s*(\d+)\b"
    company_pattern = r"\bEmpresa\s*:\s*([\w\s]+)\b"
    amount_pattern = r"\b(?:RD\$|USD\$|US\$|€)\s*([\d,]+(?:\.\d{2})?)\b"

    rnc = re.findall(rnc_pattern, text)
    companies = re.findall(company_pattern, text)
    amounts = re.findall(amount_pattern, text)

    return rnc, companies, amounts
def find_rnc(text):
    """Busca el número de RNC en el texto."""
    rnc_pattern = r"\bRNC\s*:\s*(\d+)\b"
    rnc = re.findall(rnc_pattern, text)
    return rnc[0] if rnc else None
def find_company(text):
    """Busca el nombre de la empresa en el texto."""
    company_pattern = r"\bEmpresa\s*:\s*([\w\s]+)\b"
    companies = re.findall(company_pattern, text)
    return companies[0] if companies else None
def find_amount(text):
    """Busca montos de dinero en el texto."""
    amount_pattern = r"\b(?:RD\$|USD\$|US\$|€)\s*([\d,]+(?:\.\d{2})?)\b"
    amounts = re.findall(amount_pattern, text)
    return amounts[0] if amounts else None
def find_all(text): 
    """Busca RNC, nombre de empresa y montos de dinero en el texto."""
    rnc = find_rnc(text)
    company = find_company(text)
    amount = find_amount(text)
    return rnc, company, amount
import re

def find_rnc_values(text):
    """Extrae los números de RNC y los valores monetarios del texto."""
    rnc_pattern = r"\bRNC\s*:\s*(\d+)\b"
    amount_pattern = r"\b(?:RD\$|USD\$|US\$|€)\s*([\d,]+(?:\.\d{2})?)\b"

    rnc_numbers = re.findall(rnc_pattern, text)
    amounts = re.findall(amount_pattern, text)

    return list(zip(rnc_numbers, amounts))  # Asocia RNC con su monto

# Prueba con un texto de ejemplo
sample_text = """
Contrato firmado por la empresa XYZ. RNC: 123456789.
Monto total del contrato: USD$ 50,000.00
RNC: 987654321 con pago de RD$ 120,500.00.
"""
 
