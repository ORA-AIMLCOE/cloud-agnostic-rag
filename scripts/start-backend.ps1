$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location (Join-Path $projectRoot 'backend')
python -m uvicorn app.main:app --host 127.0.0.1 --port 8011 --no-access-log
