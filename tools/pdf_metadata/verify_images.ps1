param(
    [Parameter(Mandatory=$true)][string]$Job,
    [string]$Runtime,
    [ValidateSet('ocr','qwen')][string]$Engine='ocr',
    [ValidateRange(0,100000)][int]$Limit=12,
    [switch]$RetryFailed
)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'paths.ps1')
$imageRepo=(Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..\..')).Path
if (-not $Runtime) { $Runtime=$PdfRuntimeRoot }
$Runtime=[IO.Path]::GetFullPath($Runtime)
$env:PDFMETA_RUNTIME_ROOT=$Runtime
$Job=(Resolve-Path -LiteralPath $Job).Path
$imagePython=Join-Path $Runtime '.venv\Scripts\python.exe'
$env:PYTHONPATH=$PSScriptRoot;$env:PYTHONUTF8='1';$env:PYTHONIOENCODING='utf-8';$env:PYTHONDONTWRITEBYTECODE='1'
$ownedQwen=$false
try {
    if ($Engine -eq 'qwen') {
        $manifest=Get-Content -LiteralPath (Join-Path $Runtime 'local-qwen-runtime.json') -Raw -Encoding UTF8 | ConvertFrom-Json
        $existing=@(Get-CimInstance Win32_Process -Filter "Name='llama-server.exe'" | Where-Object {
            $_.ExecutablePath -eq $manifest.server_path -and $_.CommandLine -like '*qwen3-vl-2b-instruct*'
        })
        $ownedQwen=-not $existing.Count
        & (Join-Path $PSScriptRoot 'local_model.ps1') -Action start -Runtime $Runtime
        if ($LASTEXITCODE) { throw 'Qwen failed to start.' }
        $deadline=(Get-Date).AddSeconds(120);$ready=$false
        do {
            try { $ready=(Invoke-RestMethod -Uri 'http://127.0.0.1:8790/health' -TimeoutSec 2).status -eq 'ok' } catch { $ready=$false }
            if (-not $ready) { Start-Sleep -Seconds 1 }
        } until ($ready -or (Get-Date) -ge $deadline)
        if (-not $ready) { throw 'Qwen is not ready.' }
    }
    $arguments=@('-B','-u','-m','pdfmeta.readiness','visual','--job',$Job,'--runtime',$Runtime,'--limit',$Limit,'--engine',$Engine)
    if ($RetryFailed) { $arguments+='--retry-failed' }
    & $imagePython @arguments
    if ($LASTEXITCODE) { throw 'Image verification stopped; checkpoints remain available.' }
} finally {
    if ($ownedQwen) { & (Join-Path $PSScriptRoot 'local_model.ps1') -Action stop -Runtime $Runtime }
}
