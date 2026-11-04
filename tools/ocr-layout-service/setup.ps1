param([string]$Python = 'python')
$ErrorActionPreference='Stop'
$taskRoot=Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$taskRuntime=Join-Path $taskRoot '.tmp/ocr-layout'
$taskPython=Join-Path $taskRuntime 'venv/Scripts/python.exe'
if (!(Test-Path -LiteralPath $taskPython)) {
  & $Python -m venv (Join-Path $taskRuntime 'venv')
  if ($LASTEXITCODE -ne 0) { throw 'Use Python 3.12 to create the isolated layout environment' }
}
& $taskPython -m pip install -r (Join-Path $PSScriptRoot 'requirements-lock.txt')
if ($LASTEXITCODE -ne 0) { throw 'Layout dependency install failed' }
& $taskPython (Join-Path $PSScriptRoot 'download_models.py') --model M
if ($LASTEXITCODE -ne 0) { throw 'Official model download/checksum validation failed' }
$taskToken=Join-Path $taskRuntime 'service-token.txt'
if (!(Test-Path -LiteralPath $taskToken)) {
  & $taskPython -c "import secrets,pathlib,sys; pathlib.Path(sys.argv[1]).write_text(secrets.token_hex(32))" $taskToken
  if ($LASTEXITCODE -ne 0) { throw 'Could not create local service token' }
}
Write-Host 'Optional Layout-M installed. See docs/ocr-v2/TEAM_HANDOFF.md. No model starts or downloads during application requests.'
