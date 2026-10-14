Integración inicial DoctorPlagio Odoo 20 con backend existente

Archivos:
- models/document.py
- views/document_views.xml

Requisitos:
- Backend existente iniciado y accesible desde la máquina donde corre Odoo.
- Endpoint POST /analyze, que acepta multipart/form-data con campo "file".
- El backend debe responder JSON con status="success" y results.plagiarism_percentage.
- La API del backend en el ZIP usa el puerto 5000 en su arranque directo.
- El campo backend_url se puede cambiar en el formulario si el backend escucha en otra dirección.

Aplicación:
1. Haz copia de seguridad de los dos archivos actuales.
2. Sustituye models/document.py y views/document_views.xml por estos.
3. Reinicia Odoo.
4. En Aplicaciones, actualiza DoctorPlagio.
5. Abre un documento PDF y pulsa "Analizar documento".

Notas:
- La integración inicial solo habilita PDF porque el backend /analyze del ZIP extrae texto explícitamente de PDF; para otros formatos su ruta actual decodifica bytes como UTF-8, lo cual no equivale a extraer DOCX.
- El backend existente también guarda documento/versiones/resultados en su propia base de datos. Esta integración conserva ese comportamiento y además copia el resultado JSON a Odoo. Revisa la configuración del backend antes de ejecutar análisis reales.
- Las dependencias de ChromaDB, Sentence Transformers, PyMuPDF y el resto del motor deben instalarse en el entorno del backend, no se trasladan automáticamente al venv de Odoo.
