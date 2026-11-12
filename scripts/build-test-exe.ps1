# Builds ONE file, backend\dist\zcs-leadengine.exe, with the UI and your backend\.env baked in.
# For handing to people you trust. Never upload it anywhere public: the .env inside holds the database URL.
# Run from the repo root:  powershell -ExecutionPolicy Bypass -File scripts\build-test-exe.ps1 [-Port 8005]
# The port is baked in. A ZCS_PORT line in a .env placed next to the exe overrides it later.
param([int]$Port = 8005)
$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent
if (-not (Test-Path "$root\backend\.env")) { throw "backend\.env not found" }

# Bake a copy of .env with the chosen port; your real backend\.env is never changed.
$bake = "$root\backend\build\envbake"
New-Item -ItemType Directory -Force $bake | Out-Null
(Get-Content "$root\backend\.env" | Where-Object { $_ -notmatch "^ZCS_PORT=" }) + "ZCS_PORT=$Port" | Set-Content "$bake\.env"

Push-Location "$root\frontend"
$env:STATIC_EXPORT = "1"; $env:NEXT_PUBLIC_API_URL = "same-origin"
npm run build
Remove-Item Env:STATIC_EXPORT, Env:NEXT_PUBLIC_API_URL
Pop-Location

Push-Location "$root\backend"
.\.venv\Scripts\python -m pip install -q pyinstaller
.\.venv\Scripts\python -m PyInstaller launcher.py --name zcs-leadengine --onefile --noconfirm `
  --add-data "$root\frontend\out;static" --add-data "$root\backend\migrations;migrations" `
  --add-data "$root\backend\alembic.ini;." --add-data "$root\backend\scoring_config.json;." `
  --add-data "$bake\.env;." `
  --collect-submodules app --collect-submodules uvicorn `
  --collect-all psycopg --collect-all psycopg_binary --collect-all ddgs
Pop-Location
Write-Host "`nDone: $root\backend\dist\zcs-leadengine.exe (port $Port)"
