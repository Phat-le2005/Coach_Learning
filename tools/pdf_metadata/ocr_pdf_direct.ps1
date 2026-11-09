param(
    [Parameter(Mandatory=$true)][string]$Pdf,
    [string]$Storage,
    [string]$Runtime,
    [string]$Output,
    [string]$Pages='all',
    [ValidateRange(72,400)][int]$Dpi=240,
    [ValidateRange(256,8192)][int]$MaxTokens=2048,
    [ValidateRange(1,100)][int]$MaxCallsPerRegion=24,
    [ValidateRange(0,4)][int]$MaxSplitDepth=2,
    [ValidateSet('CPU','GPU')][string]$Device='CPU',
    [ValidateRange(1,65535)][int]$Port=8790,
    [switch]$Open
)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'paths.ps1')
if (-not $Storage) { $Storage=$PdfStorageRoot }
$Storage=[IO.Path]::GetFullPath($Storage);$Pdf=(Resolve-Path -LiteralPath $Pdf).Path
$directRuntime=if ($Runtime) {[IO.Path]::GetFullPath($Runtime)} else {Join-Path $Storage 'pdf-pipeline-runtime'}
$directPython=Join-Path $directRuntime '.venv\Scripts\python.exe'
if (-not $Output) {
    $directId=(Get-PdfFileSha256 -LiteralPath $Pdf).Substring(0,24)
    $Output=Join-Path $Storage ('pdf-jobs\'+$directId+'\direct-ocr-'+[Guid]::NewGuid().ToString('N').Substring(0,8))
}
$Output=[IO.Path]::GetFullPath($Output)
$env:PYTHONPATH=$PSScriptRoot;$env:PYTHONUTF8='1';$env:PYTHONIOENCODING='utf-8';$env:PYTHONDONTWRITEBYTECODE='1'
$directOutputPattern='--output\s+(?:"'+[regex]::Escape($Output)+'"|'+[regex]::Escape($Output)+')(?:\s|$)'
$directActive=@(Get-CimInstance Win32_Process | Where-Object {
    $_.Name -like 'python*' -and $_.CommandLine -match 'pdfmeta\.direct_pdf_(ocr|layout)' -and
    $_.CommandLine -match $directOutputPattern
})
if ($directActive.Count) {throw "This output is still being processed. Stop its current OCR job before resuming: $Output"}
New-Item -ItemType Directory -Path $Output -Force | Out-Null
$directLock=$null;$directStarted=$false
$directOwnsOutput=$false
$directClock=[Diagnostics.Stopwatch]::StartNew()
$directStageClock=$null;$directStageName='';$directSummary=$null
$directPerformance=[ordered]@{version='pdf-pipeline-performance/v1';run_id=[Guid]::NewGuid().ToString('N');
    started_at_utc=[DateTime]::UtcNow.ToString('o');status='FAILED';device=$Device;
    stages_seconds=[ordered]@{};elapsed_seconds=$null;processed_pages=$null;questions=$null;pages_per_minute=$null}
function Stop-DirectStage {
    if ($directStageClock -and $directStageName) {
        $directStageClock.Stop()
        $directPerformance.stages_seconds[$directStageName]=[Math]::Round($directStageClock.Elapsed.TotalSeconds,3)
        Write-Host ('[perf] pipeline '+$directStageName+': '+$directPerformance.stages_seconds[$directStageName]+'s')
    }
}
try {
    try {
        $directLock=[IO.File]::Open((Join-Path $Output '.direct-ocr.lock'),[IO.FileMode]::OpenOrCreate,[IO.FileAccess]::ReadWrite,[IO.FileShare]::None)
        $directOwnsOutput=$true
    }
    catch {throw "Another OCR command owns this output: $Output"}
    if ($Device -eq 'GPU' -and -not (Test-Path -LiteralPath (Join-Path $directRuntime 'local-qwen-runtime.gpu.json'))) {
        & $directPython -B -u -m pdfmeta.local_backend --runtime $directRuntime --setup-gpu
        if ($LASTEXITCODE) {throw 'CUDA setup failed. CPU runtime and existing OCR checkpoints were preserved.'}
    }
    # Layout stays on CPU in its own process and releases Paddle before Qwen.
    $directStageName='layout';$directStageClock=[Diagnostics.Stopwatch]::StartNew()
    & $directPython -B -u -m pdfmeta.direct_pdf_layout --pdf $Pdf --runtime $directRuntime --output $Output --pages $Pages --dpi $Dpi
    Stop-DirectStage
    if ($LASTEXITCODE) {throw "Layout acquisition stopped. Keep the output to resume: $Output"}
    $directStageName='model_start_and_ready';$directStageClock=[Diagnostics.Stopwatch]::StartNew()
    $directServer=& (Join-Path $PSScriptRoot 'local_model.ps1') -Action start -Runtime $directRuntime -Device $Device -Port $Port
    $directStarted=[bool]$directServer.StartedByCaller
    $directReady=$false
    for ($directAttempt=0;$directAttempt -lt 120;$directAttempt++) {
        try { $directReady=(Invoke-RestMethod -Uri "http://127.0.0.1:$Port/health" -TimeoutSec 2).status -eq 'ok' } catch {}
        if ($directReady) {break};Start-Sleep -Seconds 1
    }
    Stop-DirectStage
    if (-not $directReady) {throw 'Local Qwen server is not ready.'}
    $directStageName='ocr_and_export';$directStageClock=[Diagnostics.Stopwatch]::StartNew()
    & $directPython -B -u -m pdfmeta.direct_pdf_ocr --pdf $Pdf --runtime $directRuntime --output $Output --pages $Pages --dpi $Dpi --max-tokens $MaxTokens --max-calls-per-region $MaxCallsPerRegion --max-split-depth $MaxSplitDepth --device $Device.ToLowerInvariant() --port $Port
    $directExit=$LASTEXITCODE
    Stop-DirectStage
    if ($directExit -ne 0 -and $directExit -ne 2) {throw "Direct PDF OCR stopped. Keep the output to resume: $Output"}
    Write-Host ('Markdown: '+(Join-Path $Output 'document.ocr.md'))
    Write-Host ('JSON: '+(Join-Path $Output 'pages.ocr.pretty.json'))
    Write-Host ('Question content: '+(Join-Path $Output 'content.draft.pretty.json'))
    Write-Host ('Review: '+(Join-Path $Output 'review.html'))
    $directSummary=Get-Content -LiteralPath (Join-Path $Output 'summary.json') -Raw -Encoding UTF8 | ConvertFrom-Json
    $directPerformance.status=if ($directExit -eq 2) {'INCOMPLETE'} else {$directSummary.status}
    if ($directSummary.failed_regions -gt 0) {
        Write-Warning "$($directSummary.failed_regions) region(s) remain incomplete; other regions were exported. See failures.json. Run the same command to resume."
    } elseif ($directSummary.review_regions -gt 0) {
        Write-Warning "$($directSummary.review_regions) region(s) require source review; see summary.json."
    }
    if ($Open) {Invoke-Item -LiteralPath (Join-Path $Output 'review.html')}
    if ($directExit -eq 2) {exit 2}
} finally {
    try {
        if ($directStageClock -and $directStageClock.IsRunning) {Stop-DirectStage}
        $directStageName='model_stop';$directStageClock=[Diagnostics.Stopwatch]::StartNew()
        if ($directStarted) { & (Join-Path $PSScriptRoot 'local_model.ps1') -Action stop -Runtime $directRuntime -Device $Device -Port $Port }
    } finally {
        Stop-DirectStage
        if ($directLock) {$directLock.Dispose()}
        $directClock.Stop()
        $directPerformance.elapsed_seconds=[Math]::Round($directClock.Elapsed.TotalSeconds,3)
        if ($directSummary) {
            $directPerformance.processed_pages=$directSummary.processed_pages
            $directPerformance.questions=$directSummary.questions
            $directPerformance.inference_calls_this_run=$directSummary.inference_calls_this_run
            $directPerformance.cache_hits_this_run=$directSummary.cache_hits_this_run
            if ($directClock.Elapsed.TotalSeconds -gt 0) {
                $directPerformance.pages_per_minute=[Math]::Round(60*$directSummary.processed_pages/$directClock.Elapsed.TotalSeconds,3)
            }
        }
        $directPerformance.ended_at_utc=[DateTime]::UtcNow.ToString('o')
        if ($directOwnsOutput) {
            $directPerformancePath=Join-Path $Output 'pipeline-performance.json'
            $directPerformancePending=$directPerformancePath+'.'+[Guid]::NewGuid().ToString('N')+'.pending'
            $directPerformanceJson=$directPerformance | ConvertTo-Json -Depth 8
            [IO.File]::WriteAllText($directPerformancePending,$directPerformanceJson,[Text.UTF8Encoding]::new($false))
            Move-Item -LiteralPath $directPerformancePending -Destination $directPerformancePath -Force
            $directHistory=Join-Path $Output 'performance-runs'
            New-Item -ItemType Directory -Path $directHistory -Force | Out-Null
            [IO.File]::WriteAllText((Join-Path $directHistory ($directPerformance.run_id+'-pipeline.json')),$directPerformanceJson,[Text.UTF8Encoding]::new($false))
            Write-Host ('[perf] pipeline total='+$directPerformance.elapsed_seconds+'s pages/min='+$directPerformance.pages_per_minute)
            Write-Host ('[perf] details: '+$directPerformancePath)
        }
    }
}
