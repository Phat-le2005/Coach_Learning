param([switch]$Lab, [switch]$Lan, [int]$Port = 3000, [string]$HostName = '127.0.0.1', [string]$ApiUrl = 'http://127.0.0.1:8000')
$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$frontend = Join-Path $repoRoot 'frontend'
if (!(Test-Path -LiteralPath (Join-Path $frontend 'node_modules/next/dist/bin/next'))) { throw 'Run npm ci in frontend first.' }
$env:API_BASE_URL = $ApiUrl
$env:OCR_V2_EXPERIMENTAL = if ($Lab) { '1' } else { '0' }
$env:COACH_LAN_MODE = if ($Lan) { '1' } else { '0' }
$env:COACH_LAN_FRONTEND_PORT = "$Port"
$keyFile = Join-Path $repoRoot '.tmp/tri-ocr-v2-runtime/service-token.txt'
if ($Lab -and (Test-Path -LiteralPath $keyFile)) {
    $env:OCR_V2_SIDECAR_URL = 'http://127.0.0.1:8031'
    $env:OCR_V2_SIDECAR_TOKEN = [IO.File]::ReadAllText($keyFile).Trim()
}
Push-Location -LiteralPath $frontend
try {
    if ($Lan) { & node (Join-Path $repoRoot 'tools/lan-dev.cjs') --port $Port }
    else { & node node_modules/next/dist/bin/next dev --hostname $HostName --port $Port }
    $code = $LASTEXITCODE
}
finally { Pop-Location }
if ($code -ne 0) { throw "Frontend stopped with exit $code" }
