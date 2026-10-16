{
    "name": "DoctorPlagio",
    "version": "20.0.1.0.2",
    "summary": "Gestión del análisis de similitud documental",
    "description": "Módulo de gestión e integración del sistema DoctorPlagio.",
    "category": "Productivity",
    "author": "DoctorPlagio",
    "license": "LGPL-3",
    "depends": ["base"],
    "data": [
        "security/access.xml",
        "security/dashboard_access.xml",
        "data/ir_cron.xml",
        "data/doctorplagio_dashboard_data.xml",
        "views/document_views.xml",
        "views/dashboard_views.xml",
        "views/res_config_settings_views.xml"
    ],
    "installable": True,
    "application": True
}
