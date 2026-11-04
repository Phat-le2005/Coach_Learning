from __future__ import annotations

import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import tempfile
import time
import uuid


def configure_storage(root: Path) -> dict[str, str]:
    """Set download/temp locations before importing any inference libraries."""
    root = root.resolve()
    paths = {
        "HF_HOME": root / "huggingface",
        "HF_HUB_CACHE": root / "huggingface" / "hub",
        "HF_XET_CACHE": root / "huggingface" / "xet",
        "TORCH_HOME": root / "torch",
        "PADDLE_PDX_CACHE_HOME": root / "paddlex",
        "PADDLE_HOME": root / "paddle",
        "PADDLE_EXTENSION_DIR": root / "paddle-extensions",
        "XDG_CACHE_HOME": root / "cache",
        "MODELSCOPE_CACHE": root / "modelscope",
        "PIP_CACHE_DIR": root / "pip-cache",
        "MPLCONFIGDIR": root / "matplotlib",
        "TEMP": root / "temp",
        "TMP": root / "temp",
    }
    for key, path in paths.items():
        path.mkdir(parents=True, exist_ok=True)
        os.environ[key] = str(path)
    tempfile.tempdir = str(paths["TEMP"])
    os.environ.setdefault("OMP_NUM_THREADS", "3")
    os.environ.setdefault("MKL_NUM_THREADS", "3")
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
    return {key: str(value) for key, value in paths.items()}


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for part in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(part)
    return digest.hexdigest()


def inference_versions() -> dict[str, str]:
    versions = {name: importlib.metadata.version(name) for name in ("paddleocr", "paddlex")}
    for name in ("paddlepaddle", "paddlepaddle-gpu"):
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            pass
    return versions


def write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pending = path.with_name(path.name + '.' + uuid.uuid4().hex + '.pending')
    try:
        pending.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        # A dashboard reader or antivirus can briefly hold the old file on
        # Windows. Distinct temporary files also prevent concurrent publishers
        # from renaming each other's partial writes.
        for attempt in range(20):
            try:
                pending.replace(path)
                break
            except PermissionError:
                if attempt == 19:raise
                time.sleep(.05)
    finally:
        pending.unlink(missing_ok=True)


def read_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def write_jsonl(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pending = path.with_name(path.name + '.' + uuid.uuid4().hex + '.pending')
    try:
        with pending.open("w", encoding="utf-8", newline="\n") as stream:
            for record in records:
                stream.write(json.dumps(record, ensure_ascii=False) + "\n")
        for attempt in range(20):
            try:
                pending.replace(path)
                break
            except PermissionError:
                if attempt == 19:raise
                time.sleep(.05)
    finally:
        pending.unlink(missing_ok=True)
