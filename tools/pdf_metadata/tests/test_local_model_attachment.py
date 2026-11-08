"""The web worker can reuse its model even when CIM cannot inspect its process."""
import hashlib
import json
import os
from pathlib import Path
import subprocess

import pytest


pytestmark = pytest.mark.skipif(os.name != "nt", reason="Windows PowerShell runtime")
SCRIPT = Path(__file__).resolve().parents[1] / "local_model.ps1"


@pytest.mark.parametrize("mismatch", [None, "signature", "listener", "model", "key", "state_pid", "port", "device"])
def test_authenticated_attachment_requires_runtime_profile_listener_and_key(tmp_path, mismatch):
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    manifest = dict(server_path=str(runtime / "llama-server.exe"), served_model="test-local-model",
                    gpu_layers=99, backend="cuda")
    encoded = json.dumps(manifest).encode()
    (runtime / "local-qwen-runtime.gpu.json").write_bytes(encoded)
    (runtime / "local-qwen-server.pid").write_text("7777")
    (runtime / "local-qwen-server.key").write_text("test-only-model-key")
    state = dict(process_id=7777, device="GPU", port=8790,
                 signature=hashlib.sha256(encoded).hexdigest())
    if mismatch == "signature":
        state["signature"] = "0" * 64
    elif mismatch == "state_pid":
        state["process_id"] = 8888
    elif mismatch == "port":
        state["port"] = 8791
    elif mismatch == "device":
        state["device"] = "CPU"
    (runtime / "local-qwen-server.state.json").write_text(json.dumps(state))
    wrapper = tmp_path / "check.ps1"
    wrapper.write_text("""
param([string]$ModelScript, [string]$Runtime, [string]$Mismatch)
$ErrorActionPreference = 'Stop'
function Get-CimInstance { return $null }
function Get-NetTCPConnection {
    [PSCustomObject]@{OwningProcess = $(if ($Mismatch -eq 'listener') {8888} else {7777})}
}
function Invoke-RestMethod {
    param($Uri, $Headers, $TimeoutSec)
    if ($Uri.EndsWith('/v1/models')) {
        if ($Headers.Authorization -ne 'Bearer test-only-model-key') { throw 'Missing API key' }
        if ($Mismatch -eq 'key') { throw 'Unauthorized' }
        return @{data = @(@{id = $(if ($Mismatch -eq 'model') {'other-model'} else {'test-local-model'})})}
    }
    return @{status = 'ok'}
}
function Start-Process { throw 'Must reuse the existing model' }
function Stop-Process { throw 'Must preserve the existing model' }
$result = & $ModelScript -Action start -Runtime $Runtime -Device GPU -Port 8790
$result | ConvertTo-Json -Compress
""", encoding="utf-8")
    result = subprocess.run(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(wrapper),
                             "-ModelScript", str(SCRIPT), "-Runtime", str(runtime), "-Mismatch", mismatch or "none"],
                            capture_output=True, text=True, encoding="utf-8", errors="replace")
    if mismatch:
        assert result.returncode != 0
        assert "already occupied" in result.stderr
    else:
        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout.strip().splitlines()[-1])
        assert payload["ProcessId"] == 7777
        assert payload["StartedByCaller"] is False
