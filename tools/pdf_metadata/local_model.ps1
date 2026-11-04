param(
    [ValidateSet('start', 'stop', 'status')][string]$Action = 'status',
    [string]$Runtime,
    [int]$Port = 8790
)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'paths.ps1')
$localRepoRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..\..')).Path
if (-not $Runtime) { $Runtime = $PdfRuntimeRoot }
$Runtime = [IO.Path]::GetFullPath($Runtime)
$localManifestPath = Join-Path $Runtime 'local-qwen-runtime.json'
if (-not (Test-Path -LiteralPath $localManifestPath)) { throw 'Run run.ps1 -Action local-setup first.' }
$localManifest = Get-Content -LiteralPath $localManifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
$localPidPath = Join-Path $Runtime 'local-qwen-server.pid'
$localServerProcess = $null
if (Test-Path -LiteralPath $localPidPath) {
    $localRecordedPid = [int](Get-Content -LiteralPath $localPidPath -Raw)
    $localCandidate = Get-CimInstance Win32_Process -Filter "ProcessId=$localRecordedPid" -ErrorAction SilentlyContinue
    if ($localCandidate -and $localCandidate.ExecutablePath -eq $localManifest.server_path -and $localCandidate.CommandLine -like '*qwen3-vl-2b-instruct*') {
        $localServerProcess = $localCandidate
    }
}
if ($Action -eq 'stop') {
    if ($localServerProcess) { Stop-Process -Id $localServerProcess.ProcessId; Write-Output "Stopped local Qwen server PID $($localServerProcess.ProcessId)" }
    else { Write-Output 'No matching local Qwen server is running.' }
    exit 0
}
if ($Action -eq 'start' -and -not $localServerProcess) {
    if (Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue) { throw "Port $Port is already occupied; the existing process was preserved." }
    foreach ($localCheck in @(@($localManifest.server_path, $localManifest.server_sha256), @($localManifest.model_path, $localManifest.model_sha256), @($localManifest.projector_path, $localManifest.projector_sha256))) {
        $localResolvedPath = [IO.Path]::GetFullPath($localCheck[0])
        if (-not $localResolvedPath.StartsWith($Runtime.TrimEnd('\') + '\', [StringComparison]::OrdinalIgnoreCase)) { throw 'Model runtime path lies outside the configured directory.' }
        if ((Get-FileHash -LiteralPath $localResolvedPath -Algorithm SHA256).Hash.ToLowerInvariant() -ne $localCheck[1]) { throw 'Local runtime checksum mismatch.' }
    }
    $localKeyPath = Join-Path $Runtime 'local-qwen-server.key'
    if (-not (Test-Path -LiteralPath $localKeyPath)) {
        $localKeyBytes = New-Object byte[] 32
        $localKeyRng = [Security.Cryptography.RandomNumberGenerator]::Create()
        try { $localKeyRng.GetBytes($localKeyBytes) } finally { $localKeyRng.Dispose() }
        [IO.File]::WriteAllText($localKeyPath, [Convert]::ToBase64String($localKeyBytes))
    }
    $localArguments = @('-m', ('"' + $localManifest.model_path + '"'), '--mmproj', ('"' + $localManifest.projector_path + '"'),
        '--host', '127.0.0.1', '--port', $Port, '--alias', $localManifest.served_model,
        '--ctx-size', $localManifest.context_size, '--parallel', '1', '--threads', $localManifest.threads,
        '--threads-batch', $localManifest.threads, '--n-gpu-layers', '0', '--no-mmproj-offload',
        '--batch-size', '128', '--ubatch-size', '64', '--no-warmup', '--image-min-tokens', '1024', '--image-max-tokens', '1024',
        '--api-key-file', ('"' + $localKeyPath + '"'), '--cors-origins', "http://127.0.0.1:$Port")
    $localStarted = Start-Process -FilePath $localManifest.server_path -ArgumentList $localArguments -WindowStyle Hidden -PassThru -WorkingDirectory $Runtime -RedirectStandardOutput (Join-Path $Runtime 'local-qwen-server.out.log') -RedirectStandardError (Join-Path $Runtime 'local-qwen-server.err.log')
    $localStarted.PriorityClass = 'BelowNormal'
    Set-Content -LiteralPath $localPidPath -Value $localStarted.Id
    Write-Output "Started local Qwen PID $($localStarted.Id), CPU threads=$($localManifest.threads), loopback port=$Port"
} elseif ($localServerProcess) { Write-Output "Local Qwen PID $($localServerProcess.ProcessId)" }
try {
    $localHealth = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/health" -TimeoutSec 3
    Write-Output "Health: $($localHealth.status)"
} catch { Write-Output 'Health is not ready yet; inspect local-qwen-server.err.log while the model loads.' }
