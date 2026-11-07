param([switch]$Lan, [int]$Port = 8000, [int]$FrontendPort = 3000)
$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$python = Join-Path $repoRoot 'backend/.venv/Scripts/python.exe'
if (!(Test-Path -LiteralPath $python)) { throw 'Install backend/.venv from requirements-lock.txt first. See LOCAL_SETUP.md.' }
$env:COACH_LAN_MODE = if ($Lan) { '1' } else { '0' }
$env:COACH_LAN_FRONTEND_PORT = "$FrontendPort"
$bindHost = if ($Lan) { '0.0.0.0' } else { '127.0.0.1' }
Push-Location (Join-Path $repoRoot 'backend')
try { & $python -m uvicorn app.main:app --host $bindHost --port $Port --workers 1 --ws-max-size 300000; $code = $LASTEXITCODE }
finally { Pop-Location }
if ($code -ne 0) { throw "Backend stopped with exit $code" }
