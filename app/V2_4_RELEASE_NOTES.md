# DoctorPlagio V2.4 — Resumen de cambios

Esta versión parte directamente de `DoctorPlagio_app_integrado_AI_V2_3_MemorySafe` y conserva su arquitectura y funcionalidades existentes.

## Cambios de V2.4

### 1. Interfaz web simplificada
La página de análisis muestra únicamente el resumen:
- Porcentaje de Plagio (Texto)
- Interpretación
- Porcentaje de Contenido IA
- Porcentaje Estimado de Características Humanas
- Nivel de confianza
- Predominio de características
- Explicación
- Advertencia metodológica
- Botón para descargar el informe PDF

Se retiró de la página web el detalle extenso de capítulos, segmentos, coincidencias y evolución. Ese detalle pasa al informe PDF.

### 2. Informe PDF profesional
Se incorporó `reportlab` y un generador de informes en:
`app/backend/reports.py`

El informe utiliza el resultado ya calculado y almacenado. No vuelve a ejecutar el análisis.

Incluye:
- resumen ejecutivo;
- resultados de similitud/plagio;
- fuentes y fragmentos relevantes;
- análisis de características de IA;
- métricas globales;
- análisis por capítulo/sección;
- señales observadas;
- evolución y cambios entre versiones;
- metodología y limitaciones.

### 3. Descarga del informe
Nuevo endpoint:
`GET /report/<version_id>`

La versión guardada en PostgreSQL se utiliza para construir el PDF.

### 4. Español
Se reforzaron los prompts para que las explicaciones destinadas al usuario se produzcan en español y se añadieron normalizadores para evitar que valores como `medium`, `high` o `intermediate` aparezcan en la interfaz.

### 5. Interpretación metodológica
La interfaz ya no muestra la frase técnica en inglés que describía la cobertura de evidencia.

La interpretación se expresa en español y distingue cobertura de evidencia de una probabilidad matemática de plagio.

### 6. Compatibilidad
No se eliminan los módulos existentes de:
- PostgreSQL;
- versionado de documentos;
- reutilización de evaluaciones idénticas;
- ChromaDB;
- Sentence Transformers;
- GPT-OSS / llama.cpp;
- monitor de memoria;
- autenticación;
- pagos;
- análisis académico por capítulos y segmentos.

## Validación realizada

- `python -m compileall` sobre el proyecto: OK.
- Generación de un PDF de prueba con `reportlab`: OK.

No se declara una prueba completa de extremo a extremo porque eso requiere ejecutar el entorno real del usuario, su PostgreSQL, ChromaDB y el modelo GGUF.
