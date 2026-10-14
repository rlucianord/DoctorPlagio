
$ErrorActionPreference = "Stop"

$ProjectRoot = "C:\PROYECTO\DoctorPlagio"
$AppRoot = Join-Path $ProjectRoot "app"
$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"

# Si el backend tiene su propio entorno virtual, cambia esta ruta
# por el Python de ese entorno.
if (-not (Test-Path $Python)) {
    throw "No encuentro el Python del entorno virtual: $Python"
}

if (-not (Test-Path (Join-Path $AppRoot "backend\main.py"))) {
    throw "No encuentro app\backend\main.py. Revisa la ruta del backend."
}

Set-Location $AppRoot

# Persistencia aislada: no utilizar drplagium.
$env:DATABASE_URL = "postgresql://odoo:odootest2026@localhost:5432/drplagium"

# Conserva la configuración existente del corpus ChromaDB.
# No inventes otra ruta: confirma la ruta actual antes de fijarla aquí.

& $Python -m backend.main
