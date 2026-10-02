# DoctorPlagio — AI Analysis V2

## Integración

Esta versión conserva el motor híbrido de plagio y añade un análisis jerárquico de características lingüísticas de IA.

### Flujo

PDF/TXT/DOCX → estructura académica → segmentos → métricas determinísticas → GPT-OSS → análisis por capítulo → comparación transversal → interfaz.

### Archivos nuevos

- `backend/ai_metrics.py`: métricas calculadas por Python.
- `backend/ai_prompts.py`: prompts separados por segmento, capítulo y documento.
- `backend/ai_document_analysis.py`: orquestador del análisis V2.

### Archivos modificados

- `backend/plagiarism.py`: integra V2 y conserva el motor de plagio.
- `backend/main.py`: los PDF conservan marcadores internos de página para poder mostrar rangos de páginas; los marcadores se eliminan antes del motor de plagio.
- `frontend/check.html`: muestra resumen, capítulos, páginas, métricas y segmentos desplegables.

### Interpretación

La puntuación `ai_score` es una estimación de características lingüísticas compatibles con redacción o asistencia de IA. No demuestra autoría. La información institucional o conceptual puede provenir de fuentes humanas aunque la redacción haya sido asistida por IA.

### Ejecución

Desde `C:\PROYECTO\DoctorPlagio`:

```powershell
python -m flask --app app.backend.main run --debug
```

El frontend sigue utilizando `http://localhost:5000/analyze`.
