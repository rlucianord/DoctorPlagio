DoctorPlagio - Panel de control visual corregido

Este parche reorganiza únicamente la vista XML del panel para usar una cuadrícula responsive de tarjetas.
Los contadores siguen leyendo los datos reales del modelo doctorplagio.document y cada tarjeta abre su lista filtrada.

Instalación recomendada:
1. Haz una copia de seguridad de tu carpeta doctorplagio.
2. Sustituye views/dashboard_views.xml por el archivo incluido.
3. Reinicia Odoo.
4. Actualiza el módulo DoctorPlagio desde Aplicaciones.

No sobrescribas document.py, analysis_job.py ni otros archivos del módulo con este parche.
