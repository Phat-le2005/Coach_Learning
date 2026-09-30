from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from app.questions.oxyz_gap_supplement import (
    DEFAULT_OXYZ_GAP_SUPPLEMENT_PATH,
    OxyzGapSupplementValidator,
)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate curated DATA-MATH12-029 Oxyz gap supplement."
    )
    parser.add_argument(
        "--supplement-path",
        type=Path,
        default=DEFAULT_OXYZ_GAP_SUPPLEMENT_PATH,
    )
    args = parser.parse_args(argv)
    report = OxyzGapSupplementValidator().validate(args.supplement_path)
    print(json.dumps(report.as_dict(), ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report.is_valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
