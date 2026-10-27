[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONNOUSERSITE = "1"
$OutputEncoding = [System.Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = $OutputEncoding
$backendDirectory = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectDirectory = Split-Path -Parent $backendDirectory
$python = Join-Path $projectDirectory ".conda\python.exe"
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    $python = Join-Path $backendDirectory ".venv\Scripts\python.exe"
}

if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    throw "Project environment is missing. See docs/local-setup.md to create .conda."
}

# Conda's DLLs must be discoverable even when this launcher is used without activation.
$originalPath = $env:PATH
if ($python -eq (Join-Path $projectDirectory ".conda\python.exe")) {
    $prefix = Join-Path $projectDirectory ".conda"
    $env:PATH = "$prefix;$prefix\Library\bin;$prefix\Scripts;$env:PATH"
}

Push-Location $backendDirectory
try {
    & $python -m app
    if ($LASTEXITCODE -ne 0) {
        throw "EduMS backend exited with code $LASTEXITCODE."
    }
}
finally {
    Pop-Location
    $env:PATH = $originalPath
}
