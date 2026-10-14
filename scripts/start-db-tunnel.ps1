param([string]$Profile = 'aws-rag-provision', [int]$LocalPort = 15432)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
$aws = Join-Path $env:LOCALAPPDATA 'Programs\Amazon\AWSCLIV2\aws.exe'
if (-not (Test-Path -LiteralPath $aws)) { $aws = (Get-Command aws -ErrorAction Stop).Source }
$pluginDir = Join-Path $projectRoot '.tools\session-manager\bin'
if (Test-Path -LiteralPath (Join-Path $pluginDir 'session-manager-plugin.exe')) {
    $env:PATH = "$pluginDir;$env:PATH"
}
if (-not (Get-Command session-manager-plugin -ErrorAction SilentlyContinue)) {
    throw 'Install the AWS Session Manager plugin before starting the database tunnel.'
}
$resources = Get-Content (Join-Path $projectRoot 'infrastructure\aws\development-resources.json') -Raw | ConvertFrom-Json
$parameters = @{host=@($resources.database_endpoint); portNumber=@('5432'); localPortNumber=@("$LocalPort")}
$parameterFile = Join-Path $projectRoot '.validation\db-tunnel-parameters.json'
[IO.File]::WriteAllText($parameterFile, ($parameters | ConvertTo-Json -Compress))
Write-Host "Keep this terminal open. Database tunnel: localhost:$LocalPort -> private RDS PostgreSQL."
& $aws ssm start-session --profile $Profile --region $resources.region --target $resources.bridge_instance --document-name AWS-StartPortForwardingSessionToRemoteHost --parameters "file://$parameterFile"
if ($LASTEXITCODE -ne 0) { throw 'Tunnel failed. Check that AWS login is current and the bridge is running.' }
