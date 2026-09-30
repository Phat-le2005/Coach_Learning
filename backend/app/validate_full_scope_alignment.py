from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from app.curriculum.full_scope_alignment import (
    DEFAULT_FULL_SCOPE_ALIGNMENT_PATH,
    REPO_ROOT,
    FullScopeAlignmentValidator,
)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate DATA-MATH12-033 full-scope Grade 12 GDPT 2018 graph alignment candidate."
    )
    parser.add_argument(
        "--alignment-path",
        type=Path,
        default=DEFAULT_FULL_SCOPE_ALIGNMENT_PATH,
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=REPO_ROOT,
    )
    args = parser.parse_args(argv)
    report = FullScopeAlignmentValidator().validate(
        args.alignment_path, repo_root=args.repo_root
    )
    print(json.dumps(report.as_dict(), ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report.is_valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
