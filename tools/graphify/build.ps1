param([switch]$Full)
$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$pythonPath = Join-Path $repoRoot '.tmp/graphify-runtime/.venv/Scripts/python.exe'
$extractArgs = @('extract', '.', '--code-only', '--max-workers', '2', '--no-dedup', '--timing')
if ($Full) { $extractArgs += '--force' }
& (Join-Path $PSScriptRoot 'graphify.ps1') @extractArgs
& $pythonPath (Join-Path $PSScriptRoot 'export_architecture.py')
if ($LASTEXITCODE -ne 0) { throw 'Architecture export failed.' }
& (Join-Path $PSScriptRoot 'graphify.ps1') export html --node-limit 1800
& (Join-Path $PSScriptRoot 'graphify.ps1') export graphml
Write-Output 'Graph: graphify-out/graph.html | Report: docs/graphify/architecture.md'
