"""
DOCTORPLAGIO - DIAGNÓSTICO ACTUAL DEL SISTEMA
Script exclusivamente de lectura/análisis. NO modifica archivos, bases de datos o configuraciones.
"""

import sys
import os
import re
import ast
import inspect
import tempfile
import shutil
from pathlib import Path
from datetime import datetime
import importlib.util

# Configuración de paths
RAIZ_PROYECTO = Path(__file__).resolve().parent
if str(RAIZ_PROYECTO) not in sys.path:
    sys.path.insert(0, str(RAIZ_PROYECTO))

class DiagnosticAnalyzer:
    """Analizador del sistema actual sin modificar nada."""
    
    def __init__(self):
        self.config = {}
        self.pipeline = {}
        self.chunking = {}
        self.embeddings = {}
        self.chromadb = {}
        self.search = {}
        self.scoring = {}
        self.problems = []
        self.warnings = []
        self.ok = []
        
    def print_separator(self, title):
        print("\n" + "="*80)
        print(f"  {title}")
        print("="*80)
    
    def analyze_configuration(self):
        """Analiza la configuración actual del sistema."""
        self.print_separator("[1] CONFIGURACIÓN")
        
        # Analizar config.py
        config_file = RAIZ_PROYECTO / "app" / "backend" / "config.py"
        if config_file.exists():
            print(f"✅ Archivo de configuración encontrado: {config_file}")
            with open(config_file, 'r', encoding='utf-8') as f:
                content = f.read()
                
            # Extraer configuraciones
            db_url_match = re.search(r'DATABASE_URL\s*=\s*["\']([^"\']+)["\']', content)
            ollama_url_match = re.search(r'OLLAMA_BASE_URL\s*=\s*["\']([^"\']+)["\']', content)
            ollama_model_match = re.search(r'OLLAMA_MODEL\s*=\s*["\']([^"\']+)["\']', content)
            
            if db_url_match:
                self.config['database_url'] = db_url_match.group(1)
                print(f"   Database URL: {self.config['database_url']}")
            if ollama_url_match:
                self.config['ollama_base_url'] = ollama_url_match.group(1)
                print(f"   Ollama Base URL: {self.config['ollama_base_url']}")
            if ollama_model_match:
                self.config['ollama_model'] = ollama_model_match.group(1)
                print(f"   Ollama Model: {self.config['ollama_model']}")
        else:
            print(f"⚠️ Archivo de configuración no encontrado: {config_file}")
            self.warnings.append("Archivo config.py no encontrado")
        
        # Analizar requirements.txt
        req_file = RAIZ_PROYECTO / "requirements.txt"
        if req_file.exists():
            print(f"\n✅ Requirements.txt encontrado")
            with open(req_file, 'r', encoding='utf-8') as f:
                requirements = [line.strip() for line in f if line.strip() and not line.startswith('#')]
            
            sentence_transformers_match = [r for r in requirements if 'sentence-transformers' in r.lower()]
            chromadb_match = [r for r in requirements if 'chromadb' in r.lower()]
            
            if sentence_transformers_match:
                print(f"   Sentence Transformers: {sentence_transformers_match[0]}")
                self.config['sentence_transformers'] = sentence_transformers_match[0]
            if chromadb_match:
                print(f"   ChromaDB: {chromadb_match[0]}")
                self.config['chromadb'] = chromadb_match[0]
        
        # Buscar modelos de Sentence Transformers en el código
        print(f"\n🔍 Buscando modelos de Sentence Transformers en el código...")
        st_models = set()
        ollama_models = set()  # Inicializar antes del uso
        
        for py_file in RAIZ_PROYECTO.rglob("*.py"):
            if '.venv' in str(py_file) or 'Python-3.12.3' in str(py_file):
                continue
            try:
                with open(py_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                    matches = re.findall(r"SentenceTransformer\(['\"]([^'\"]+)['\"]\)", content)
                    for match in matches:
                        st_models.add(match)
            except:
                pass
        
        if st_models:
            print(f"   Modelos encontrados en código:")
            for model in st_models:
                print(f"     - {model}")
                self.config['sentence_transformer_models'] = list(st_models)
        
        # Buscar modelos de Ollama en el código
        print(f"\n🔍 Buscando modelos de Ollama en el código...")
        for py_file in RAIZ_PROYECTO.rglob("*.py"):
            if '.venv' in str(py_file) or 'Python-3.12.3' in str(py_file):
                continue
            try:
                with open(py_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                    matches = re.findall(r'"model":\s*"([^"]+)"', content)
                    for match in matches:
                        if 'embed' in match.lower() or 'nomic' in match.lower():
                            ollama_models.add(match)
            except:
                pass
        
        if ollama_models:
            print(f"   Modelos Ollama encontrados:")
            for model in ollama_models:
                print(f"     - {model}")
                self.config['ollama_embedding_models'] = list(ollama_models)
            
            # Verificar si Ollama está disponible
            print(f"\n🔍 Verificando disponibilidad de Ollama...")
            try:
                import httpx
                import asyncio
                
                async def check_ollama():
                    try:
                        async with httpx.AsyncClient(timeout=5.0) as client:
                            response = await client.get(f"{self.config.get('ollama_base_url', 'http://localhost:11434')}/api/tags")
                            if response.status_code == 200:
                                models = response.json().get("models", [])
                                available_models = [m['name'] for m in models]
                                print(f"   ✅ Ollama disponible")
                                print(f"   Modelos disponibles: {available_models[:5]}...")  # Mostrar primeros 5
                                
                                # Verificar si el modelo de embeddings está disponible
                                for ollama_model in ollama_models:
                                    if ollama_model in available_models:
                                        print(f"   ✅ Modelo {ollama_model} está disponible")
                                    else:
                                        print(f"   🚨 Modelo {ollama_model} NO está disponible en Ollama")
                                        self.problems.append(f"Modelo Ollama {ollama_model} no está instalado")
                                return True
                    except:
                        return False
                
                ollama_available = asyncio.run(check_ollama())
                if not ollama_available:
                    print(f"   ❌ Ollama no está disponible")
                    self.problems.append("Ollama no está disponible o no está corriendo")
                    
            except ImportError:
                print(f"   ⚠️ httpx no disponible para verificar Ollama")
                self.warnings.append("No se puede verificar disponibilidad de Ollama")
        
        # Detectar conflicto de sistemas de embeddings
        if st_models and ollama_models:
            print(f"\n   🚨 PROBLEMA CRÍTICO: Dos sistemas de embeddings incompatibles")
            print(f"   - Sentence Transformers: {list(st_models)}")
            print(f"   - Ollama: {list(ollama_models)}")
            print(f"   - Los embeddings NO son compatibles entre sistemas")
            self.problems.append("Dos sistemas de embeddings incompatibles (Ollama vs Sentence Transformers)")
    
    def analyze_pipeline(self):
        """Analiza el pipeline actual del sistema."""
        self.print_separator("[2] PIPELINE")
        
        # Analizar archivos principales
        plagiarism_file = RAIZ_PROYECTO / "app" / "backend" / "plagiarism.py"
        main_file = RAIZ_PROYECTO / "app" / "backend" / "main.py"
        ingest_file = RAIZ_PROYECTO / "app" / "backend" / "ingest_tesis.py"
        
        print("🔍 Analizando funciones del pipeline...")
        
        # Funciones de extracción
        extraction_functions = []
        # Funciones de chunking
        chunking_functions = []
        # Funciones de embeddings
        embedding_functions = []
        # Funciones de búsqueda
        search_functions = []
        # Funciones de scoring
        scoring_functions = []
        
        for py_file in [plagiarism_file, main_file, ingest_file]:
            if not py_file.exists():
                continue
            
            print(f"\n   Archivo: {py_file.name}")
            with open(py_file, 'r', encoding='utf-8') as f:
                content = f.read()
                
            # Buscar funciones relevantes
            if 'extract' in content.lower() or 'pdf' in content.lower():
                extract_matches = re.findall(r'def\s+(\w+.*extract\w*|\w+.*pdf\w*)', content)
                if extract_matches:
                    print(f"     Extracción: {extract_matches}")
                    extraction_functions.extend([(py_file.name, func) for func in extract_matches])
            
            if 'chunk' in content.lower() or 'fragment' in content.lower() or 'segment' in content.lower():
                chunk_matches = re.findall(r'def\s+(\w+.*chunk\w*|\w+.*fragment\w*|\w+.*segment\w*)', content)
                if chunk_matches:
                    print(f"     Chunking: {chunk_matches}")
                    chunking_functions.extend([(py_file.name, func) for func in chunk_matches])
            
            if 'embedding' in content.lower():
                embed_matches = re.findall(r'def\s+(\w+.*embedding\w*)', content)
                if embed_matches:
                    print(f"     Embeddings: {embed_matches}")
                    embedding_functions.extend([(py_file.name, func) for func in embed_matches])
            
            if 'query' in content.lower() or 'search' in content.lower():
                search_matches = re.findall(r'def\s+(\w+.*query\w*|\w+.*search\w*)', content)
                if search_matches:
                    print(f"     Búsqueda: {search_matches}")
                    search_functions.extend([(py_file.name, func) for func in search_matches])
            
            if 'analy' in content.lower() or 'score' in content.lower() or 'similarity' in content.lower():
                score_matches = re.findall(r'def\s+(\w+.*analy\w*|\w+.*score\w*|\w+.*similarity\w*)', content)
                if score_matches:
                    print(f"     Análisis/Scoring: {score_matches}")
                    scoring_functions.extend([(py_file.name, func) for func in score_matches])
        
        self.pipeline['extraction'] = extraction_functions
        self.pipeline['chunking'] = chunking_functions
        self.pipeline['embeddings'] = embedding_functions
        self.pipeline['search'] = search_functions
        self.pipeline['scoring'] = scoring_functions
        
        # Análisis específico del chunking
        print(f"\n🔍 Análisis específico de chunking...")
        if plagiarism_file.exists():
            with open(plagiarism_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Buscar el patrón de chunking
            chunk_pattern = re.search(r'fragments\s*=\s*\[([^\]]+)\]', content)
            if chunk_pattern:
                chunk_code = chunk_pattern.group(0)
                print(f"   Código de chunking encontrado:")
                print(f"   {chunk_code}")
                
                # Extraer tamaño
                size_match = re.search(r'\[([^\]]+):(\d+)\]', chunk_code)
                if size_match:
                    chunk_size = int(size_match.group(2))
                    self.chunking['size'] = chunk_size
                    self.chunking['unit'] = 'caracteres'
                    print(f"   Tamaño: {chunk_size} caracteres")
                    
                    # Evaluar tamaño de chunk
                    if chunk_size < 200:
                        print(f"   ⚠️ Tamaño de chunk muy pequeño ({chunk_size}) - puede fragmentar demasiado el contexto")
                        self.warnings.append(f"Tamaño de chunk muy pequeño: {chunk_size} caracteres")
                    elif chunk_size > 2000:
                        print(f"   ⚠️ Tamaño de chunk muy grande ({chunk_size}) - puede reducir precisión de coincidencias")
                        self.warnings.append(f"Tamaño de chunk muy grande: {chunk_size} caracteres")
                
                # Verificar overlap
                if 'step' in chunk_code or 'stride' in chunk_code:
                    print(f"   Overlap: Detectado")
                    self.chunking['overlap'] = True
                else:
                    print(f"   Overlap: No detectado")
                    self.chunking['overlap'] = False
                    print(f"   ⚠️ Sin overlap - coincidencias divididas entre chunks no serán detectadas")
                    self.warnings.append("Chunking sin overlap - coincidencias divididas no detectadas")
                
                # Evaluar método de segmentación
                if 'i:i+1000' in chunk_code or 'i:i+' in chunk_code:
                    print(f"   ⚠️ Segmentación por caracteres - puede cortar palabras a la mitad")
                    self.warnings.append("Segmentación por caracteres - puede cortar palabras")
    
    def analyze_embeddings(self):
        """Analiza la configuración de embeddings."""
        self.print_separator("[3] EMBEDDINGS")
        
        # Intentar cargar Sentence Transformers para obtener información del modelo
        try:
            from sentence_transformers import SentenceTransformer
            
            # Buscar qué modelo se usa
            model_name = 'paraphrase-multilingual-mpnet-base-v2'  # Modelo más común encontrado
            
            print(f"🔍 Probando carga del modelo: {model_name}")
            try:
                model = SentenceTransformer(model_name)
                print(f"✅ Modelo cargado exitosamente")
                
                # Obtener información del modelo
                test_text = "Texto de prueba para análisis de embeddings"
                embedding = model.encode(test_text)
                
                self.embeddings['model'] = model_name
                self.embeddings['dimension'] = len(embedding)
                self.embeddings['type'] = type(embedding[0]).__name__
                self.embeddings['normalization'] = 'unknown'  # SentenceTransformer normaliza por defecto
                
                print(f"   Modelo: {model_name}")
                print(f"   Dimensión: {len(embedding)}")
                print(f"   Tipo de dato: {type(embedding[0]).__name__}")
                
                # Calcular norma para verificar normalización
                import numpy as np
                norm = np.linalg.norm(embedding)
                print(f"   Norma L2: {norm:.4f}")
                if abs(norm - 1.0) < 0.01:
                    print(f"   ✅ Embeddings normalizados (norma ≈ 1.0)")
                    self.embeddings['normalization'] = 'L2 normalized'
                else:
                    print(f"   ⚠️ Embeddings no normalizados (norma = {norm:.4f})")
                    self.warnings.append("Embeddings no normalizados")
                
            except Exception as e:
                print(f"❌ Error cargando modelo: {e}")
                self.problems.append(f"No se pudo cargar el modelo Sentence Transformer: {e}")
                
        except ImportError:
            print(f"❌ Sentence Transformers no está instalado")
            self.problems.append("Sentence Transformers no está instalado")
        
        # Verificar información en código
        print(f"\n🔍 Buscando configuración de embeddings en código...")
        for py_file in RAIZ_PROYECTO.rglob("*.py"):
            if '.venv' in str(py_file) or 'Python-3.12.3' in str(py_file):
                continue
            try:
                with open(py_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                    
                # Buscar normalización
                if 'normalize' in content.lower():
                    print(f"   Normalización encontrada en: {py_file.name}")
                    
            except:
                pass
    
    def analyze_chromadb(self):
        """Analiza el estado de ChromaDB sin modificarlo."""
        self.print_separator("[4] CHROMADB")
        
        try:
            # Intentar importar ChromaDB
            try:
                __import__('pysqlite3')
                sys.modules['sqlite3'] = sys.modules.pop('pysqlite3')
            except ImportError:
                print("⚠️ pysqlite3-binary no instalado, usando sqlite3 del sistema")
            
            import chromadb
            
            # Analizar configuración en database.py
            db_file = RAIZ_PROYECTO / "chatbox" / "db" / "database.py"
            if db_file.exists():
                print(f"✅ Archivo de configuración ChromaDB encontrado: {db_file}")
                with open(db_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                # Extraer ruta de base de datos
                db_path_match = re.search(r'DB_PATH\s*=\s*["\']([^"\']+)["\']', content)
                if db_path_match:
                    db_path = db_path_match.group(1)
                    print(f"   Ruta configurada: {db_path}")
                    
                    # Verificar si es ruta relativa
                    if db_path.startswith('.'):
                        full_path = db_file.parent / db_path
                        print(f"   Ruta completa: {full_path}")
                        
                        if full_path.exists():
                            size = sum(f.stat().st_size for f in full_path.rglob('*') if f.is_file())
                            print(f"   Tamaño: {size / 1024:.2f} KB")
                            self.chromadb['path'] = str(full_path)
                            self.chromadb['size_kb'] = size / 1024
                        else:
                            print(f"   ⚠️ La ruta no existe")
                            self.warnings.append("Ruta de ChromaDB no existe")
            
            # Intentar conectar para obtener información (SOLO LECTURA)
            try:
                from chatbox.db.database import get_chroma_client
                
                print(f"\n🔍 Conectando a ChromaDB (SOLO LECTURA)...")
                client = get_chroma_client()
                print(f"✅ Conexión exitosa")
                
                # Listar colecciones
                collections = client.list_collections()
                print(f"   Colecciones: {[c.name for c in collections]}")
                self.chromadb['collections'] = [c.name for c in collections]
                
                # Analizar colección principal
                if 'tesis_universitarias' in [c.name for c in collections]:
                    collection = client.get_collection("tesis_universitarias")
                    count = collection.count()
                    print(f"\n   Colección 'tesis_universitarias':")
                    print(f"     Documentos: {count}")
                    self.chromadb['document_count'] = count
                    
                    if count > 0:
                        # Obtener sample (SOLO LECTURA)
                        try:
                            sample = collection.get(limit=1, include=['metadatas', 'embeddings'])
                            if sample['metadatas']:
                                print(f"     Sample metadata: {sample['metadatas'][0]}")
                                self.chromadb['sample_metadata'] = sample['metadatas'][0]
                            
                            # Verificar si hay embeddings
                            if sample.get('embeddings') and len(sample['embeddings']) > 0 and sample['embeddings'][0] is not None:
                                embedding_dim = len(sample['embeddings'][0])
                                print(f"     Dimensión de embeddings en ChromaDB: {embedding_dim}")
                                self.chromadb['embedding_dimension'] = embedding_dim
                                
                                # Comparar con el modelo configurado
                                if self.embeddings.get('dimension'):
                                    if embedding_dim == self.embeddings['dimension']:
                                        print(f"     ✅ Dimensión compatible con modelo configurado")
                                        self.ok.append("Dimensión de embeddings compatible")
                                    else:
                                        print(f"     🚨 ERROR CRÍTICO: Dimensión incompatible")
                                        print(f"     - ChromaDB: {embedding_dim} dims")
                                        print(f"     - Modelo configurado: {self.embeddings['dimension']} dims")
                                        self.problems.append(f"Dimensión de embeddings incompatible: ChromaDB {embedding_dim} vs modelo {self.embeddings['dimension']}")
                        except Exception as e:
                            print(f"     ⚠️ Error obteniendo sample: {e}")
                    else:
                        print(f"     ⚠️ COLECCIÓN VACÍA")
                        self.problems.append("Colección de ChromaDB está vacía")
                
            except Exception as e:
                print(f"❌ Error conectando a ChromaDB: {e}")
                self.warnings.append(f"No se pudo conectar a ChromaDB: {e}")
                
        except ImportError:
            print(f"❌ ChromaDB no está instalado")
            self.problems.append("ChromaDB no está instalado")
    
    def analyze_search(self):
        """Analiza la configuración de búsqueda."""
        self.print_separator("[5] SEARCH")
        
        # Analizar código de búsqueda
        plagiarism_file = RAIZ_PROYECTO / "app" / "backend" / "plagiarism.py"
        if plagiarism_file.exists():
            with open(plagiarism_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            print("🔍 Analizando configuración de búsqueda...")
            
            # Buscar n_results
            n_results_match = re.search(r'n_results\s*=\s*(\d+)', content)
            if n_results_match:
                n_results = int(n_results_match.group(1))
                self.search['n_results'] = n_results
                print(f"   n_results: {n_results}")
            
            # Buscar threshold
            threshold_match = re.search(r'if\s+.*<\s*([\d.]+)', content)
            if threshold_match:
                threshold = float(threshold_match.group(1))
                self.search['threshold'] = threshold
                print(f"   Threshold encontrado: {threshold}")
                
                # Evaluar threshold
                if threshold > 0.9:
                    print(f"   ⚠️ Threshold muy alto ({threshold}) - puede causar falsos negativos")
                    self.warnings.append(f"Threshold muy alto: {threshold}")
                elif threshold < 0.3:
                    print(f"   ⚠️ Threshold muy bajo ({threshold}) - puede causar falsos positivos")
                    self.warnings.append(f"Threshold muy bajo: {threshold}")
            
            # Buscar el threshold específico usado en el código
            specific_threshold = re.search(r'dist_factor\s*<\s*([\d.]+)', content)
            if specific_threshold:
                threshold_value = float(specific_threshold.group(1))
                print(f"   Threshold específico (dist_factor): {threshold_value}")
                
                if threshold_value == 0.8:
                    print(f"   ⚠️ Threshold 0.8 parece arbitrario, no calibrado para el modelo específico")
                    self.warnings.append("Threshold 0.8 no calibrado para el modelo específico")
            
            # Buscar cálculo de distancia
            if 'dist' in content and '100' in content:
                print(f"   ⚠️ Cálculo de distancia: dist/100 detectado")
                self.search['distance_calculation'] = 'dist/100'
                self.warnings.append("Cálculo de distancia asume rango 0-100 sin verificación")
            
            # Buscar métrica
            if 'cosine' in content.lower():
                print(f"   Métrica: cosine similarity mencionada")
                self.search['metric'] = 'cosine (mencionada)'
            elif 'euclidean' in content.lower():
                print(f"   Métrica: euclidean mencionada")
                self.search['metric'] = 'euclidean (mencionada)'
            else:
                print(f"   Métrica: No especificada en código (usando default de ChromaDB)")
                self.search['metric'] = 'default (no especificada)'
                self.warnings.append("Métrica de distancia no especificada en código")
    
    def analyze_scoring(self):
        """Analiza el cálculo del score final."""
        self.print_separator("[6] SCORING")
        
        plagiarism_file = RAIZ_PROYECTO / "app" / "backend" / "plagiarism.py"
        if plagiarism_file.exists():
            with open(plagiarism_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            print("🔍 Analizando cálculo de score...")
            
            # Buscar cálculo de porcentaje
            percentage_pattern = re.search(r'percentage\s*=\s*([^\n]+)', content)
            if percentage_pattern:
                percentage_code = percentage_pattern.group(1)
                print(f"   Cálculo de percentage: {percentage_code}")
                self.scoring['percentage_calculation'] = percentage_code
            
            # Buscar cálculo final
            final_pattern = re.search(r'procentaje\d*\s*=\s*([^\n]+)', content)
            if final_pattern:
                final_code = final_pattern.group(1)
                print(f"   Cálculo final: {final_code}")
                self.scoring['final_calculation'] = final_code
                
                # Detectar división doble - múltiples patrones
                double_division = False
                if '/ total_frags' in final_code and 'total_frags' in percentage_code:
                    double_division = True
                elif 'percentage/total_frags' in content or 'procentaje100=percentage/total_frags' in content:
                    double_division = True
                
                if double_division:
                    print(f"   🚨 ERROR CRÍTICO: División doble detectada")
                    print(f"   WARNING: semantic similarity is being interpreted as plagiarism score con error matemático")
                    self.problems.append("División doble en cálculo de porcentaje")
            
            # Verificar si hay distinción entre similarity y plagio
            if 'similarity' in content.lower() and 'plagiarism' in content.lower():
                print(f"   ⚠️ Sistema usa 'similarity' y 'plagiarism' indistintamente")
                print(f"   WARNING: semantic similarity is being interpreted as plagiarism score")
                self.warnings.append("Similitud semántica interpretada directamente como score de plagio")
    
    def run_controlled_tests(self):
        """Ejecuta tests controlados en memoria/temporales."""
        self.print_separator("[7] TESTS CONTROLADOS")
        
        print("🔍 Creando dataset de prueba en memoria...")
        
        # Dataset de prueba
        test_cases = {
            'different_topics': {
                'text1': "El cambio climático es un problema global que requiere acción inmediata.",
                'text2': "La economía digital está transformando los modelos de negocio tradicionales.",
                'expected': 'different',
                'description': 'Textos sobre temas completamente diferentes'
            },
            'same_topic_independent': {
                'text1': "El cambio climático es uno de los mayores desafíos ambientales del siglo XXI, afectando ecosistemas y sociedades humanas.",
                'text2': "El calentamiento global representa una amenaza significativa para el medio ambiente y la civilización moderna en la actualidad.",
                'expected': 'same_topic_independent',
                'description': 'Mismo tema (cambio climático) pero redacción independiente'
            },
            'exact_copy': {
                'text1': "El cambio climático es uno de los mayores desafíos que enfrenta la humanidad en el siglo XXI.",
                'text2': "El cambio climático es uno de los mayores desafíos que enfrenta la humanidad en el siglo XXI.",
                'expected': 'exact_copy',
                'description': 'Copia exacta'
            },
            'partial_copy': {
                'text1': "El cambio climático es uno de los mayores desafíos que enfrenta la humanidad en el siglo XXI. Los científicos advierten sobre consecuencias devastadoras.",
                'text2': "El cambio climático es uno de los mayores desafíos que enfrenta la humanidad en el siglo XXI. Sin embargo, algunas medidas están siendo implementadas.",
                'expected': 'partial_copy',
                'description': 'Copia parcial (primer párrafo idéntico)'
            },
            'paraphrase': {
                'text1': "El cambio climático afecta significativamente la biodiversidad global.",
                'text2': "Las modificaciones del clima producen importantes efectos sobre la diversidad biológica en el mundo.",
                'expected': 'paraphrase',
                'description': 'Paráfrasis (mismo significado, palabras diferentes)'
            },
            'word_substitution': {
                'text1': "El cambio climático es un problema grave para el planeta.",
                'text2': "El calentamiento global es un asunto serio para la Tierra.",
                'expected': 'word_substitution',
                'description': 'Sustitución de palabras clave'
            },
            'rearrangement': {
                'text1': "El cambio climático afecta la biodiversidad y los ecosistemas.",
                'text2': "La biodiversidad y los ecosistemas son afectados por el cambio climático.",
                'expected': 'rearrangement',
                'description': 'Reorganización de frases'
            }
        }
        
        print(f"   {len(test_cases)} casos de prueba creados")
        
        # Intentar probar con el sistema actual
        print(f"\n🔍 Intentando probar con el sistema actual...")
        
        try:
            # Importar funciones del sistema actual
            from app.backend.plagiarism import get_embeddings, analyze_plagiarism
            import asyncio
            
            async def test_single_case(case_name, case_data):
                """Prueba un solo caso."""
                text1 = case_data['text1']
                text2 = case_data['text2']
                expected = case_data['expected']
                
                # Simular análisis
                try:
                    # Generar embeddings
                    embedding1 = await get_embeddings(text1)
                    embedding2 = await get_embeddings(text2)
                    
                    if embedding1 and embedding2:
                        # Calcular similitud coseno
                        import numpy as np
                        from sklearn.metrics.pairwise import cosine_similarity
                        
                        similarity = cosine_similarity([embedding1], [embedding2])[0][0]
                        
                        return {
                            'case': case_name,
                            'expected': expected,
                            'similarity': float(similarity),
                            'description': case_data['description']
                        }
                    else:
                        return {
                            'case': case_name,
                            'expected': expected,
                            'similarity': None,
                            'error': 'No se pudo generar embeddings',
                            'description': case_data['description']
                        }
                except Exception as e:
                    return {
                        'case': case_name,
                        'expected': expected,
                        'similarity': None,
                        'error': str(e),
                        'description': case_data['description']
                    }
            
            # Ejecutar tests
            results = []
            for case_name, case_data in test_cases.items():
                result = asyncio.run(test_single_case(case_name, case_data))
                results.append(result)
            
            # Mostrar resultados
            print(f"\n   Resultados de tests:")
            print(f"   {'Caso':<25} {'Expected':<25} {'Similarity':<10} {'Status'}")
            print(f"   {'-'*70}")
            
            for result in results:
                similarity = result.get('similarity')
                if similarity is not None:
                    sim_str = f"{similarity:.4f}"
                    
                    # Clasificación simple
                    if similarity > 0.9:
                        classification = 'exact_copy'
                    elif similarity > 0.7:
                        classification = 'high_similarity'
                    elif similarity > 0.5:
                        classification = 'moderate_similarity'
                    else:
                        classification = 'low_similarity'
                    
                    # Verificar si coincide con expected
                    expected = result['expected']
                    if expected in ['exact_copy', 'partial_copy'] and similarity > 0.8:
                        status = '✅ OK'
                    elif expected == 'different' and similarity < 0.3:
                        status = '✅ OK'
                    elif expected == 'paraphrase' and 0.5 < similarity < 0.8:
                        status = '✅ OK'
                    else:
                        status = '⚠️ UNCERTAIN'
                else:
                    sim_str = 'ERROR'
                    classification = 'N/A'
                    status = '❌ ERROR'
                
                print(f"   {result['case']:<25} {result['expected']:<25} {sim_str:<10} {status}")
                print(f"   {result['description']}")
                print(f"   Classification: {classification}")
                print()
            
            self.scoring['test_results'] = results
            
        except Exception as e:
            print(f"❌ No se pudo ejecutar tests con el sistema actual: {e}")
            print(f"   Posibles causas:")
            print(f"   - Ollama no está corriendo")
            print(f"   - Modelo nomic-embed-text no está instalado")
            print(f"   - Problemas de importación")
            
            # Mostrar dataset sin ejecutar tests
            print(f"\n   Dataset de prueba (sin ejecutar):")
            for case_name, case_data in test_cases.items():
                print(f"   {case_name}: {case_data['description']}")
                print(f"     Expected: {case_data['expected']}")
    
    def generate_summary(self):
        """Genera el resumen final."""
        self.print_separator("[8] RESUMEN")
        
        print("CRITICAL:")
        for problem in self.problems:
            print(f"  🚨 {problem}")
        
        print("\nWARNING:")
        for warning in self.warnings:
            print(f"  ⚠️ {warning}")
        
        print("\nOK:")
        for item in self.ok:
            print(f"  ✅ {item}")
        
        if not self.problems:
            print("  🚨 No se detectaron problemas críticos")
        
        if not self.warnings:
            print("  ⚠️ No se detectaron advertencias")
        
        if not self.ok:
            print("  ✅ No se registraron elementos OK")
    
    def run_full_diagnosis(self):
        """Ejecuta el diagnóstico completo."""
        print("="*80)
        print("  DOCTORPLAGIO - DIAGNÓSTICO ACTUAL")
        print("  Script exclusivamente de lectura/análisis")
        print(f"  Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("="*80)
        
        try:
            self.analyze_configuration()
            self.analyze_pipeline()
            self.analyze_embeddings()
            self.analyze_chromadb()
            self.analyze_search()
            self.analyze_scoring()
            self.run_controlled_tests()
            self.generate_summary()
            
            print("\n" + "="*80)
            print("  DIAGNÓSTICO COMPLETADO")
            print("  NO se modificaron archivos, bases de datos o configuraciones")
            print("="*80)
            
        except Exception as e:
            print(f"\n❌ Error durante el diagnóstico: {e}")
            import traceback
            traceback.print_exc()

def main():
    """Función principal."""
    analyzer = DiagnosticAnalyzer()
    analyzer.run_full_diagnosis()

if __name__ == "__main__":
    main()