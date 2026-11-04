param(
    [Parameter(Mandatory=$true)][string]$Metadata,
    [Parameter(Mandatory=$true)][string]$Plan,
    [Parameter(Mandatory=$true)][string]$Output,
    [string]$Storage,
    [string]$Runtime,
    [ValidateRange(4,100000)][int]$Count=100,
    [ValidateSet(1,2)][int]$Workers=2,
    [ValidateSet('v1','v2')][string]$Version='v1',
    [string[]]$ExcludeSelection=@(),
    [string]$Selection,
    [switch]$All,
    [ValidateSet('local','cold')][string]$CacheMode='local',
    [ValidateRange(1,100)][int]$ChunkSize=10,
    [ValidateRange(1,64)][int]$MaxPageCache=8,
    [ValidateRange(1,86400)][int]$ChunkTimeout=1800,
    [ValidateRange(1,604800)][int]$RunTimeout=14400,
    [ValidateRange(0,1048576)][int]$MemoryLimitMB=8192,
    [ValidateRange(0,100000)][int]$StopAfterChunks=0,
    [switch]$PlanOnly,
    [switch]$SkipQwen,
    [switch]$Open
)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'paths.ps1')
$taskRepo=(Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..\..')).Path
if (-not $Storage) { $Storage=$PdfStorageRoot }
$Storage=[IO.Path]::GetFullPath($Storage)
if (-not $Runtime) { $Runtime=Join-Path $Storage 'pdf-pipeline-runtime' }
$taskRuntime=[IO.Path]::GetFullPath($Runtime)
$taskPython=Join-Path $taskRuntime '.venv\Scripts\python.exe'
$taskKatex=Join-Path $taskRepo 'frontend\node_modules\katex\dist'
$taskOutput=[IO.Path]::GetFullPath($Output)
foreach ($taskPath in @($Metadata,$Plan,$taskPython,(Join-Path $taskKatex 'katex.js'))) {
    if (-not (Test-Path -LiteralPath $taskPath -PathType Leaf)) { throw "Required local file missing: $taskPath" }
}
$env:PYTHONPATH=$PSScriptRoot
$env:PYTHONUTF8='1'
$env:PYTHONIOENCODING='utf-8'
$env:PYTHONDONTWRITEBYTECODE='1'
if ($Version -eq 'v2') {
    if ($All -and $Selection) { throw 'Choose All or an explicit Selection, not both.' }
    if ($All) {
        New-Item -ItemType Directory -Force -Path $taskOutput | Out-Null
        $Selection=Join-Path $taskOutput 'selection.all.json'
        $taskSelectArgs=@('-B','-m','pdfmeta.paired.selection_cli','--input',$Metadata,'--output',$Selection)
        foreach ($taskExcluded in $ExcludeSelection) { $taskSelectArgs+=@('--exclude-selection',$taskExcluded) }
        & $taskPython @taskSelectArgs
        if ($LASTEXITCODE) { throw 'Could not freeze the full corpus selection.' }
    }
    $taskArgs=@('-B','-u','-m','pdfmeta.paired.transcription_v2.batch',
        '--input',$Metadata,'--plan',$Plan,'--output',$taskOutput,'--runtime',$taskRuntime,
        '--katex',$taskKatex,'--count',$Count,'--workers',$Workers,'--cache-mode',$CacheMode,
        '--chunk-size',$ChunkSize,'--max-page-cache',$MaxPageCache,'--chunk-timeout',$ChunkTimeout,
        '--run-timeout',$RunTimeout,'--memory-limit-mb',$MemoryLimitMB,'--stop-after-chunks',$StopAfterChunks)
    foreach ($taskExcluded in $ExcludeSelection) { $taskArgs+=@('--exclude-selection',$taskExcluded) }
    if ($Selection) { $taskArgs+=@('--selection',$Selection) }
    if ($PlanOnly) { $taskArgs+='--plan-only' }
    & $taskPython @taskArgs
    $taskV2Exit=$LASTEXITCODE
    if ($taskV2Exit -ne 0) {
        if ($taskV2Exit -eq 3) { Write-Host 'Paused at a chunk boundary. Run the same command without StopAfterChunks to resume.' }
        else { Write-Warning 'V2 is incomplete. Check batch-state.json, runtime.json and chunks/*/*/worker.log.' }
        exit $taskV2Exit
    }
    if ($PlanOnly) { return }
    if (-not $SkipQwen) {
        $taskVisionState=Join-Path $taskOutput 'qwen-runtime'
        try {
            & (Join-Path $PSScriptRoot 'transcription_vision_runtime.ps1') -Action start -Runtime $taskRuntime -State $taskVisionState
            $taskVisionReady=$false
            for ($taskHealthAttempt=0;$taskHealthAttempt -lt 60;$taskHealthAttempt++) {
                try {
                    $taskVisionHealth=Invoke-RestMethod -Uri 'http://127.0.0.1:8792/health' -TimeoutSec 2
                    if ($taskVisionHealth.status -eq 'ok') { $taskVisionReady=$true;break }
                } catch { }
                Start-Sleep -Seconds 1
            }
            if (-not $taskVisionReady) { throw 'Vision server did not become ready within the startup budget.' }
            & $taskPython -B -u -m pdfmeta.paired.transcription_v2.vision --output $taskOutput --runtime $taskVisionState
            if ($LASTEXITCODE) { throw 'V2 image diagnostic failed. OCR checkpoints remain available.' }
        } finally {
            & (Join-Path $PSScriptRoot 'transcription_vision_runtime.ps1') -Action stop -Runtime $taskRuntime -State $taskVisionState
        }
    }
    Write-Output "V2 draft: $(Join-Path $taskOutput 'content.draft.pretty.json')"
    Write-Output "Benchmark: $(Join-Path $taskOutput 'benchmark.json')"
    if ($Open) {
        $taskJobs=Join-Path $Storage 'pdf-jobs'
        if ($taskOutput.StartsWith($taskJobs.TrimEnd('\')+'\',[StringComparison]::OrdinalIgnoreCase)) {
            $taskBase=(& $taskPython -B -m pdfmeta.progress ensure --root $taskJobs --runtime $taskRuntime --port 8789 | Select-Object -Last 1).Trim()
            $taskRelative=$taskOutput.Substring($taskJobs.TrimEnd('\').Length+1).Replace('\','/')
            Start-Process -FilePath ($taskBase.TrimEnd('/')+'/artifacts/'+$taskRelative+'/review.html')
        }
    }
    return
}
if ($All -or $ExcludeSelection.Count -or $Selection -or $CacheMode -ne 'local' -or $StopAfterChunks -or $PlanOnly) {
    throw 'Selection, cold-cache and chunk controls require -Version v2.'
}
& $taskPython -B -u -m pdfmeta.paired.transcript_batch --input $Metadata --plan $Plan --output $taskOutput --runtime $taskRuntime --katex $taskKatex --count $Count --workers $Workers
$taskBatchExit=$LASTEXITCODE
& $taskPython -B -m pdfmeta.paired.transcript_rescue --input $Metadata --plan $Plan --output $taskOutput
if ($LASTEXITCODE) { throw 'Could not retain failed questions as source-image-only records.' }
if (-not $SkipQwen) {
    & (Join-Path $PSScriptRoot 'local_model.ps1') -Action start -Runtime $taskRuntime
    for ($taskAttempt=0;$taskAttempt -lt 30;$taskAttempt++) {
        try {
            $taskHealth=Invoke-RestMethod -Uri 'http://127.0.0.1:8790/health' -TimeoutSec 2
            if ($taskHealth.status -eq 'ok') { break }
        } catch { }
        Start-Sleep -Seconds 1
    }
    & $taskPython -B -u -m pdfmeta.paired.transcript_triage --output $taskOutput --runtime $taskRuntime --limit 40 --retry-failed
    if ($LASTEXITCODE) { Write-Warning 'Qwen triage stopped; source-backed drafts and checkpoints remain available.' }
}
& $taskPython -B -m pdfmeta.paired.transcript_audit --output $taskOutput
if ($LASTEXITCODE) { throw 'Draft quality audit failed; check its log before using the output.' }
if ($Open) {
        $taskJobs=Join-Path $Storage 'pdf-jobs'
    if ($taskOutput.StartsWith($taskJobs.TrimEnd('\')+'\',[StringComparison]::OrdinalIgnoreCase)) {
        $taskBase=(& $taskPython -B -m pdfmeta.progress ensure --root $taskJobs --runtime $taskRuntime --port 8789 | Select-Object -Last 1).Trim()
        if ($LASTEXITCODE) { throw 'Could not start the local artifact viewer.' }
        $taskRelative=$taskOutput.Substring($taskJobs.TrimEnd('\').Length+1).Replace('\','/')
        $taskEncoded=($taskRelative.Split('/') | ForEach-Object { [Uri]::EscapeDataString($_) }) -join '/'
        Start-Process -FilePath ($taskBase.TrimEnd('/')+'/artifacts/'+$taskEncoded+'/review.html')
    } else {
        Write-Warning 'Use an Output folder under .tmp\pdf-jobs\<job> to open it in the local dashboard.'
    }
}
if ($taskBatchExit) { Write-Warning 'Some questions could not be transcribed. Their source-image-only records are retained and explicitly flagged.' }
Write-Output "Draft JSONL: $(Join-Path $taskOutput 'metadata.transcribed.draft.jsonl')"
Write-Output "Quality report: $(Join-Path $taskOutput 'quality-summary.json')"
