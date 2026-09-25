# DoctorPlagio V1.1

Esta versión corrige el motor de similitud sin depender de APIs comerciales.

## Cambios

- Un solo modelo de embeddings: `paraphrase-multilingual-mpnet-base-v2`.
- Embeddings normalizados.
- Nueva colección Chroma `tesis_universitarias_v11` con métrica cosine.
- Chunking por oraciones con overlap.
- Score de evidencia separado de la similitud semántica.
- Detección de coincidencia literal, léxica y semántica.
- Se mantiene separada la detección de texto generado por IA.
- Se corrige la división doble del porcentaje.
- La subida de PDF usa PyMuPDF en lugar de decodificar el PDF como UTF-8.

## Migración recomendada

1. Haz una copia de `chatbox/db/chroma_data` y de `data/chroma_db`.
2. Instala dependencias del backend.
3. Ejecuta `python app/backend/migrate_chroma_v11.py`.
4. Verifica que `tesis_universitarias_v11` tenga los mismos documentos.
5. Ejecuta el backend.
6. Solo después, si todo está correcto, deja de usar la colección antigua.

La migración NO elimina la colección anterior.

## Importante

`plagiarism_percentage` representa **cobertura de evidencia** de los chunks del documento, no una probabilidad estadística de plagio. Los resultados individuales incluyen `semantic_similarity`, `exact_overlap`, `lexical_similarity`, `evidence_score` y `classification`.
