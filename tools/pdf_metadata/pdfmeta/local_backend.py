"""CPU/CUDA profiles sharing the same pinned OCR weights and runtime directory."""
from __future__ import annotations

import argparse
from pathlib import Path
import zipfile

from .storage import file_hash, read_json, write_json


GPU_RELEASE = 'b12032'
CUDA_ARCHIVES = (
    ('llama-b12032-bin-win-cuda-12.4-x64.zip',
     '36c7e24ad048cceabf00c1b49d0f0411b954c6a410a7ff4300af8721a94fd00a', 279952566),
    ('cudart-llama-bin-win-cuda-12.4-x64.zip',
     '8c79a9b226de4b3cacfd1f83d24f962d0773be79f1e7b75c6af4ded7e32ae1d6', 391443627),
)
HARDWARE_FIELDS = {'threads', 'downloaded_bytes', 'server_path', 'server_sha256',
                   'gpu_layers', 'mmproj_offload', 'backend', 'backend_files'}


def manifest_path(runtime: Path, device='cpu'):
    device = device.lower()
    if device not in {'cpu', 'gpu'}:
        raise ValueError('LOCAL_DEVICE_MUST_BE_CPU_OR_GPU')
    return Path(runtime) / ('local-qwen-runtime.gpu.json' if device == 'gpu' else 'local-qwen-runtime.json')


def load_manifest(runtime: Path, device='cpu'):
    path = manifest_path(runtime, device)
    if not path.is_file():
        raise ValueError('GPU_PROFILE_MISSING_RUN_LOCAL_BACKEND_SETUP' if device.lower() == 'gpu'
                         else 'LOCAL_RUNTIME_MISSING_RUN_LOCAL_SETUP')
    manifest = read_json(path)
    if device.lower() == 'gpu' and (manifest.get('gpu_layers', 0) <= 0 or manifest.get('backend') != 'cuda'):
        raise ValueError('GPU_PROFILE_REQUIRES_CUDA_OFFLOAD')
    if device.lower() == 'cpu' and manifest.get('gpu_layers', 0) != 0:
        raise ValueError('CPU_PROFILE_REQUIRES_ZERO_GPU_LAYERS')
    return manifest


def semantic_model(model):
    return {k: v for k, v in model.items() if k not in HARDWARE_FIELDS}


def verify_weights(manifest):
    for field in ('model', 'projector'):
        digest = manifest.get(field + '_sha256')
        path = Path(manifest.get(field + '_path', ''))
        if not digest or len(digest) != 64 or not path.is_file() or file_hash(path) != digest:
            raise ValueError('LOCAL_WEIGHTS_CHECKSUM_MISMATCH:' + field)


def setup_gpu(runtime: Path):
    """Install CUDA alongside CPU, without rewriting the existing CPU manifest."""
    from .local_setup import download
    runtime = runtime.resolve()
    cpu = load_manifest(runtime)
    if cpu.get('runtime_release') != GPU_RELEASE:
        raise ValueError('GPU_SETUP_REQUIRES_MATCHING_B12032_CPU_RUNTIME')
    verify_weights(cpu)
    binary_root = runtime / 'llama.cpp' / (GPU_RELEASE + '-cuda-12.4')
    for name, digest, size in CUDA_ARCHIVES:
        archive_path = runtime / 'downloads' / name
        download(f'https://github.com/ggml-org/llama.cpp/releases/download/{GPU_RELEASE}/{name}',
                 archive_path, digest, size)
        with zipfile.ZipFile(archive_path) as archive:
            for info in archive.infolist():
                target = (binary_root / info.filename).resolve()
                if not target.is_relative_to(binary_root.resolve()):
                    raise ValueError('RUNTIME_ARCHIVE_PATH_INVALID')
                # An already installed executable/DLL may be in use. Never overwrite
                # identical installed files (and never silently trust different ones).
                if target.is_file():
                    import hashlib
                    expected = hashlib.sha256(archive.read(info)).hexdigest()
                    if file_hash(target) != expected:
                        raise ValueError('EXISTING_CUDA_FILE_HASH_MISMATCH:' + info.filename)
                else:
                    archive.extract(info, binary_root)
    servers = list(binary_root.rglob('llama-server.exe'))
    if len(servers) != 1 or not (servers[0].parent / 'ggml-cuda.dll').is_file():
        raise ValueError('CUDA_SERVER_BINARY_NOT_FOUND')
    backend_files = [{'path': str(p), 'sha256': file_hash(p)}
                     for p in sorted(binary_root.rglob('*.dll'))]
    gpu = dict(cpu, server_path=str(servers[0]), server_sha256=file_hash(servers[0]),
               gpu_layers=99, mmproj_offload=True, backend='cuda', backend_files=backend_files)
    write_json(manifest_path(runtime, 'gpu'), gpu)
    print('GPU profile ready: ' + str(manifest_path(runtime, 'gpu')), flush=True)
    return gpu


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', type=Path, required=True)
    parser.add_argument('--setup-gpu', action='store_true', required=True)
    setup_gpu(parser.parse_args().runtime)


if __name__ == '__main__':
    main()
