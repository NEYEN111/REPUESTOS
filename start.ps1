param([switch]$Reseed)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$taskTemp = Join-Path $PSScriptRoot '.tmp'
New-Item -ItemType Directory -Force -Path $taskTemp | Out-Null
$env:TEMP = $taskTemp
$env:TMP = $taskTemp
$env:PYTHONUTF8 = '1'
if (!(Test-Path '.venv/Scripts/python.exe')) {
    python -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'No se pudo crear el entorno Python.' }
}
$pythonExe = Join-Path $PSScriptRoot '.venv/Scripts/python.exe'
& $pythonExe -c 'import importlib.util,sys; sys.exit(0 if all(importlib.util.find_spec(m) for m in ["""fastapi""","""uvicorn""","""multipart""","""PIL""","""tzdata"""]) else 1)'
if ($LASTEXITCODE -ne 0) {
    python -m pip --python $pythonExe install -r requirements.txt
    if ($LASTEXITCODE -ne 0) { throw 'No se pudieron instalar las dependencias Python.' }
}
if (!(Test-Path 'backend/static/hero.webp')) {
    & $pythonExe scripts/download_assets.py
    if ($LASTEXITCODE -ne 0) { throw 'No se pudieron descargar las imágenes.' }
}
if (!(Test-Path '.venv-ml/Scripts/python.exe')) {
    python -m venv .venv-ml
    if ($LASTEXITCODE -ne 0) { throw 'No se pudo crear el entorno de inferencia.' }
}
$mlPython = Join-Path $PSScriptRoot '.venv-ml/Scripts/python.exe'
& $mlPython -c 'import sys; from pathlib import Path; from importlib.metadata import distributions; installed={d.metadata["""Name"""].lower():d.version for d in distributions()}; sys.exit(0 if all(installed.get(p.lower())==v for p,v in (s.split("""==""") for s in Path("""ml/runtime-requirements.txt""").read_text().splitlines() if s)) else 1)'
if ($LASTEXITCODE -ne 0) {
    python -m pip --python $mlPython install -r ml/runtime-requirements.txt
    if ($LASTEXITCODE -ne 0) { throw 'No se pudieron instalar las dependencias del modelo.' }
}
if ($Reseed) { & $pythonExe scripts/seed.py --reset }
else { & $pythonExe scripts/seed.py }
if ($LASTEXITCODE -ne 0) { throw 'No se pudo preparar la base de datos.' }
Push-Location frontend
try {
    if (!(Test-Path node_modules)) {
        npm.cmd ci --no-audit --no-fund
        if ($LASTEXITCODE -ne 0) { throw 'No se pudieron instalar las dependencias web.' }
    }
    npm.cmd run build
    if ($LASTEXITCODE -ne 0) { throw 'Falló la compilación web.' }
} finally { Pop-Location }
Write-Host 'Tienda y gestión: http://127.0.0.1:8000  |  Ingresa desde Mi cuenta' -ForegroundColor Green
Write-Host 'Detener: Ctrl+C. Los datos se conservan en data/store.db.'
& $pythonExe -m uvicorn backend.app:app --host 127.0.0.1 --port 8000
