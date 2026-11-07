from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from app.questions.pdf_handoff_staging import (
    DEFAULT_OUTPUT, DEFAULT_SOURCE, HandoffValidationError,
    build_bundle, validate_bundle, write_bundle,
)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify the pinned 200-question handoff and non-importable staging; no DB writes.")
    parser.add_argument("--source-package", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--path", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--write", action="store_true", help="Create deterministic staging files; refuse overwriting edited output.")
    args = parser.parse_args(argv)
    try:
        bundle = build_bundle(args.source_package)
        if args.write:
            write_bundle(bundle, args.path, args.source_package)
        validate_bundle(bundle, args.path)
    except (HandoffValidationError, OSError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({"status": "FAIL", "error": str(exc)}, ensure_ascii=True))
        return 1
    print(json.dumps({**bundle.files["validation_report.json"], "aggregate_sha256": bundle.aggregate_sha256}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
