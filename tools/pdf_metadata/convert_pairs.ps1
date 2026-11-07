param(
    [Parameter(Position=0,Mandatory=$true)][string]$Pdf,
    [string]$Storage,
    [switch]$Open
)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'paths.ps1')
$pairRepo=(Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..\..')).Path
if (-not $Storage) { $Storage=$PdfStorageRoot }
$Storage=[IO.Path]::GetFullPath($Storage)
$Pdf=(Resolve-Path -LiteralPath $Pdf.Trim().Trim('"')).Path
if ([IO.Path]::GetExtension($Pdf) -ine '.pdf') { throw 'Select a PDF file.' }
$runtime=Join-Path $Storage 'pdf-pipeline-runtime'
$pairPython=Join-Path $runtime '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pairPython)) { throw 'Initialize the existing local environment with process_pdf.ps1 first.' }
$env:PYTHONPATH=$PSScriptRoot
$env:PYTHONUTF8='1';$env:PYTHONIOENCODING='utf-8';$env:PYTHONDONTWRITEBYTECODE='1'
$env:TEMP=Join-Path $runtime 'temp';$env:TMP=$env:TEMP
$jobs=Join-Path $Storage 'pdf-jobs'
& $pairPython -B -u -m pdfmeta.paired convert --pdf $Pdf --jobs $jobs
if ($LASTEXITCODE) { throw 'Conversion stopped. Keep checkpoints and rerun to resume.' }
$pairDigest=(Get-FileHash -LiteralPath $Pdf -Algorithm SHA256).Hash.ToLowerInvariant().Substring(0,24)
$pairReport=Get-Content -LiteralPath (Join-Path (Join-Path $jobs $pairDigest) 'paired.json') -Raw | ConvertFrom-Json
Write-Host ('Single file: '+$pairReport.single_file_html)
Write-Host ('Metadata: '+$pairReport.metadata_json)
if ($Open) { Invoke-Item -LiteralPath $pairReport.single_file_html }
