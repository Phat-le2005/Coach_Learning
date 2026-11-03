param(
    [Parameter(Mandatory=$true)][string]$Metadata,
    [Parameter(Mandatory=$true)][string]$Plan,
    [Parameter(Mandatory=$true)][string]$Output,
    [ValidateRange(4,1000)][int]$Count=100,
    [ValidateSet(1,2)][int]$Workers=2,
    [switch]$SkipQwen,
    [switch]$Open
)
$ErrorActionPreference='Stop'
$taskRepo=(Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..\..')).Path
$taskRuntime=Join-Path $taskRepo '.tmp\pdf-pipeline-runtime'
$taskPython=Join-Path $taskRuntime '.venv\Scripts\python.exe'
$taskKatex=Join-Path $taskRepo 'frontend\node_modules\katex\dist'
if ($taskRuntime -notmatch '^[Ee]:\\') { throw 'Keep runtime, caches and outputs on E.' }
$taskOutput=[IO.Path]::GetFullPath($Output)
if ($taskOutput -notmatch '^[Ee]:\\') { throw 'Keep transcription output on E.' }
foreach ($taskPath in @($Metadata,$Plan,$taskPython,(Join-Path $taskKatex 'katex.js'))) {
    if (-not (Test-Path -LiteralPath $taskPath -PathType Leaf)) { throw "Required local file missing: $taskPath" }
}
$env:PYTHONPATH=$PSScriptRoot
$env:PYTHONUTF8='1'
$env:PYTHONIOENCODING='utf-8'
$env:PYTHONDONTWRITEBYTECODE='1'
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
    $taskJobs=Join-Path $taskRepo '.tmp\pdf-jobs'
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
