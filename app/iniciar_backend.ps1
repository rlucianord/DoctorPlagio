
$ErrorActionPreference = "Stop"

# ============================================================
# DoctorPlagio Backend - Lanzador en segundo plano
# ============================================================

$ProjectRoot = "C:\PROYECTO\DoctorPlagio"
$AppRoot     = Join-Path $ProjectRoot "app"
$Python      = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$MainFile    = Join-Path $AppRoot "backend\main.py"
$LogDir      = Join-Path $ProjectRoot "logs"

# Validar rutas existentes
if (-not (Test-Path $Python)) {
    throw "No encuentro el Python del entorno virtual: $Python"
}

if (-not (Test-Path $MainFile)) {
    throw "No encuentro app\backend\main.py: $MainFile"
}

# Crear carpeta de logs
New-Item -ItemType Directory -Path $LogDir -Force |
    Out-Null

# Evitar iniciar otra instancia si el puerto 5000 ya está ocupado
$Listener = Get-NetTCPConnection `
    -LocalPort 5000 `
    -State Listen `
    -ErrorAction SilentlyContinue

if ($Listener) {
    Write-Host "El puerto 5000 ya está escuchando."
    Write-Host "No se iniciará otra instancia para evitar duplicados."
    exit 0
}

# Configuración del backend
$env:DATABASE_URL = "postgresql://odoo:odootest2026@localhost:5432/drplagium"

# No modificar la configuración existente de ChromaDB.
# Las variables de entorno ya definidas se heredarán del proceso.
# Si ChromaDB depende de variables definidas en otro terminal,
# deberán configurarse también aquí antes del arranque.

# Logs únicos por ejecución
$Stamp  = Get-Date -Format "yyyyMMdd_HHmmss"
$StdOut = Join-Path $LogDir "backend_$Stamp.log"
$StdErr = Join-Path $LogDir "backend_error_$Stamp.log"

Write-Host "Iniciando DoctorPlagio Backend en segundo plano..."

# Arrancar usando el módulo existente
$Process = Start-Process `
    -FilePath $Python `
    -ArgumentList @("-m", "backend.main") `
    -WorkingDirectory $AppRoot `
    -WindowStyle Hidden `
    -RedirectStandardOutput $StdOut `
    -RedirectStandardError $StdErr `
    -PassThru

Start-Sleep -Seconds 5

# Verificar proceso y puerto
if ($Process.HasExited) {
    Write-Host "ERROR: el backend terminó durante el arranque."
    Write-Host "Revisa el log: $StdErr"
    exit 1
}

$Listener = Get-NetTCPConnection `
    -LocalPort 5000 `
    -State Listen `
    -ErrorAction SilentlyContinue

if ($Listener) {
    Write-Host "Backend iniciado correctamente."
    Write-Host "PID: $($Process.Id)"
    Write-Host "Puerto: 5000"
    Write-Host "Log: $StdOut"
    Write-Host "Errores: $StdErr"
} else {
    Write-Host "El proceso sigue activo, pero no se detecta el puerto 5000."
    Write-Host "Comprueba la configuración del puerto y los logs."
}
