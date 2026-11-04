param(
    [ValidateSet('start','stop','status')][string]$Action = 'status',
    [Parameter(Mandatory=$true)][string]$Runtime,
    [Parameter(Mandatory=$true)][string]$State,
    [int]$Port = 8792
)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'paths.ps1')
$Runtime = [IO.Path]::GetFullPath($Runtime)
$State = [IO.Path]::GetFullPath($State)
$visionSource = Get-Content -LiteralPath (Join-Path $Runtime 'local-qwen-runtime.json') -Raw -Encoding UTF8 | ConvertFrom-Json
New-Item -ItemType Directory -Force -Path $State | Out-Null
$visionPidPath = Join-Path $State 'server.pid'
$visionKey = Join-Path $State 'local-qwen-server.key'
$visionProcess = $null
if (Test-Path -LiteralPath $visionPidPath) {
    $visionCandidate = Get-CimInstance Win32_Process -Filter "ProcessId=$([int](Get-Content -LiteralPath $visionPidPath -Raw))" -ErrorAction SilentlyContinue
    if ($visionCandidate -and $visionCandidate.ExecutablePath -eq $visionSource.server_path -and $visionCandidate.CommandLine.Contains($visionSource.model_path) -and $visionCandidate.CommandLine.Contains($visionKey)) { $visionProcess = $visionCandidate }
}
if ($Action -eq 'stop') {
    if ($visionProcess) { Stop-Process -Id $visionProcess.ProcessId; Write-Output "Stopped owned vision server PID $($visionProcess.ProcessId)" }
    else { Write-Output 'No matching vision server.' }
    exit 0
}
if ($Action -eq 'start' -and -not $visionProcess) {
    if (Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue) { throw 'Vision port occupied; existing process preserved.' }
    foreach ($visionCheck in @(@($visionSource.server_path,$visionSource.server_sha256),@($visionSource.model_path,$visionSource.model_sha256),@($visionSource.projector_path,$visionSource.projector_sha256))) {
        $visionResolved = [IO.Path]::GetFullPath($visionCheck[0])
        if (-not $visionResolved.StartsWith($Runtime.TrimEnd('\')+'\',[StringComparison]::OrdinalIgnoreCase)) { throw 'Weight or executable lies outside runtime.' }
        if ((Get-FileHash -LiteralPath $visionResolved -Algorithm SHA256).Hash.ToLowerInvariant() -ne $visionCheck[1]) { throw 'Runtime checksum mismatch.' }
    }
    $visionManifest = $visionSource | Select-Object *
    $visionManifest.threads = 6
    $visionManifest.context_size = 8192
    $visionManifest | Add-Member -NotePropertyName image_min_tokens -NotePropertyValue 64 -Force
    $visionManifest | Add-Member -NotePropertyName image_max_tokens -NotePropertyValue 768 -Force
    [IO.File]::WriteAllText((Join-Path $State 'local-qwen-runtime.json'),($visionManifest | ConvertTo-Json -Depth 10),(New-Object Text.UTF8Encoding($false)))
    if (-not (Test-Path -LiteralPath $visionKey)) {
        $visionBytes = New-Object byte[] 32
        $visionRng = [Security.Cryptography.RandomNumberGenerator]::Create()
        try { $visionRng.GetBytes($visionBytes) } finally { $visionRng.Dispose() }
        [IO.File]::WriteAllText($visionKey,[Convert]::ToBase64String($visionBytes))
    }
    $visionArgs = @('-m',('"'+$visionSource.model_path+'"'),'--mmproj',('"'+$visionSource.projector_path+'"'),
        '--host','127.0.0.1','--port',$Port,'--alias',$visionSource.served_model,
        '--ctx-size','8192','--parallel','1','--threads','6','--threads-batch','6',
        '--n-gpu-layers','0','--no-mmproj-offload','--batch-size','128','--ubatch-size','64','--no-warmup',
        '--image-min-tokens','64','--image-max-tokens','768','--api-key-file',('"'+$visionKey+'"'))
    $visionStarted = Start-Process -FilePath $visionSource.server_path -ArgumentList $visionArgs -WindowStyle Hidden -PassThru -WorkingDirectory $State -RedirectStandardOutput (Join-Path $State 'server.out.log') -RedirectStandardError (Join-Path $State 'server.err.log')
    $visionStarted.PriorityClass = 'BelowNormal'
    Set-Content -LiteralPath $visionPidPath -Value $visionStarted.Id
    Write-Output "Started vision server PID $($visionStarted.Id), loopback=$Port, CPU threads=6"
}
try { $visionHealth = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/health" -TimeoutSec 2; Write-Output "Health: $($visionHealth.status)" }
catch { Write-Output 'Model is loading or stopped.' }
