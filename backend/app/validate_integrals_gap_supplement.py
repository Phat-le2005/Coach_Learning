from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from app.questions.integrals_academic_review import (
    DEFAULT_INTEGRALS_ACADEMIC_REVIEW_PATH,
)
from app.questions.integrals_gap_supplement import (
    DEFAULT_INTEGRALS_GAP_SUPPLEMENT_PATH,
    IntegralsGapSupplementValidator,
)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate curated DATA-MATH12-026 Integrals gap supplement overlay."
    )
    parser.add_argument(
        "--supplement-path",
        type=Path,
        default=DEFAULT_INTEGRALS_GAP_SUPPLEMENT_PATH,
    )
    parser.add_argument(
        "--base-path",
        type=Path,
        default=DEFAULT_INTEGRALS_ACADEMIC_REVIEW_PATH,
    )
    args = parser.parse_args(argv)
    report = IntegralsGapSupplementValidator().validate(
        args.supplement_path, args.base_path
    )
    print(json.dumps(report.as_dict(), ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report.is_valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
