from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from app.questions.oxyz_academic_review import (
    DEFAULT_OXYZ_ACADEMIC_REVIEW_PATH,
    OxyzAcademicReviewValidator,
)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate curated DATA-MATH12-024 Oxyz academic review."
    )
    parser.add_argument(
        "--review-path",
        type=Path,
        default=DEFAULT_OXYZ_ACADEMIC_REVIEW_PATH,
    )
    args = parser.parse_args(argv)
    report = OxyzAcademicReviewValidator().validate(args.review_path)
    print(json.dumps(report.as_dict(), ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report.is_valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
