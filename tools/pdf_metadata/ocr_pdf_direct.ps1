param(
    [Parameter(Mandatory=$true)][string]$Pdf,
    [string]$Storage,
    [string]$Output,
    [string]$Pages='all',
    [ValidateRange(72,400)][int]$Dpi=240,
    [ValidateRange(256,8192)][int]$MaxTokens=2048,
    [ValidateRange(1,100)][int]$MaxCallsPerRegion=24,
    [ValidateRange(0,4)][int]$MaxSplitDepth=2,
    [switch]$Open
)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'paths.ps1')
if (-not $Storage) { $Storage=$PdfStorageRoot }
$Storage=[IO.Path]::GetFullPath($Storage);$Pdf=(Resolve-Path -LiteralPath $Pdf).Path
$directRuntime=Join-Path $Storage 'pdf-pipeline-runtime'
$directPython=Join-Path $directRuntime '.venv\Scripts\python.exe'
if (-not $Output) {
    $directId=(Get-FileHash -LiteralPath $Pdf -Algorithm SHA256).Hash.ToLowerInvariant().Substring(0,24)
    $Output=Join-Path $Storage ('pdf-jobs\'+$directId+'\direct-ocr-'+[Guid]::NewGuid().ToString('N').Substring(0,8))
}
$Output=[IO.Path]::GetFullPath($Output)
$env:PYTHONPATH=$PSScriptRoot;$env:PYTHONUTF8='1';$env:PYTHONIOENCODING='utf-8';$env:PYTHONDONTWRITEBYTECODE='1'
$directManifest=Get-Content -LiteralPath (Join-Path $directRuntime 'local-qwen-runtime.json') -Raw -Encoding UTF8 | ConvertFrom-Json
$directExisting=@(Get-CimInstance Win32_Process -Filter "Name='llama-server.exe'" | Where-Object { $_.ExecutablePath -eq $directManifest.server_path -and $_.CommandLine -like '*qwen3-vl-2b-instruct*' })
# Layout runs in its own process and releases Paddle before starting Qwen.
& $directPython -B -u -m pdfmeta.direct_pdf_layout --pdf $Pdf --runtime $directRuntime --output $Output --pages $Pages --dpi $Dpi
if ($LASTEXITCODE) {throw "Layout acquisition stopped. Keep the output to resume: $Output"}
try {
    & (Join-Path $PSScriptRoot 'local_model.ps1') -Action start -Runtime $directRuntime
    $directReady=$false
    for ($directAttempt=0;$directAttempt -lt 120;$directAttempt++) {
        try { $directReady=(Invoke-RestMethod -Uri 'http://127.0.0.1:8790/health' -TimeoutSec 2).status -eq 'ok' } catch {}
        if ($directReady) {break};Start-Sleep -Seconds 1
    }
    if (-not $directReady) {throw 'Local Qwen server is not ready.'}
    & $directPython -B -u -m pdfmeta.direct_pdf_ocr --pdf $Pdf --runtime $directRuntime --output $Output --pages $Pages --dpi $Dpi --max-tokens $MaxTokens --max-calls-per-region $MaxCallsPerRegion --max-split-depth $MaxSplitDepth
    $directExit=$LASTEXITCODE
    if ($directExit -ne 0 -and $directExit -ne 2) {throw "Direct PDF OCR stopped. Keep the output to resume: $Output"}
    Write-Host ('Markdown: '+(Join-Path $Output 'document.ocr.md'))
    Write-Host ('JSON: '+(Join-Path $Output 'pages.ocr.pretty.json'))
    Write-Host ('Question content: '+(Join-Path $Output 'content.draft.pretty.json'))
    Write-Host ('Review: '+(Join-Path $Output 'review.html'))
    $directSummary=Get-Content -LiteralPath (Join-Path $Output 'summary.json') -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($directSummary.failed_regions -gt 0) {
        Write-Warning "$($directSummary.failed_regions) region(s) remain incomplete; other regions were exported. See failures.json. Run the same command to resume."
    } elseif ($directSummary.review_regions -gt 0) {
        Write-Warning "$($directSummary.review_regions) region(s) require source review; see summary.json."
    }
    if ($Open) {Invoke-Item -LiteralPath (Join-Path $Output 'review.html')}
    if ($directExit -eq 2) {exit 2}
} finally {
    if (-not $directExisting.Count) { & (Join-Path $PSScriptRoot 'local_model.ps1') -Action stop -Runtime $directRuntime }
}
