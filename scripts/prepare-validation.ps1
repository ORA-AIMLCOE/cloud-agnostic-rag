$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
docker build -t aws-oci-validator:oracle-v1 (Join-Path $PSScriptRoot 'validation')
if ($LASTEXITCODE -ne 0) { throw 'Validation image build failed. Start Docker and retry.' }
