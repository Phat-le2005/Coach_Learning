[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$backendDirectory = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = Join-Path $backendDirectory ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    throw "Backend virtual environment is missing. Run: python -m venv backend\.venv"
}

# A machine-wide DEBUG value is often owned by another tool. Only boolean
# values are valid for EduMS; discard an incompatible inherited value so the
# backend can read DEBUG from backend/.env.
$inheritedDebug = [Environment]::GetEnvironmentVariable("DEBUG", "Process")
if (
    $null -ne $inheritedDebug -and
    $inheritedDebug.Trim().ToLowerInvariant() -notin @(
        "0", "1", "false", "true", "no", "yes", "off", "on"
    )
) {
    Remove-Item Env:DEBUG
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
}
