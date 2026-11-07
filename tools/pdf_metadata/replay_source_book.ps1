param(
    [Parameter(Position=0)][string]$Pdf='.local\source_pdfs\math12\Toan12-001.pdf',
    [string]$Sources,
    [string]$ReferenceJson,
    [string]$Storage,
    [string]$Output,
    [ValidateSet('native','ocr')][string]$Profile='ocr',
    [ValidateSet(1,2)][int]$Workers=1,
    [ValidateRange(1024,1048576)][int]$MemoryLimitMB=4096,
    [ValidateRange(30,86400)][int]$Timeout=7200,
    [switch]$Open,
    [switch]$PlanOnly
)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'paths.ps1')
$replayRepo=(Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..\..')).Path
if (-not $Storage) { $Storage=$PdfStorageRoot }
if (-not $Sources) { $Sources=Join-Path $replayRepo '.local\source_pdfs\math12' }
$Storage=[IO.Path]::GetFullPath($Storage)
$Pdf=(Resolve-Path -LiteralPath $Pdf).Path;$Sources=(Resolve-Path -LiteralPath $Sources).Path
$replayRuntime=Join-Path $Storage 'pdf-pipeline-runtime'
$replayPython=Join-Path $replayRuntime '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $replayPython)) {throw 'Local PDF Python environment missing.'}
$replayJobs=Join-Path $Storage 'pdf-jobs'
if (-not $Output) {
    $replayId=(Get-FileHash -LiteralPath $Pdf -Algorithm SHA256).Hash.ToLowerInvariant().Substring(0,24)
    $Output=Join-Path $replayJobs ($replayId+'\source-replay-'+[Guid]::NewGuid().ToString('N').Substring(0,8))
}
$Output=[IO.Path]::GetFullPath($Output)
$env:PYTHONPATH=$PSScriptRoot;$env:PYTHONUTF8='1';$env:PYTHONIOENCODING='utf-8'
$env:PYTHONDONTWRITEBYTECODE='1';$env:PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK='True'
$env:PDFMETA_STORAGE_ROOT=$Storage;$env:PDFMETA_RUNTIME_ROOT=$replayRuntime
Write-Host 'Reading matching original PDFs using source references in the book.'
Write-Host 'This run preserves original PDF text/fonts; it does not OCR the book images.'
$replayArgs=@('-B','-u','-m','pdfmeta.paired.source_book_replay','--pdf',$Pdf,'--sources',$Sources,
    '--storage',$Storage,'--repo',$replayRepo,'--output',$Output,'--profile',$Profile,
    '--workers',$Workers,'--timeout',$Timeout,'--memory-limit-mb',$MemoryLimitMB)
if ($ReferenceJson) { $replayArgs+=@('--reference',(Resolve-Path -LiteralPath $ReferenceJson).Path) }
if ($PlanOnly) { $replayArgs+='--plan-only' }
& $replayPython @replayArgs
if ($LASTEXITCODE) {throw 'Original-source replay incomplete. Inspect the source-replay manifest and chunk logs.'}
if ($PlanOnly) { Write-Host ('Plan verified: '+$Output); return }
Write-Host ('Text/LaTeX: '+(Join-Path $Output 'transcription\content.draft.pretty.json'))
if ($Open) {
    $replayBase=(& $replayPython -B -m pdfmeta.progress ensure --root $replayJobs --runtime $replayRuntime --port 8789 | Select-Object -Last 1).Trim()
    if ($LASTEXITCODE) {throw 'Could not start the result server.'}
    if (-not $Output.StartsWith($replayJobs.TrimEnd('\')+'\',[StringComparison]::OrdinalIgnoreCase)) {throw 'Open requires an output directory inside pdf-jobs.'}
    $replayRelative=$Output.Substring($replayJobs.TrimEnd('\').Length+1).Replace('\','/')
    Start-Process -FilePath ($replayBase.TrimEnd('/')+'/artifacts/'+$replayRelative+'/transcription/review.html')
}
