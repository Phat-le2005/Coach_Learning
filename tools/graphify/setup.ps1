param([string]$Python = 'python')
$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$venvPath = Join-Path $repoRoot '.tmp/graphify-runtime/.venv'
$pythonPath = Join-Path $venvPath 'Scripts/python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) {
    & $Python -m venv $venvPath
    if ($LASTEXITCODE -ne 0) { throw 'Could not create Graphify virtualenv.' }
}
& $pythonPath -m pip install --disable-pip-version-check -r (Join-Path $PSScriptRoot 'requirements.txt')
if ($LASTEXITCODE -ne 0) { throw 'Graphify installation failed.' }
Push-Location -LiteralPath $repoRoot
try {
    & $pythonPath (Join-Path $PSScriptRoot 'configure.py')
    if ($LASTEXITCODE -ne 0) { throw 'Codex project configuration failed.' }
} finally { Pop-Location }
Write-Output 'Ready. Run tools/graphify/build.ps1, then reopen Codex to load the project MCP server.'
