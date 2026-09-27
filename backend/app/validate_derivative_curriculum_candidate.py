from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from app.curriculum.derivative_candidate import (
    DEFAULT_CANONICAL_CURRICULUM_PATH,
    DEFAULT_DERIVATIVE_STAGING_PATH,
    DEFAULT_PRODUCTION_BRIDGE_ROOT,
    DerivativeCurriculumCandidateValidator,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate the non-importable derivative curriculum candidate."
    )
    parser.add_argument(
        "--canonical-path", type=Path, default=DEFAULT_CANONICAL_CURRICULUM_PATH
    )
    parser.add_argument(
        "--staging-path", type=Path, default=DEFAULT_DERIVATIVE_STAGING_PATH
    )
    parser.add_argument(
        "--bridge-root", type=Path, default=DEFAULT_PRODUCTION_BRIDGE_ROOT
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = DerivativeCurriculumCandidateValidator().validate(
        canonical_path=args.canonical_path,
        staging_path=args.staging_path,
        bridge_root=args.bridge_root,
    )
    print(json.dumps(report.as_dict(), ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report.is_valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
