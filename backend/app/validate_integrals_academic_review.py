from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from app.questions.integrals_academic_review import (
    DEFAULT_INTEGRALS_ACADEMIC_REVIEW_PATH,
    IntegralsAcademicReviewValidator,
)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate curated DATA-MATH12-023 integral academic review."
    )
    parser.add_argument(
        "--review-path",
        type=Path,
        default=DEFAULT_INTEGRALS_ACADEMIC_REVIEW_PATH,
    )
    args = parser.parse_args(argv)
    report = IntegralsAcademicReviewValidator().validate(args.review_path)
    print(json.dumps(report.as_dict(), ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report.is_valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
