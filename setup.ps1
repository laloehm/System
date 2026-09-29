# ==============================================================================
# SCRIPT DE INSTALACIÓN RÁPIDA - SISTEMA DE AFILIADOS (GANGAS MX)
# Uso: En una máquina nueva con Python y Node.js instalados, ejecuta:
#      powershell -ExecutionPolicy Bypass -File setup.ps1
# ==============================================================================

$ErrorActionPreference = "Stop"

Write-Host "==================================================" -ForegroundColor Cyan
Write-Host " Iniciando instalacion de dependencias del Sistema" -ForegroundColor Cyan
Write-Host "==================================================" -ForegroundColor Cyan
Write-Host ""

# 1. Comprobar Python
Write-Host "[1/5] Verificando Python..." -ForegroundColor Yellow
$pythonCmd = Get-Command python -ErrorAction SilentlyContinue
if (-not $pythonCmd) {
    Write-Host "ERROR: Python no esta instalado o no se encuentra en el PATH." -ForegroundColor Red
    Write-Host "Por favor instala Python 3.10+ desde python.org e intenta de nuevo." -ForegroundColor Red
    exit 1
}
Write-Host "  -> Python detectado: $(python --version)" -ForegroundColor Green

# 2. Comprobar Node.js y npm
Write-Host "[2/5] Verificando Node.js y npm..." -ForegroundColor Yellow
$nodeCmd = Get-Command node -ErrorAction SilentlyContinue
$npmCmd  = Get-Command npm -ErrorAction SilentlyContinue
if (-not $nodeCmd -or -not $npmCmd) {
    Write-Host "ADVERTENCIA: Node.js o npm no se detectaron en el sistema." -ForegroundColor Yellow
    Write-Host "Si vas a usar el Panel Web (Next.js), instala Node.js (v18+) desde nodejs.org" -ForegroundColor Yellow
} else {
    Write-Host "  -> Node.js detectado: $(node --version) | npm: $(npm --version)" -ForegroundColor Green
}

# 3. Crear entorno virtual e instalar requerimientos de Python
Write-Host "[3/5] Configurando entorno virtual de Python (venv)..." -ForegroundColor Yellow
if (-not (Test-Path "venv")) {
    python -m venv venv
    Write-Host "  -> Entorno virtual creado en .\venv" -ForegroundColor Green
} else {
    Write-Host "  -> Entorno virtual existente detectado." -ForegroundColor Green
}

$venvPython = ".\venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    # Fallback para entornos Unix/Bash si se ejecutara en PowerShell Core
    $venvPython = ".\venv\bin\python"
}

Write-Host "  -> Actualizando pip e instalando requirements.txt..." -ForegroundColor Gray
& $venvPython -m pip install --upgrade pip --quiet
& $venvPython -m pip install -r requirements.txt --quiet
Write-Host "  -> Librerias de Python instaladas correctamente." -ForegroundColor Green

# 4. Instalar Chromium para Playwright
Write-Host "[4/5] Instalando navegador Chromium para Playwright (scrapers)..." -ForegroundColor Yellow
& $venvPython -m playwright install chromium
Write-Host "  -> Chromium para Playwright instalado correctamente." -ForegroundColor Green

# 5. Instalar dependencias del Web Panel (Next.js)
if (Test-Path "web-panel\package.json") {
    Write-Host "[5/5] Instalando dependencias de Node.js en web-panel..." -ForegroundColor Yellow
    if ($npmCmd) {
        Push-Location web-panel
        npm install --silent
        Pop-Location
        Write-Host "  -> Dependencias del Panel Web instaladas correctamente." -ForegroundColor Green
    } else {
        Write-Host "  -> Omitido: npm no disponible. Ejecuta 'npm install' en web-panel/ cuando instales Node.js." -ForegroundColor Yellow
    }
}

# Verificación final de .env
Write-Host ""
Write-Host "==================================================" -ForegroundColor Cyan
if (-not (Test-Path ".env")) {
    if (Test-Path ".env.example") {
        Copy-Item ".env.example" ".env"
        Write-Host "AVISO IMPORTANTE: Se ha generado un archivo '.env' a partir de '.env.example'." -ForegroundColor Yellow
        Write-Host "Abre '.env' y completa tus tokens/credenciales para que el bot pueda operar." -ForegroundColor Yellow
    }
} else {
    Write-Host "Archivo de configuracion '.env' detectado correctamente." -ForegroundColor Green
}

Write-Host ""
Write-Host " INSTALACION COMPLETADA CON EXITO! " -ForegroundColor Green -BackgroundColor Black
Write-Host "==================================================" -ForegroundColor Cyan
