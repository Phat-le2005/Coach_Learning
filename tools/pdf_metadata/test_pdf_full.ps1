param(
    [Parameter(Position=0)][string]$Pdf='.local\source_pdfs\math12\Toan12-001.pdf',
    [string]$Storage,
    [ValidateSet(1,2)][int]$Workers=1,
    [ValidateRange(1024,1048576)][int]$MemoryLimitMB=4096,
    [ValidateRange(30,86400)][int]$Timeout=14400,
    [switch]$Open
)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'paths.ps1')
$fullRepo=(Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..\..')).Path
if (-not $Storage) { $Storage=$PdfStorageRoot }
$Storage=[IO.Path]::GetFullPath($Storage)
$Pdf=(Resolve-Path -LiteralPath $Pdf.Trim().Trim('"')).Path
if ([IO.Path]::GetExtension($Pdf) -ine '.pdf') { throw 'Select a PDF file.' }
$fullRuntime=Join-Path $Storage 'pdf-pipeline-runtime'
$fullPython=Join-Path $fullRuntime '.venv\Scripts\python.exe'
$fullKatex=Join-Path $fullRepo 'frontend\node_modules\katex\dist'
foreach ($required in @($fullPython,(Join-Path $fullRuntime 'local-qwen-runtime.json'),(Join-Path $fullKatex 'katex.js'))) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) { throw "Required local file missing: $required" }
}
foreach ($model in @('PP-FormulaNet_plus-M','PP-FormulaNet_plus-S')) {
    if (-not (Test-Path -LiteralPath (Join-Path $fullRuntime "paddlex\official_models\$model\inference.pdiparams"))) {
        throw "Install the local formula model first: $model"
    }
}
$env:PDFMETA_STORAGE_ROOT=$Storage;$env:PDFMETA_RUNTIME_ROOT=$fullRuntime
$env:PYTHONPATH=$PSScriptRoot;$env:PYTHONUTF8='1';$env:PYTHONIOENCODING='utf-8'
$env:PYTHONDONTWRITEBYTECODE='1';$env:PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK='True'
$fullDigest=(Get-FileHash -LiteralPath $Pdf -Algorithm SHA256).Hash.ToLowerInvariant()
$fullJobs=Join-Path $Storage 'pdf-jobs';$fullJob=Join-Path $fullJobs $fullDigest.Substring(0,24)
$fullOutput=Join-Path $fullJob ('full-local-'+(Get-Date -Format 'yyyyMMdd-HHmmss'))
New-Item -ItemType Directory -Path $fullOutput -Force | Out-Null
$fullLog=Join-Path $fullOutput 'run.log'
function Assert-FullPdfStep([string]$Step) {
    if ($LASTEXITCODE -ne 0) { throw "Stopped at $Step (exit $LASTEXITCODE). See $fullLog" }
}
Start-Transcript -LiteralPath $fullLog | Out-Null
try {
    Write-Host '[1/8] Native text, text OCR, formula layout/OCR, tables, math and solution steps'
    Write-Host 'PP-DocLayoutV3 is downloaded into the configured runtime on first use if missing.'
    & $fullPython -B -u -m pdfmeta.pdf_workflow --pdf $Pdf --repo $fullRepo --output-root $fullJobs --runtime $fullRuntime
    Assert-FullPdfStep 'document extraction'
    Write-Host '[2/8] Qwen metadata/LaTeX review: all discovered questions'
    & (Join-Path $PSScriptRoot 'review_pdf.ps1') -Job $fullJob -Runtime $fullRuntime -Limit 0 -RetryFailed
    Assert-FullPdfStep 'Qwen document review'
    Write-Host '[3/8] Formula image verification: all located regions, FormulaNet'
    & (Join-Path $PSScriptRoot 'verify_images.ps1') -Job $fullJob -Runtime $fullRuntime -Engine ocr -Limit 0 -RetryFailed
    Assert-FullPdfStep 'OCR image verification'
    Write-Host '[4/8] Formula image verification: all located regions, Qwen'
    & (Join-Path $PSScriptRoot 'verify_images.ps1') -Job $fullJob -Runtime $fullRuntime -Engine qwen -Limit 0 -RetryFailed
    Assert-FullPdfStep 'Qwen image verification'
    & $fullPython -B -m pdfmeta.readiness export --job $fullJob
    Assert-FullPdfStep 'core contract export'
    Write-Host '[5/8] Whole-PDF paired dataset and curation'
    & (Join-Path $PSScriptRoot 'build_dataset.ps1') -Pdf $Pdf -Storage $Storage -Profile ocr -Workers $Workers -MemoryLimitMB $MemoryLimitMB -Timeout $Timeout
    Assert-FullPdfStep 'paired dataset'
    $fullDataset=Get-Content -LiteralPath (Join-Path $fullJob 'dataset-final.json') -Raw -Encoding UTF8 | ConvertFrom-Json
    $fullSourceRoot=Split-Path -Parent $fullDataset.final_directory
    $fullMetadata=Join-Path $fullSourceRoot 'questions.source.jsonl';$fullPlan=Join-Path $fullSourceRoot 'plan.json'
    if ($fullDataset.questions -lt 1) { throw 'No paired questions for v2. Inspect the source review queue.' }
    Write-Host '[6/8] Transcription v2: all pairs, followed by Qwen vision diagnostics'
    Write-Host 'V2 vision checks one selected region per question; embedded images may remain source images.'
    $fullV2=Join-Path $fullOutput 'transcription-v2'
    & (Join-Path $PSScriptRoot 'transcribe_corpus.ps1') -Metadata $fullMetadata -Plan $fullPlan -Output $fullV2 -Storage $Storage -Runtime $fullRuntime -Version v2 -All -Workers $Workers -MemoryLimitMB $MemoryLimitMB -RunTimeout $Timeout -CacheMode cold
    Assert-FullPdfStep 'transcription v2 and vision diagnostics'
    Write-Host '[7/8] Curated export from the separate v2 test'
    $fullCurated=Join-Path $fullOutput 'curated-v2'
    & $fullPython -B -u -m pdfmeta.curation --transcripts $fullV2 --output $fullCurated --plan $fullPlan --katex $fullKatex
    Assert-FullPdfStep 'v2 curation'
    Write-Host '[8/8] Result server and links'
    $fullBase=(& $fullPython -B -m pdfmeta.progress ensure --root $fullJobs --runtime $fullRuntime --port 8789 | Select-Object -Last 1)
    Assert-FullPdfStep 'result server'
    $fullBase=$fullBase.Trim().TrimEnd('/')
    $fullRelative=$fullOutput.Substring($fullJobs.TrimEnd('\').Length+1).Replace('\','/')
    $fullDocumentUrl=$fullBase+'/artifacts/'+$fullDigest.Substring(0,24)+'/final.html'
    $fullV2Url=$fullBase+'/artifacts/'+$fullRelative+'/transcription-v2/review.html'
    $fullCuratedUrl=$fullBase+'/artifacts/'+$fullRelative+'/curated-v2/index.html'
    Write-Host "Document pipeline: $fullDocumentUrl"
    Write-Host "V2 + vision diagnostics: $fullV2Url"
    Write-Host "Curated v2: $fullCuratedUrl"
    Write-Host "Full log: $fullLog"
    Write-Host 'Completed the applicable local workflows. Consult model call counts and review flags for actual coverage.'
    if ($Open) { Start-Process -FilePath $fullDocumentUrl; Start-Process -FilePath $fullV2Url }
} finally {
    Stop-Transcript | Out-Null
}
