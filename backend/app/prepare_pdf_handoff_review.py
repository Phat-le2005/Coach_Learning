from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from app.questions.pdf_handoff_review import DEFAULT_REVIEW_OUTPUT, build_review, validate_review, write_review
from app.questions.pdf_handoff_staging import DEFAULT_SOURCE


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Prepare/validate all 200 source questions for review. Does not connect to or replace a database.")
    parser.add_argument("--source-package", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--path", type=Path, default=DEFAULT_REVIEW_OUTPUT)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    try:
        package = build_review(args.source_package, args.path)
        if args.write:
            write_review(package, args.path, args.source_package)
        validate_review(package, args.path, args.source_package)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({"status": "FAIL", "error": str(exc)}, ensure_ascii=True))
        return 1
    print(json.dumps({**package.report, "aggregate_sha256": package.aggregate_sha256}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
