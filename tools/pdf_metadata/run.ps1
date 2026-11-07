param(
    [ValidateSet('native', 'ocr', 'formula', 'fallback', 'hybrid', 'enrich', 'curate', 'steps', 'pilot-trial', 'layout-refine', 'gemini-preflight', 'gemini-review', 'local-setup', 'local-start', 'local-stop', 'local-preflight', 'local-review', 'corpus-plan', 'corpus-run', 'corpus-review', 'pipeline', 'review', 'recheck', 'check', 'test')][string]$Action = 'native',
    [string]$Pdf,
    [string]$Output,
    [string]$TrialOutput,
    [string]$Runtime,
    [string]$Pages = '1',
    [string]$InputPath,
    [string]$Questions,
    [string]$Documents,
    [string]$Jobs,
    [string]$Model,
    [ValidateSet('local', 'gemini')][string]$Provider = 'local',
    [int]$Limit = 3,
    [int]$MaxCalls = 5,
    [int]$MaxTotalTokens = 100000,
    [int]$MaxOutputTokens = 8192,
    [int]$CorePages = 2,
    [int]$Overlap = 1,
    [int]$RequestInterval = 0,
    [switch]$SamplePerDocument,
    [switch]$RetryFailed,
    [switch]$Revalidate,
    [switch]$MathOnly,
    [switch]$Install,
    [switch]$InstallOcr
)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'paths.ps1')
if ($Action -like 'gemini-*') { $Provider = 'gemini' }
if ($Action -like 'local-*') { $Provider = 'local' }
$repoRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..\..')).Path
if (-not $Pdf) { $Pdf = Join-Path $repoRoot 'data\tu-luan-va-trac-nghiem-ung-dung-dao-ham-de-khao-sat-va-ve-do-thi-ham-so-toan-12-knttvcs9.pdf' }
if (-not $Output) {
    $Output = if ($Action -in @('corpus-plan', 'corpus-run', 'corpus-review', 'pipeline')) { Join-Path $PdfStorageRoot "toan12-$Provider-corpus" } else { Join-Path $PdfStorageRoot 'pdf-metadata-pilot-v1' }
}
if ($Action -in @('corpus-plan', 'pipeline') -and -not $InputPath) { $InputPath = Join-Path $repoRoot 'data\Toan12.zip' }
if ($InputPath) { $InputPath = [IO.Path]::GetFullPath($InputPath) }
if ($Limit -lt 1 -or $MaxCalls -lt 1 -or $MaxTotalTokens -lt 1000) { throw 'Use positive explicit job/call/token limits.' }
if (-not $Runtime) { $Runtime = $PdfRuntimeRoot }
$Runtime = [IO.Path]::GetFullPath($Runtime)
$env:PDFMETA_RUNTIME_ROOT = $Runtime
$Pdf = [IO.Path]::GetFullPath($Pdf)
$Output = [IO.Path]::GetFullPath($Output)
foreach ($folder in @($Runtime, (Join-Path $Runtime 'temp'), (Join-Path $Runtime 'pip-cache'))) {
    New-Item -ItemType Directory -Force -Path $folder | Out-Null
}
$env:TEMP = Join-Path $Runtime 'temp'
$env:TMP = $env:TEMP
$env:PIP_CACHE_DIR = Join-Path $Runtime 'pip-cache'
$pythonPath = Join-Path $Runtime '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) {
    if (-not $Install -and -not $InstallOcr) { throw 'Environment missing. Run with -Install first.' }
    & py -3.13 -m venv (Join-Path $Runtime '.venv')
    if ($LASTEXITCODE) { throw 'Could not create the isolated environment.' }
}
if ($Install -or $InstallOcr) {
    $requirements = if ($InstallOcr) { 'requirements-paddle.txt' } else { 'requirements-native.txt' }
    & $pythonPath -m pip install -r (Join-Path $PSScriptRoot $requirements)
    if ($LASTEXITCODE) { throw 'Dependency installation failed.' }
}
Push-Location -LiteralPath $PSScriptRoot
try {
    $geminiArgs = @('--limit', $Limit, '--max-calls', $MaxCalls, '--max-total-tokens', $MaxTotalTokens, '--provider', $Provider)
    if ($Model) { $geminiArgs += @('--model', $Model) }
    if ($RetryFailed) { $geminiArgs += '--retry-failed' }
    $corpusArgs = $geminiArgs.Clone()
    if ($Documents) { $corpusArgs += @('--documents', $Documents) }
    if ($Jobs) { $corpusArgs += @('--jobs', $Jobs) }
    if ($Revalidate) { $corpusArgs += '--revalidate' }
    $corpusArgs += @('--max-output-tokens', $MaxOutputTokens, '--request-interval', $RequestInterval)
    $geminiArgs += @('--max-output-tokens', $MaxOutputTokens)
    if ($SamplePerDocument) { $corpusArgs += '--sample-per-document' }
    switch ($Action) {
        'native' { & $pythonPath -m pdfmeta --pdf $Pdf --output $Output --runtime $Runtime }
        'ocr' { & $pythonPath -u -m pdfmeta.paddle_probe --pilot $Output --runtime $Runtime --pages $Pages }
        'formula' { & $pythonPath -u -m pdfmeta.formula_probe --pilot $Output --runtime $Runtime }
        'fallback' { & $pythonPath -u -m pdfmeta.formula_fallback --pilot $Output --runtime $Runtime }
        'hybrid' { & $pythonPath -u -m pdfmeta.fast_hybrid --pilot $Output --runtime $Runtime --pages $Pages }
        'enrich' { & $pythonPath -m pdfmeta.enrich --pilot $Output }
        'curate' { & $pythonPath -m pdfmeta.curate --pilot $Output }
        'steps' { & $pythonPath -m pdfmeta.step_segmentation --pilot $Output }
        'pilot-trial' {
            if (-not $TrialOutput) { $TrialOutput = Join-Path $Output 'metadata-trial-v1' }
            $TrialOutput = [IO.Path]::GetFullPath($TrialOutput)
            $trialArgs = @('--pilot', $Output, '--pdf', $Pdf, '--output', $TrialOutput, '--limit', $Limit)
            if ($Questions) { $trialArgs += @('--questions', $Questions) }
            # Short metadata contract; cap the general wrapper's 8192-token default.
            $trialArgs += @('--max-output-tokens', [Math]::Min($MaxOutputTokens, 768))
            if ($MathOnly) { $trialArgs += '--math-only' }
            & $pythonPath -u -m pdfmeta.pilot_trial @trialArgs
        }
        'layout-refine' {
            if (-not $Questions) { throw 'Select table questions explicitly with -Questions.' }
            if (-not $TrialOutput) { $TrialOutput = Join-Path $Output 'layout-trial-v1' }
            $TrialOutput = [IO.Path]::GetFullPath($TrialOutput)
            & $pythonPath -B -u -m pdfmeta.layout_refinement --pilot $Output --pdf $Pdf --output $TrialOutput --runtime $Runtime --questions $Questions --limit $Limit
        }
        'gemini-preflight' { & $pythonPath -m pdfmeta.gemini_review --pilot $Output --preflight @geminiArgs }
        'gemini-review' {
            if ($Questions) { $geminiArgs += @('--questions', $Questions) }
            & $pythonPath -u -m pdfmeta.gemini_review --pilot $Output @geminiArgs
        }
        'local-setup' { & $pythonPath -u -m pdfmeta.local_setup --runtime $Runtime }
        'local-start' { & (Join-Path $PSScriptRoot 'local_model.ps1') -Action start -Runtime $Runtime }
        'local-stop' { & (Join-Path $PSScriptRoot 'local_model.ps1') -Action stop -Runtime $Runtime }
        'local-preflight' { & $pythonPath -m pdfmeta.gemini_review --pilot $Output --preflight @geminiArgs }
        'local-review' {
            if ($Questions) { $geminiArgs += @('--questions', $Questions) }
            & $pythonPath -u -m pdfmeta.gemini_review --pilot $Output @geminiArgs
        }
        'corpus-plan' { & $pythonPath -u -m pdfmeta.corpus plan --input $InputPath --output $Output --core-pages $CorePages --overlap $Overlap }
        'corpus-run' { & $pythonPath -u -m pdfmeta.corpus run --output $Output @corpusArgs }
        'corpus-review' { & $pythonPath -u -m pdfmeta.artifact_server --root $Output }
        'pipeline' {
            & $pythonPath -u -m pdfmeta.corpus plan --input $InputPath --output $Output --core-pages $CorePages --overlap $Overlap
            if ($LASTEXITCODE) { throw 'Corpus planning failed; no inference was started.' }
            & $pythonPath -u -m pdfmeta.corpus run --output $Output @corpusArgs
        }
        'review' { & $pythonPath -u -m pdfmeta.review_server --pilot $Output }
        'recheck' { & $pythonPath -m pdfmeta.recheck_quality --pilot $Output }
        'check' { & $pythonPath -m pdfmeta.check_fixture --pilot $Output --fixture 'fixtures/pilot-kntt-v1.json' }
        'test' { & $pythonPath -m pytest tests -q --basetemp (Join-Path $Runtime 'pytest-temp') }
    }
    if ($LASTEXITCODE) { throw "Pipeline action $Action failed with exit code $LASTEXITCODE" }
} finally { Pop-Location }
