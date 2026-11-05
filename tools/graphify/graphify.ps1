param([Parameter(ValueFromRemainingArguments = $true)][string[]]$GraphifyArgs)
$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$pythonPath = Join-Path $repoRoot '.tmp/graphify-runtime/.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) { throw 'Run tools/graphify/setup.ps1 first.' }
$previousUtf8 = $env:PYTHONUTF8
$previousOut = $env:GRAPHIFY_OUT
try {
    $env:PYTHONUTF8 = '1'
    $env:GRAPHIFY_OUT = Join-Path $repoRoot 'graphify-out'
    Push-Location -LiteralPath $repoRoot
    & $pythonPath -m graphify @GraphifyArgs
    $commandExitCode = $LASTEXITCODE
} finally {
    Pop-Location
    $env:PYTHONUTF8 = $previousUtf8
    $env:GRAPHIFY_OUT = $previousOut
}
if ($commandExitCode -ne 0) { throw "Graphify exited with code $commandExitCode" }
