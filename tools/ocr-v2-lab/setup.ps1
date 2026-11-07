param([string]$Python = 'python', [switch]$WithV3)
$ErrorActionPreference='Stop'
$taskRoot=Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$taskVenv=Join-Path $taskRoot '.tmp/tri-ocr-v2-runtime/venv'
if (!(Test-Path -LiteralPath (Join-Path $taskVenv 'Scripts/python.exe'))) {
  & $Python -m venv $taskVenv
  if ($LASTEXITCODE -ne 0) { throw 'venv creation failed; use Python 3.12' }
}
$taskPython=Join-Path $taskVenv 'Scripts/python.exe'
& $taskPython -m pip install -r (Join-Path $PSScriptRoot 'requirements-lock.txt')
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed' }
& $taskPython (Join-Path $PSScriptRoot 'download_models.py') --model M
if ($LASTEXITCODE -ne 0) { throw 'Official model download failed' }
if ($WithV3) { & $taskPython (Join-Path $PSScriptRoot 'download_models.py') --model V3; if ($LASTEXITCODE -ne 0) { throw 'V3 download failed' } }
Write-Host 'Setup complete. Run: node tools/ocr-v2-lab/manage.cjs start'
