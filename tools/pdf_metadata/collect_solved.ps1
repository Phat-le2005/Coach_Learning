param(
    [Parameter(Position=0)][string]$InputPath,
    [Parameter(Mandatory=$true)][string]$Work,
    [Parameter(Mandatory=$true)][string]$Output,
    [Parameter(Mandatory=$true)][string]$Archive,
    [ValidateSet('derivative_applications','integrals','grouped_statistics','probability')][string]$Chapter,
    [string]$Storage,
    [string]$PdfPython
)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'paths.ps1')
$solvedRepo=(Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..\..')).Path
if (-not $Storage) { $Storage=$PdfStorageRoot }
$Storage=[IO.Path]::GetFullPath($Storage)
$Work=[IO.Path]::GetFullPath($Work)
$Output=[IO.Path]::GetFullPath($Output)
$runtime=Join-Path $Storage 'pdf-pipeline-runtime'
$solvedPython=Join-Path $runtime '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $solvedPython)) { throw 'Initialize the project PDF environment first.' }
if ($PdfPython -and -not (Test-Path -LiteralPath $PdfPython)) { throw 'PDF renderer Python does not exist.' }
$env:PYTHONPATH=$PSScriptRoot;$env:PYTHONUTF8='1';$env:PYTHONDONTWRITEBYTECODE='1'
$env:TEMP=Join-Path $runtime 'temp';$env:TMP=$env:TEMP
$solvedArgs=@('-B','-u','-m','pdfmeta.paired.solved_workflow','--root',$Work,'--runtime',$runtime,
    '--output',$Output,'--archive',(Resolve-Path -LiteralPath $Archive).Path)
if ($InputPath) { $solvedArgs+=@('--input',(Resolve-Path -LiteralPath $InputPath).Path) }
if ($Chapter) { $solvedArgs+=@('--chapter',$Chapter) }
& $solvedPython @solvedArgs
if ($LASTEXITCODE) { throw 'Collection incomplete. See controller.json and per-document worker.log; rerun to resume.' }
if ($PdfPython) {
    & $PdfPython -B (Join-Path $PSScriptRoot 'pdfmeta\paired\collection_pdf.py') --metadata (Join-Path $Output 'questions.metadata.json') --output (Join-Path $Output 'Toan12_Cau_hoi_co_loi_giai.pdf')
    if ($LASTEXITCODE) { throw 'Source metadata is saved, but PDF export failed.' }
    & $PdfPython -B (Join-Path $PSScriptRoot 'pdfmeta\paired\collection_check.py') --metadata (Join-Path $Output 'cau-hoi-co-loi-giai.metadata.json') --report (Join-Path $Output 'verification.json')
    if ($LASTEXITCODE) { throw 'PDF structural verification failed. See verification.json.' }
    $controllerPath=Join-Path $Work 'controller.json'
    $controller=Get-Content -LiteralPath $controllerPath -Raw | ConvertFrom-Json
    $controller.pdf_export_pending=$false
    $controller.status='COLLECTION_COMPLETE_WITH_REVIEW_QUEUE'
    $controllerJson=$controller | ConvertTo-Json -Depth 50
    [IO.File]::WriteAllText($controllerPath,$controllerJson,[Text.UTF8Encoding]::new($false))
}
Write-Host "Collection: $Output"
if (-not $PdfPython) { Write-Host 'PDF export pending. Supply -PdfPython pointing to Python with ReportLab and Pillow.' }
