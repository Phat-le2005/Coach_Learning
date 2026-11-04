param(
    [Parameter(Position=0,Mandatory=$true)][string[]]$Inputs,
    [string]$Storage,
    [ValidateRange(0,100000)][int]$ReviewLimit=3,
    [ValidateRange(0,100000)][int]$VisualLimit=8,
    [ValidateRange(0,100000)][int]$MaxPages=100,
    [ValidateRange(0,100000)][int]$MaxPdfs=0,
    [ValidateRange(30,86400)][int]$Timeout=3600,
    [ValidateSet('run','defer')][string]$OversizePolicy='run',
    [switch]$SkipQwen,
    [switch]$RetryFailed,
    [switch]$Open
)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'paths.ps1')
$corpusRepo=(Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..\..')).Path
if (-not $Storage) { $Storage=$PdfStorageRoot }
$Storage=[IO.Path]::GetFullPath($Storage)
$runtime=Join-Path $Storage 'pdf-pipeline-runtime'
$env:PDFMETA_RUNTIME_ROOT=$runtime
$corpusPython=Join-Path $runtime '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $corpusPython)) { throw 'Initialize the local environment by running process_pdf.ps1 on one PDF first.' }
$env:PYTHONPATH=$PSScriptRoot
$env:PYTHONUTF8='1';$env:PYTHONIOENCODING='utf-8';$env:PYTHONDONTWRITEBYTECODE='1'
$env:TEMP=Join-Path $runtime 'temp';$env:TMP=$env:TEMP
$jobs=Join-Path $Storage 'pdf-jobs'
$url=& $corpusPython -B -m pdfmeta.progress ensure --root $jobs --runtime $runtime
if ($LASTEXITCODE) { throw 'Progress dashboard failed to start.' }
Write-Host "Progress: $url"
if ($Open) { Start-Process ($url | Select-Object -Last 1) }
$arguments=@('-B','-u','-m','pdfmeta.readiness','batch','--repo',$corpusRepo,'--storage',$Storage,
    '--review-limit',$ReviewLimit,'--visual-limit',$VisualLimit,'--max-pages',$MaxPages,'--max-pdfs',$MaxPdfs,'--timeout',$Timeout,'--oversize-policy',$OversizePolicy)
if ($SkipQwen) { $arguments+='--skip-qwen' }
if ($RetryFailed) { $arguments+='--retry-failed' }
$arguments+='--'
$arguments+=@($Inputs | ForEach-Object { (Resolve-Path -LiteralPath $_.Trim().Trim('"')).Path })
& $corpusPython @arguments
if ($LASTEXITCODE) { throw 'Queue stopped. Check queue.json and rerun to resume.' }
