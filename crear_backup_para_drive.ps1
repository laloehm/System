# ==============================================================================
# SCRIPT GENERADOR DE RESPALDO PRIVADO (PARA GOOGLE DRIVE / ONEDRIVE)
# Empaqueta los archivos privados que NO estan en GitHub en un unico archivo ZIP.
# ==============================================================================

$ErrorActionPreference = "Stop"

$fecha = Get-Date -Format "yyyyMMdd_HHmmss"
$desktop = [Environment]::GetFolderPath("Desktop")
$tempFolder = "$env:TEMP\Backup_System_$fecha"
$zipFile = "$desktop\Respaldo_Privado_System_$fecha.zip"

Write-Host "==================================================" -ForegroundColor Cyan
Write-Host " Creando paquete de Respaldo Privado para Drive   " -ForegroundColor Cyan
Write-Host "==================================================" -ForegroundColor Cyan
Write-Host ""

# Crear carpeta temporal
New-Item -ItemType Directory -Path $tempFolder -Force | Out-Null

# Lista de archivos privados y de configuracion clave
$archivosSensibles = @(
    ".env",
    "Afiliados-EHM-credentials.csv",
    "scheduler_config.json",
    "scraping_config.json",
    "user_state.json",
    "products_list.json",
    "products_list_baby.json",
    "products_list_pets.json",
    "queue_tenis.json",
    "queue_moda.json"
)

# Patrones para sesiones y cookies
$patronesSesiones = @(
    "storage_state*.json",
    "*_state*.json"
)

$copiados = 0

# Copiar archivos sensibles directos
foreach ($archivo in $archivosSensibles) {
    if (Test-Path $archivo) {
        Copy-Item -Path $archivo -Destination $tempFolder -Force
        Write-Host "  [+] Incluido: $archivo" -ForegroundColor Green
        $copiados++
    }
}

# Copiar archivos de sesión
foreach ($patron in $patronesSesiones) {
    Get-ChildItem -Path . -Filter $patron -File -ErrorAction SilentlyContinue | ForEach-Object {
        Copy-Item -Path $_.FullName -Destination $tempFolder -Force
        Write-Host "  [+] Incluida sesion: $($_.Name)" -ForegroundColor Green
        $copiados++
    }
}

Write-Host ""
Write-Host "Comprimiendo $copiados archivos en el ZIP..." -ForegroundColor Yellow

# Comprimir a archivo ZIP en el Escritorio
if (Test-Path $zipFile) { Remove-Item $zipFile -Force }
Compress-Archive -Path "$tempFolder\*" -DestinationPath $zipFile -Force

# Limpiar carpeta temporal
Remove-Item -Path $tempFolder -Recurse -Force

Write-Host ""
Write-Host "==================================================" -ForegroundColor Cyan
Write-Host " RESPALDO CREADO EXITOSAMENTE! " -ForegroundColor Green -BackgroundColor Black
Write-Host " Ubicacion: $zipFile" -ForegroundColor Cyan
Write-Host ""
Write-Host "Pasos siguientes:" -ForegroundColor Yellow
Write-Host "1. Ve a tu Escritorio y sube ese archivo ZIP a tu Google Drive." -ForegroundColor White
Write-Host "2. Si alguna vez necesitas restaurar en una PC nueva:" -ForegroundColor White
Write-Host "   - Clonas tu repo con 'git clone https://github.com/laloehm/System.git'" -ForegroundColor Gray
Write-Host "   - Descomprimes este ZIP directamente dentro de la carpeta clonada." -ForegroundColor Gray
Write-Host "   - Ejecutas 'powershell -ExecutionPolicy Bypass -File setup.ps1'" -ForegroundColor Gray
Write-Host "==================================================" -ForegroundColor Cyan
