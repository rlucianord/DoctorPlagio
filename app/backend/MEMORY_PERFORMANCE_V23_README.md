# DoctorPlagio V2.3 — Memory Safe / Diagnostic

## Objetivo
Reducir la competencia de memoria entre MPNet y GPT-OSS y medir exactamente en qué fase aumenta la RAM.

## Cambios
- MPNet se libera antes de iniciar GPT-OSS.
- `LOCAL_LLM_CONTEXT` predeterminado: 4096.
- `LOCAL_LLM_BATCH` predeterminado: 64.
- Telemetría de RAM antes/después de extracción de bloques e inferencias.
- `gc.collect()` en puntos de transición.
- Se mantienen análisis por capítulos, segmentos, versiones, plagio y evidencia de oraciones.

## Interpretación
El log mostrará líneas `[MEM]`. El objetivo es identificar si el salto ocurre al generar bloques, al cargar páginas de GPT-OSS o durante la inferencia.

## Importante
No se desactiva el análisis IA automáticamente: primero se mide el consumo real para no degradar la funcionalidad ni la calidad sin evidencia.
