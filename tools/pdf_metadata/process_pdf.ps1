param(
    [Parameter(Position=0)][string]$Pdf,
    [string]$Storage,
    [switch]$SkipQwen,
    [ValidateRange(0,100000)][int]$ReviewLimit=0,
    [switch]$Open,
    [switch]$NoProgress,
    [ValidateRange(0,100000)][int]$VisualLimit=12,
    [switch]$SkipImageCheck,
    [ValidateRange(1024,65525)][int]$ProgressPort=8789
)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'paths.ps1')
$repoRoot=(Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..\..')).Path
if (-not $Pdf) { $Pdf=Read-Host 'Enter the PDF file path' }
$Pdf=$Pdf.Trim().Trim('"')
if (-not (Test-Path -LiteralPath $Pdf -PathType Leaf)) { throw 'PDF file not found.' }
$Pdf=(Resolve-Path -LiteralPath $Pdf).Path
if ([IO.Path]::GetExtension($Pdf) -ine '.pdf') { throw 'Select a PDF file.' }
if (-not $Storage) {
    $Storage=$PdfStorageRoot
}
$Storage=[IO.Path]::GetFullPath($Storage)
$runtime=Join-Path $Storage 'pdf-pipeline-runtime'
$env:PDFMETA_RUNTIME_ROOT=$runtime
$jobs=Join-Path $Storage 'pdf-jobs'
foreach ($folder in @($runtime,$jobs,(Join-Path $runtime 'temp'),(Join-Path $runtime 'pip-cache'))) {
    New-Item -ItemType Directory -Force -Path $folder | Out-Null
}
$env:TEMP=Join-Path $runtime 'temp'
$env:TMP=$env:TEMP
$env:PIP_CACHE_DIR=Join-Path $runtime 'pip-cache'
$env:PYTHONUTF8='1'
$env:PYTHONIOENCODING='utf-8'
$env:PYTHONDONTWRITEBYTECODE='1'
$env:PYTHONPATH=$PSScriptRoot
$python=Join-Path $runtime '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) {
    & py -3.13 -m venv (Join-Path $runtime '.venv')
    if ($LASTEXITCODE) { throw 'Python 3.13 is required for the local Windows environment.' }
}
$dependencyState=@'
try:
    import pdfplumber, PIL, sympy, jsonschema, psutil, httpx
    import importlib.metadata as m
    m.version('paddleocr'); m.version('paddlepaddle')
    print('READY')
except Exception:
    print('MISSING')
'@ | & $python -B -
if ($LASTEXITCODE -or $dependencyState -notcontains 'READY') {
    & $python -m pip install -r (Join-Path $PSScriptRoot 'requirements-paddle.txt')
    if ($LASTEXITCODE) { throw 'Local dependency installation failed. Run this command again to resume.' }
}
$digest=(Get-FileHash -LiteralPath $Pdf -Algorithm SHA256).Hash.ToLowerInvariant()
$documentJob=Join-Path $jobs $digest.Substring(0,24)
$dashboardUrl=$null
if (-not $NoProgress) {
    try {
        $dashboardBase=& $python -B -m pdfmeta.progress ensure --root $jobs --runtime $runtime --port $ProgressPort
        if ($LASTEXITCODE) { throw 'Progress dashboard unavailable.' }
        $dashboardUrl=($dashboardBase | Select-Object -Last 1).Trim()+'?job='+$digest.Substring(0,24)
        Write-Host "Progress: $dashboardUrl"
        if ($Open) { Start-Process $dashboardUrl }
    } catch { Write-Warning 'Progress dashboard could not open. PDF processing will continue; see the console log.'; $dashboardUrl=$null }
}
& $python -B -u -m pdfmeta.pdf_workflow --pdf $Pdf --repo $repoRoot --output-root $jobs --runtime $runtime
if ($LASTEXITCODE) { throw 'PDF processing stopped. Keep the output folder and run the same PDF again to resume.' }
$review=Join-Path (Join-Path $jobs $digest.Substring(0,24)) 'review.html'
$completeArgs=@('-B','-u','-m','pdfmeta.document_pipeline','--job',$documentJob,'--runtime',$runtime,'--repo',$repoRoot,'--rules-only')
if (-not $SkipQwen) {
    try {
        & (Join-Path $PSScriptRoot 'review_pdf.ps1') -Job $documentJob -Runtime $runtime -Limit $ReviewLimit
    } catch {
        Write-Warning 'The local model stage stopped. Exporting a partial final result with source and rule-based LaTeX; rerun to resume Qwen.'
        & $python @completeArgs
        if ($LASTEXITCODE) { throw 'Final artifact generation failed. Source extraction and checkpoints remain available.' }
    }
} else {
    & $python @completeArgs
    if ($LASTEXITCODE) { throw 'Final artifact generation failed.' }
}
$review=Join-Path $documentJob 'final.html'
if ($SkipImageCheck) {
    & $python -B -u -m pdfmeta.readiness export --job $documentJob
} else {
    & $python -B -u -m pdfmeta.readiness all --job $documentJob --runtime $runtime --limit $VisualLimit
}
if ($LASTEXITCODE) { throw 'Image/core checks stopped. The final draft remains available; rerun to resume.' }
Write-Host "Review: $review"
if ($dashboardUrl) { Write-Host "Progress: $dashboardUrl" }
if ($Open -and -not $dashboardUrl) { Invoke-Item -LiteralPath $review }
