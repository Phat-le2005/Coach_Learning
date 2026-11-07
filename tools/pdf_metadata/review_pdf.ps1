param(
    [Parameter(Mandatory=$true)][string]$Job,
    [string]$Runtime,
    [ValidateRange(0,100000)][int]$Limit=0,
    [switch]$RetryFailed,
    [switch]$Open
)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'paths.ps1')
$reviewRepo=(Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..\..')).Path
if (-not $Runtime) { $Runtime=$PdfRuntimeRoot }
$Runtime=[IO.Path]::GetFullPath($Runtime)
$env:PDFMETA_RUNTIME_ROOT=$Runtime
$Job=(Resolve-Path -LiteralPath $Job).Path
$env:PYTHONPATH=$PSScriptRoot
$env:PYTHONUTF8='1'
$env:PYTHONIOENCODING='utf-8'
$env:PYTHONDONTWRITEBYTECODE='1'
$reviewPython=Join-Path $Runtime '.venv\Scripts\python.exe'
& $reviewPython -B -m pdfmeta.progress model-loading --job $Job
$reviewManifest=Join-Path $Runtime 'local-qwen-runtime.json'
if (-not (Test-Path -LiteralPath $reviewManifest)) {
    & $reviewPython -B -u -m pdfmeta.local_setup --runtime $Runtime
    if ($LASTEXITCODE) { throw 'Local Qwen setup failed.' }
}
$reviewConfig=Get-Content -LiteralPath $reviewManifest -Raw -Encoding UTF8 | ConvertFrom-Json
$existingServer=@(Get-CimInstance Win32_Process -Filter "Name='llama-server.exe'" | Where-Object {
    $_.ExecutablePath -eq $reviewConfig.server_path -and $_.CommandLine -like '*qwen3-vl-2b-instruct*'
})
try {
    & (Join-Path $PSScriptRoot 'local_model.ps1') -Action start -Runtime $Runtime
    if ($LASTEXITCODE) { throw 'Local Qwen did not start.' }
    $ready=$false
    $reviewDeadline=(Get-Date).AddSeconds(120)
    do {
        try {
            $health=Invoke-RestMethod -Uri 'http://127.0.0.1:8790/health' -TimeoutSec 2
            $ready=$health.status -eq 'ok'
        } catch { $ready=$false }
        if (-not $ready) { Start-Sleep -Seconds 1 }
    } until ($ready -or (Get-Date) -ge $reviewDeadline)
    if (-not $ready) { throw 'Local Qwen is not ready; metadata remains available.' }
    $reviewArgs=@('-B','-u','-m','pdfmeta.document_pipeline','--job',$Job,'--runtime',$Runtime,'--repo',$reviewRepo,'--limit',$Limit)
    if ($RetryFailed) { $reviewArgs+='--retry-failed' }
    & $reviewPython @reviewArgs
    if ($LASTEXITCODE) { throw 'Qwen review stopped. Per-question checkpoints remain available.' }
} finally {
    if (-not $existingServer.Count) {
        & (Join-Path $PSScriptRoot 'local_model.ps1') -Action stop -Runtime $Runtime
    }
}
$reviewPage=Join-Path $Job 'final.html'
Write-Host "Final review: $reviewPage"
if ($Open) { Invoke-Item -LiteralPath $reviewPage }
