param(
    [Parameter(Position=0,Mandatory=$true)][string]$Pdf,
    [ValidateSet('native','ocr')][string]$Profile='native',
    [string]$Storage,
    [ValidateSet(1,2)][int]$Workers=2,
    [ValidateRange(30,86400)][int]$Timeout=1800,
    [ValidateRange(1024,1048576)][int]$MemoryLimitMB=8192,
    [switch]$Open
)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'paths.ps1')
$datasetRepo=(Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..\..')).Path
if (-not $Storage) { $Storage = $PdfStorageRoot }
$Storage=[IO.Path]::GetFullPath($Storage)

$Pdf=(Resolve-Path -LiteralPath $Pdf.Trim().Trim('"')).Path
$datasetRuntime=Join-Path $Storage 'pdf-pipeline-runtime'
$datasetPython=Join-Path $datasetRuntime '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $datasetPython)) {throw 'Initialize the existing PDF environment using process_pdf.ps1 first.'}
$env:PYTHONPATH=$PSScriptRoot;$env:PYTHONUTF8='1';$env:PYTHONIOENCODING='utf-8';$env:PYTHONDONTWRITEBYTECODE='1'
& $datasetPython -B -u -m pdfmeta.dataset_workflow --pdf $Pdf --storage $Storage --repo $datasetRepo --profile $Profile --workers $Workers --timeout $Timeout --memory-limit-mb $MemoryLimitMB
if ($LASTEXITCODE) {throw 'Dataset is partial. Check progress.json and chunk logs; rerun the same command to resume.'}
$datasetDigest=(Get-FileHash -LiteralPath $Pdf -Algorithm SHA256).Hash.ToLower().Substring(0,24)
$datasetSummary=Get-Content -LiteralPath (Join-Path $Storage "pdf-jobs\$datasetDigest\dataset-final.json") -Raw | ConvertFrom-Json
Write-Host ('Final metadata: '+$datasetSummary.final_jsonl)
Write-Host ('Review: '+$datasetSummary.review)
if ($Open) {
    $datasetJobs=Join-Path $Storage 'pdf-jobs'
    $datasetBase=(& $datasetPython -B -m pdfmeta.progress ensure --root $datasetJobs --runtime $datasetRuntime --port 8789 | Select-Object -Last 1).Trim()
    $datasetRelative=$datasetSummary.review.Substring($datasetJobs.TrimEnd('\').Length+1).Replace('\','/')
    Start-Process -FilePath ($datasetBase.TrimEnd('/')+'/artifacts/'+$datasetRelative)
}
