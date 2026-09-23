from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from app.curriculum.staging_validator import (
    DEFAULT_STAGING_PATH,
    CurriculumStagingValidator,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate a non-canonical curriculum staging dataset."
    )
    parser.add_argument(
        "--path",
        type=Path,
        default=DEFAULT_STAGING_PATH,
        help="Path to the staging taxonomy directory.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = CurriculumStagingValidator().validate(args.path)
    print(json.dumps(report.as_dict(), ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report.is_valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
