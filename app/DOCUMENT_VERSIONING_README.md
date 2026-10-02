# DoctorPlagio — Historial de versiones de documentos

Esta integración añade control de versiones para documentos que el usuario sube repetidamente después de recibir una evaluación.

## Comportamiento

1. Se calcula un hash SHA-256 del archivo cuando existe archivo físico.
2. Se calcula un hash SHA-256 del contenido textual normalizado.
3. Si el contenido textual coincide con una evaluación anterior, DoctorPlagio:
   - identifica el documento como la misma versión de contenido;
   - recupera la última evaluación guardada;
   - no vuelve a ejecutar el motor de plagio ni el análisis local de IA;
   - registra una nueva entrada histórica indicando `unchanged_reused`.
4. Si el contenido cambió pero sigue siendo muy similar a una versión anterior, DoctorPlagio:
   - registra la relación entre versiones;
   - calcula una comparación a nivel de oraciones;
   - muestra oraciones modificadas, añadidas y eliminadas;
   - ejecuta nuevamente el análisis completo para que los porcentajes correspondan a la nueva versión.
5. Cada evaluación permanece almacenada; no se sobrescribe la anterior.

## Tablas nuevas

- `document_versions`: huellas, versión, relación con la versión anterior, similitud, estado, diff y evaluación JSON.

La tabla se crea mediante el `Base.metadata.create_all()` existente. No se eliminan las tablas actuales.

## Estados

- `new_analysis`: primera evaluación.
- `revised_document`: nueva versión que cambió y fue analizada nuevamente.
- `unchanged_reused`: contenido textual idéntico a una evaluación anterior; se reutiliza esa evaluación.

## Nota metodológica

La similitud entre versiones sirve para identificar continuidad documental. No debe interpretarse como porcentaje de plagio. El análisis de plagio sigue utilizando el motor híbrido existente y el análisis de IA sigue expresando características lingüísticas compatibles con IA/IA-asistencia, no una prueba de autoría.
