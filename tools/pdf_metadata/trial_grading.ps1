param(
    [Parameter(Mandatory=$true)][string]$Job,
    [string]$Cohort,
    [string]$Runtime,
    [switch]$Open
)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'paths.ps1')
$trialRepo=(Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..\..')).Path
if (-not $Runtime) { $Runtime=$PdfRuntimeRoot }
$Runtime=[IO.Path]::GetFullPath($Runtime)
if (-not $Cohort) { $Cohort=Join-Path $PSScriptRoot 'tests\fixtures\calculus-cohort-12.v1.json' }
$Job=(Resolve-Path -LiteralPath $Job).Path
$Cohort=(Resolve-Path -LiteralPath $Cohort).Path
$python=Join-Path $Runtime '.venv\Scripts\python.exe'
$env:PYTHONPATH=$PSScriptRoot;$env:PYTHONUTF8='1';$env:PYTHONIOENCODING='utf-8';$env:PYTHONDONTWRITEBYTECODE='1'
& $python -B -u -m pdfmeta.grading_trial all --job $Job --cohort $Cohort
if ($LASTEXITCODE) { throw 'Grading trial failed; inspect the source cohort or scenario feedback.' }
$url=& $python -B -m pdfmeta.progress ensure --root (Split-Path -Parent $Job) --runtime $Runtime
if ($LASTEXITCODE) { throw 'The trial completed but the dashboard could not open.' }
$reviewUrl=($url | Select-Object -Last 1).Trim()+'artifacts/'+(Split-Path -Leaf $Job)+'/grading-trial/review.html'
Write-Host "Sandbox review: $reviewUrl"
if ($Open) { Start-Process $reviewUrl }
