"""Explicit, streaming preparation of official RapidLaTeXOCR CPU checkpoints.

Without --download this command only verifies already provisioned files.
No FastAPI request calls this script. Downloaded files stay in gitignored .tmp/.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import urlopen

from app.core.exceptions import ApplicationError
from app.math_ocr.local_rapid_adapter import _MIN_MODEL_BYTES, inspect_cpu_model_files


OFFICIAL_RELEASE = "https://github.com/RapidAI/RapidLaTeXOCR/releases/download/v0.0.0"
DEFAULT_TARGET = Path(__file__).resolve().parents[2] / ".tmp" / "ocr_cpu_models"
ALLOWED_REDIRECT_HOSTS = {
    "github.com", "release-assets.githubusercontent.com", "objects.githubusercontent.com",
}


def _download_one(target: Path, name: str) -> None:
    url = f"{OFFICIAL_RELEASE}/{name}"
    temporary = target / f"{name}.part"
    with urlopen(url, timeout=45) as response:
        host = urlparse(response.geturl()).hostname
        if host not in ALLOWED_REDIRECT_HOSTS:
            raise RuntimeError("Checkpoint redirect left the official GitHub release hosts.")
        with temporary.open("wb") as output:
            while chunk := response.read(64 * 1024):
                output.write(chunk)
    if temporary.stat().st_size < _MIN_MODEL_BYTES[name]:
        raise RuntimeError(f"The downloaded {name} is incomplete.")
    temporary.replace(target / name)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", type=Path, default=DEFAULT_TARGET)
    parser.add_argument("--download", action="store_true", help="Explicitly fetch missing files from the official GitHub release")
    args = parser.parse_args(argv)
    target = args.target.resolve()
    if args.download:
        target.mkdir(parents=True, exist_ok=True)
        for name, minimum in _MIN_MODEL_BYTES.items():
            current = target / name
            if current.is_file() and current.stat().st_size >= minimum:
                continue
            print(f"Fetching official checkpoint: {name}")
            try:
                _download_one(target, name)
            except Exception as exc:
                print(f"Download failed for {name}: {type(exc).__name__}", file=sys.stderr)
                return 2
    try:
        _, sizes = inspect_cpu_model_files(target)
    except ApplicationError as exc:
        print(f"Checkpoint verification failed: {exc.code}", file=sys.stderr)
        return 2
    hashes: dict[str, str] = {}
    for name in _MIN_MODEL_BYTES:
        with (target / name).open("rb") as model_file:
            hashes[name] = hashlib.file_digest(model_file, "sha256").hexdigest()
    inventory = {"source": OFFICIAL_RELEASE, "sizes_bytes": sizes, "sha256": hashes}
    (target / "model_inventory.json").write_text(
        json.dumps(inventory, indent=2), encoding="utf-8",
    )
    print(json.dumps(inventory, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
