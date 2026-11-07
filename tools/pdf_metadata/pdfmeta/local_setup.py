"""Set up pinned llama.cpp and Qwen files in the configured local runtime."""
from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import zipfile

import httpx

from .storage import file_hash, write_json


RELEASE = "b12032"
REPO = "ggml-org/Qwen3-VL-2B-Instruct-GGUF"
REVISION = "ea6a11058182570be6436b9a2e4ee7f7b49f908d"
FILES = [
    (f"https://github.com/ggml-org/llama.cpp/releases/download/{RELEASE}/llama-{RELEASE}-bin-win-cpu-x64.zip",
     f"downloads/llama-{RELEASE}-win-cpu-x64.zip", "5296f5d18bb7d422c7c26f4bb9bc796d9d4f41e1312a8c296cff475bdc60d0d4", 24582754),
    (f"https://huggingface.co/{REPO}/resolve/{REVISION}/Qwen3-VL-2B-Instruct-Q8_0.gguf",
     "models/qwen3-vl-2b/Qwen3-VL-2B-Instruct-Q8_0.gguf", "b7802e29f71a9e5b5e3f83f613df898a2204342dcea71a231ea501d481813c39", 1834427296),
    (f"https://huggingface.co/{REPO}/resolve/{REVISION}/mmproj-Qwen3-VL-2B-Instruct-Q8_0.gguf",
     "models/qwen3-vl-2b/mmproj-Qwen3-VL-2B-Instruct-Q8_0.gguf", "69066c8f279ec85ff48ab4059f6ebba0d2932ca57667f2bbdac7d9805bca9e7b", 445053056),
]


def download(url: str, target: Path, digest: str, size: int):
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        if target.stat().st_size == size and file_hash(target) == digest:
            print(f"Verified existing {target.name}", flush=True)
            return
        raise ValueError(f"EXISTING_FILE_HASH_MISMATCH:{target.name}")
    pending = target.with_suffix(target.suffix + ".part")
    offset = pending.stat().st_size if pending.exists() else 0
    if offset > size:
        raise ValueError("PARTIAL_DOWNLOAD_LARGER_THAN_SOURCE")
    if offset < size:
        with httpx.Client(timeout=httpx.Timeout(120, connect=30), follow_redirects=True) as client:
            with client.stream("GET", url, headers={"Range": f"bytes={offset}-"} if offset else {}) as response:
                if response.status_code not in {200, 206}:
                    raise ValueError(f"DOWNLOAD_HTTP_{response.status_code}:{target.name}")
                if offset and response.status_code == 200:
                    offset = 0
                received, mark = offset, offset
                with pending.open("ab" if offset else "wb") as stream:
                    for part in response.iter_bytes(chunk_size=1024 * 1024):
                        received += len(part)
                        if received > size:
                            raise ValueError("DOWNLOAD_SIZE_EXCEEDED")
                        stream.write(part)
                        if received - mark >= 128 * 1024 * 1024:
                            print(f"{target.name}: {received/size:.0%}", flush=True)
                            mark = received
    if pending.stat().st_size != size or file_hash(pending) != digest:
        raise ValueError(f"DOWNLOAD_CHECKSUM_MISMATCH:{target.name}")
    pending.replace(target)
    print(f"Downloaded and SHA-256 verified {target.name}", flush=True)


def setup(runtime: Path):
    runtime = runtime.resolve()
    for url, relative, digest, size in FILES:
        download(url, runtime / relative, digest, size)
    binary_root = runtime / "llama.cpp" / RELEASE
    archive_path = runtime / FILES[0][1]
    with zipfile.ZipFile(archive_path) as archive:
        for info in archive.infolist():
            target = (binary_root / info.filename).resolve()
            if not target.is_relative_to(binary_root.resolve()):
                raise ValueError("RUNTIME_ARCHIVE_PATH_INVALID")
        archive.extractall(binary_root)
    servers = list(binary_root.rglob("llama-server.exe"))
    if len(servers) != 1:
        raise ValueError("LLAMA_SERVER_BINARY_NOT_FOUND")
    manifest = {"schema_version": "local-qwen-runtime/v1", "model_repo": REPO, "revision": REVISION,
        "runtime_release": RELEASE, "server_path": str(servers[0]), "server_sha256": file_hash(servers[0]),
        "model_path": str(runtime / FILES[1][1]), "model_sha256": FILES[1][2],
        "projector_path": str(runtime / FILES[2][1]), "projector_sha256": FILES[2][2],
        "served_model": "qwen3-vl-2b-instruct", "threads": 3, "gpu_layers": 0,
        "context_size": 16384, "downloaded_bytes": sum(f[3] for f in FILES)}
    write_json(runtime / "local-qwen-runtime.json", manifest)
    print(f"Ready: {runtime / 'local-qwen-runtime.json'}", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime", type=Path, required=True)
    setup(parser.parse_args().runtime)


if __name__ == "__main__":
    main()
