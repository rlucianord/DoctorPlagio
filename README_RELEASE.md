# DoctorPlagio V2.6 — Motor Copy/Paste y Corpus Incremental

## Base

Esta versión parte directamente de `DoctorPlagio_app_integrado_AI_V2_5`.

No elimina PostgreSQL, ChromaDB, MPNet, GPT-OSS, versionado de documentos ni generación del informe PDF.

## Nuevo

### 1. Motor Copy/Paste local

Archivo:

`app/backend/copypaste_engine.py`

Implementa:

- n-gramas de 8 palabras;
- fingerprints;
- selección tipo Winnowing;
- índice SQLite;
- coincidencias por bloques consecutivos;
- cobertura de Copy/Paste sin doble conteo;
- fuentes y fragmentos de evidencia;
- páginas cuando el documento analizado las conserva.

### 2. Gestor de corpus

Archivo:

`scripts/corpus_manager.py`

Comandos:

```powershell
python scripts\corpus_manager.py init
python scripts\corpus_manager.py stats
python scripts\corpus_manager.py ingest-file ...
python scripts\corpus_manager.py ingest-dir ...
python scripts\corpus_manager.py ingest-csic ...
python scripts\corpus_manager.py ingest-jsonl ...
```

El proceso es incremental: un documento con el mismo contenido no se vuelve a indexar.

### 3. Fuentes documentales

Se incluye documentación para:

- CSIC Spanish Corpus;
- Corpus científico y académico de USC / Proxecto Nós;
- PAN-PC-11 como benchmark;
- PAN español-inglés como benchmark;
- CEREAL como fuente de investigación;
- TDX como fuente secundaria.

No se descargan automáticamente datasets grandes dentro del ZIP.

### 4. Integración con el análisis

`plagiarism.py` ejecuta el motor Copy/Paste y devuelve:

`copypaste_analysis`

El motor existente de Chroma/MPNet se conserva.

GPT-OSS continúa separado y se utiliza para el análisis de características compatibles con IA.

### 5. Interfaz

La pantalla de resultados muestra:

- porcentaje de Copy/Paste detectado;
- cantidad de documentos consultados;
- porcentaje de similitud textual existente;
- interpretación;
- análisis de IA.

### 6. PDF

El informe incluye:

- porcentaje de Copy/Paste;
- documentos del corpus consultado;
- fuentes con coincidencias;
- fragmentos encontrados;
- páginas del documento analizado cuando están disponibles;
- páginas fuente cuando la fuente conserva esa información.

## Validación

Se ejecutaron:

- `compileall`: correcto.
- pruebas del motor Copy/Paste: 2 pruebas correctas.

## Importante

El corpus de producción debe incorporar únicamente documentos cuyo uso sea compatible con el propósito de DoctorPlagio. Que un dataset pueda descargarse no significa automáticamente que todo su contenido pueda redistribuirse comercialmente.

La información de licencias y procedencia queda documentada en:

`docs/COPYPASTE_CORPUS_README.md`

y:

`docs/CORPUS_SOURCES.json`
