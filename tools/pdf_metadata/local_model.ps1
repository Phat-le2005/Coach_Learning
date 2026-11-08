param(
    [ValidateSet('start', 'stop', 'status')][string]$Action = 'status',
    [string]$Runtime,
    [ValidateRange(1,65535)][int]$Port = 8790,
    [ValidateSet('CPU','GPU')][string]$Device = 'CPU'
)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'paths.ps1')
$localRepoRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..\..')).Path
if (-not $Runtime) { $Runtime = $PdfRuntimeRoot }
$Runtime = [IO.Path]::GetFullPath($Runtime)
$localManifestName = if ($Device -eq 'GPU') {'local-qwen-runtime.gpu.json'} else {'local-qwen-runtime.json'}
$localManifestPath = Join-Path $Runtime $localManifestName
if (-not (Test-Path -LiteralPath $localManifestPath)) { throw 'Run run.ps1 -Action local-setup first.' }
$localManifest = Get-Content -LiteralPath $localManifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
$localStem = if ($Port -eq 8790) {'local-qwen-server'} else {"local-qwen-server-$Port"}
$localPidPath = Join-Path $Runtime ($localStem+'.pid')
$localStatePath = Join-Path $Runtime ($localStem+'.state.json')
$localSignature = (Get-FileHash -LiteralPath $localManifestPath -Algorithm SHA256).Hash
$localLayers = if ($Device -eq 'GPU') {[int]$localManifest.gpu_layers} else {0}
if ($Device -eq 'GPU' -and ($localLayers -le 0 -or $localManifest.backend -ne 'cuda')) {throw 'GPU profile requires CUDA offload.'}
$localServerProcess = $null
$localStarted = $null
if (Test-Path -LiteralPath $localPidPath) {
    $localRecordedPid = [int](Get-Content -LiteralPath $localPidPath -Raw)
    $localCandidate = Get-CimInstance Win32_Process -Filter "ProcessId=$localRecordedPid" -ErrorAction SilentlyContinue
    if ($localCandidate -and $localCandidate.ExecutablePath -eq $localManifest.server_path -and $localCandidate.CommandLine -like ('*'+$localManifest.served_model+'*') -and $localCandidate.CommandLine -match ("--port\s+$Port(?:\s|$)")) {
        $localServerProcess = $localCandidate
    }
}
# A web worker may not be allowed to read an elevated server's executable or
# command line through CIM. Reuse only our recorded listener and matching profile,
# after the server accepts the runtime's private API key and serves its model.
# This attachment never authorizes stopping a process we could not inspect.
if (-not $localServerProcess -and $Action -ne 'stop' -and
    (Test-Path -LiteralPath $localPidPath) -and (Test-Path -LiteralPath $localStatePath)) {
    $localAttachmentState = Get-Content -LiteralPath $localStatePath -Raw -Encoding UTF8 | ConvertFrom-Json
    $localAttachmentKeyPath = Join-Path $Runtime 'local-qwen-server.key'
    $localRecordedListener = @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
        Where-Object { $_.OwningProcess -eq $localRecordedPid })
    if ($localRecordedListener.Count -gt 0 -and
        $localAttachmentState.process_id -eq $localRecordedPid -and
        $localAttachmentState.port -eq $Port -and
        $localAttachmentState.device -eq $Device -and
        $localAttachmentState.signature -eq $localSignature -and
        (Test-Path -LiteralPath $localAttachmentKeyPath)) {
        try {
            $localAttachmentHeaders = @{Authorization = 'Bearer ' + [IO.File]::ReadAllText($localAttachmentKeyPath).Trim()}
            $localAttachedModels = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/v1/models" -Headers $localAttachmentHeaders -TimeoutSec 5
            if (@($localAttachedModels.data | Where-Object { $_.id -eq $localManifest.served_model }).Count -gt 0) {
                $localServerProcess = [PSCustomObject]@{ProcessId = $localRecordedPid}
                Write-Host 'Reused authenticated local Qwen server using its recorded runtime profile.'
            }
        } catch {
            # A healthy but unrelated listener must never be adopted.
        } finally {
            $localAttachmentHeaders = $null
        }
    }
}
if ($localServerProcess -and $Action -eq 'start') {
    if (Test-Path -LiteralPath $localStatePath) {
        $localState=Get-Content -LiteralPath $localStatePath -Raw -Encoding UTF8 | ConvertFrom-Json
        if ($localState.process_id -ne $localServerProcess.ProcessId -or $localState.device -ne $Device -or $localState.signature -ne $localSignature) {
            throw 'Running Qwen configuration differs. Stop the current OCR/server before switching device or settings.'
        }
    } elseif ($Device -ne 'CPU' -or $localServerProcess.CommandLine -notmatch '--n-gpu-layers\s+0(?:\s|$)' -or $localServerProcess.CommandLine -notmatch '--no-mmproj-offload' -or $localServerProcess.CommandLine -notmatch ("--ctx-size\s+$($localManifest.context_size)(?:\s|$)") -or $localServerProcess.CommandLine -notmatch ("--threads\s+$($localManifest.threads)(?:\s|$)")) {
        throw 'Existing server configuration is not verified; stop it before starting this OCR job.'
    }
}
if ($Action -eq 'stop') {
    if ($localServerProcess) { Stop-Process -Id $localServerProcess.ProcessId; Write-Output "Stopped local Qwen server PID $($localServerProcess.ProcessId)" }
    else { Write-Output 'No matching local Qwen server is running.' }
    exit 0
}
if ($Action -eq 'start' -and -not $localServerProcess) {
    if (Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue) { throw "Port $Port is already occupied; the existing process was preserved." }
    $localChecks=@(@($localManifest.server_path, $localManifest.server_sha256), @($localManifest.model_path, $localManifest.model_sha256), @($localManifest.projector_path, $localManifest.projector_sha256))
    if ($Device -eq 'GPU') { foreach ($localBackendFile in $localManifest.backend_files) {$localChecks += ,@($localBackendFile.path,$localBackendFile.sha256)} }
    foreach ($localCheck in $localChecks) {
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
        '--threads-batch', $localManifest.threads, '--n-gpu-layers', $localLayers,
        '--batch-size', '128', '--ubatch-size', '64', '--no-warmup', '--image-min-tokens', '1024', '--image-max-tokens', '1024',
        '--api-key-file', ('"' + $localKeyPath + '"'), '--cors-origins', "http://127.0.0.1:$Port")
    if ($Device -eq 'CPU' -or -not $localManifest.mmproj_offload) {$localArguments += '--no-mmproj-offload'}
    # Keep the tested context/batch/weights; don't let automatic fitting change them.
    if ($Device -eq 'GPU') {$localArguments += @('--fit','off')}
    $localStarted = Start-Process -FilePath $localManifest.server_path -ArgumentList $localArguments -WindowStyle Hidden -PassThru -WorkingDirectory $Runtime -RedirectStandardOutput (Join-Path $Runtime ($localStem+'.out.log')) -RedirectStandardError (Join-Path $Runtime ($localStem+'.err.log'))
    $localStarted.PriorityClass = 'BelowNormal'
    Set-Content -LiteralPath $localPidPath -Value $localStarted.Id
    @{process_id=$localStarted.Id;device=$Device;signature=$localSignature;port=$Port} | ConvertTo-Json | Set-Content -LiteralPath $localStatePath -Encoding UTF8
    Write-Host "Started local Qwen PID $($localStarted.Id), device=$Device, CPU threads=$($localManifest.threads), GPU layers=$localLayers, loopback port=$Port"
} elseif ($localServerProcess) { Write-Host "Local Qwen PID $($localServerProcess.ProcessId), device=$Device" }
try {
    $localHealth = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/health" -TimeoutSec 3
    Write-Host "Health: $($localHealth.status)"
} catch { Write-Host "Health is not ready yet; inspect $localStem.err.log while the model loads." }
if ($Action -eq 'start') {
    [PSCustomObject]@{StartedByCaller=($null -ne $localStarted);ProcessId=if ($localStarted) {$localStarted.Id} elseif ($localServerProcess) {$localServerProcess.ProcessId};Device=$Device;Port=$Port}
}
