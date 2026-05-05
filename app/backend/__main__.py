# from setuptools import setup, find_packages

# setup(name='backend', packages=find_packages())
# app/backend/main.py
from flask import Flask, request, jsonify
from chatbox.src.agency import create_agency
from chatbox.src.processfiles import process_pdf # Tu script de PyMuPDF

app = Flask(__name__)
agency = create_agency()

@app.route('/upload', methods=['POST'])
def handle_upload():
    file = request.files['file']
    if file:
        path = f"data/uploads/{file.filename}"
        file.save(path)
        
        # 1. Extraer texto del PDF
        text = process_pdf(path)
        
        # 2. La Agencia toma el mando
        # El agente TechnicalAgent usará la PlagiarismTool automáticamente
        verdict = agency.get_completion(f"Analiza esta tesis: {text[:3000]}")
        
        return jsonify({"veredicto": verdict})