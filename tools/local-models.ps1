param(
    [Parameter(Mandatory=$true)][ValidateSet('layout','htr','unimumer')][string]$Component,
    [ValidateSet('setup','start','health','stop')][string]$Action = 'health',
    [string]$Python = 'python',
    [ValidateSet('cpu','cuda','both')][string]$Runtime = 'cpu'
)
$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$lab = Join-Path $PSScriptRoot 'ocr-v2-lab'
function Invoke-Checked([string]$Exe, [string[]]$Arguments) {
    & $Exe @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Command failed: $Exe (exit $LASTEXITCODE)" }
}
if ($Component -eq 'layout') {
    if ($Action -eq 'setup') { & (Join-Path $lab 'setup.ps1') -Python $Python; exit }
    $venvPython = Join-Path $repoRoot '.tmp/tri-ocr-v2-runtime/venv/Scripts/python.exe'
    $keyFile = Join-Path $repoRoot '.tmp/tri-ocr-v2-runtime/service-token.txt'
    if (!(Test-Path -LiteralPath $venvPython)) { throw 'Run layout setup first.' }
    if ($Action -eq 'stop') { throw 'The foreground layout service stops with Ctrl+C in its terminal.' }
    if (!(Test-Path -LiteralPath $keyFile)) {
        $keyBytes = New-Object byte[] 48
        $rng = [Security.Cryptography.RandomNumberGenerator]::Create()
        try { $rng.GetBytes($keyBytes) } finally { $rng.Dispose() }
        [IO.File]::WriteAllText($keyFile, [Convert]::ToBase64String($keyBytes))
    }
    $env:OCR_V2_SIDECAR_TOKEN = [IO.File]::ReadAllText($keyFile).Trim()
    if ($Action -eq 'health') {
        Invoke-RestMethod 'http://127.0.0.1:8031/health' -Headers @{Authorization="Bearer $env:OCR_V2_SIDECAR_TOKEN"}
    } else { Invoke-Checked $venvPython @((Join-Path $lab 'service.py'),'--port','8031') }
    exit
}
$folder = if ($Component -eq 'htr') { '.tmp/tri-vietnamese-htr' } else { '.tmp/tri-unimumer-lab' }
$venvPython = Join-Path $repoRoot "$folder/venv/Scripts/python.exe"
if ($Action -eq 'setup') {
    if (!(Test-Path -LiteralPath $venvPython)) {
        Invoke-Checked $Python @('-c','import sys; assert sys.version_info[:2] == (3,12), "Use Python 3.12 for the pinned inference environments"')
        Invoke-Checked $Python @('-m','venv',(Join-Path $repoRoot "$folder/venv"))
    }
    $requirements = if ($Component -eq 'htr') { 'htr-requirements.txt' } else { 'unimumer-requirements.txt' }
    Invoke-Checked $venvPython @('-m','pip','install','-r',(Join-Path $lab $requirements))
    if ($Component -eq 'htr') {
        Invoke-Checked $venvPython @('-m','pip','install','vietocr==0.3.13','--no-deps')
        Invoke-Checked $venvPython @((Join-Path $lab 'htr_setup.py'))
    } else { Invoke-Checked $venvPython @((Join-Path $lab 'unimumer_setup.py'),'--runtime',$Runtime) }
    exit
}
if (!(Test-Path -LiteralPath $venvPython)) { throw "Run $Component setup first." }
if ($Component -eq 'htr') { Invoke-Checked $venvPython @((Join-Path $lab 'htr_local.py'),$Action) }
elseif ($Action -eq 'start') {
    $profile = if ($Runtime -eq 'cpu') { 'cpu' } else { 'hybrid' }
    Invoke-Checked $venvPython @((Join-Path $lab 'unimumer.py'),'start','--profile',$profile)
} else { Invoke-Checked $venvPython @((Join-Path $lab 'unimumer.py'),$Action) }
