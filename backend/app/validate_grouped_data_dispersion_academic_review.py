from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from app.questions.grouped_data_dispersion_academic_review import (
    DEFAULT_GROUPED_DATA_DISPERSION_ACADEMIC_REVIEW_PATH,
    GroupedDataDispersionAcademicReviewValidator,
)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate curated DATA-MATH12-021 academic review."
    )
    parser.add_argument(
        "--review-path",
        type=Path,
        default=DEFAULT_GROUPED_DATA_DISPERSION_ACADEMIC_REVIEW_PATH,
    )
    args = parser.parse_args(argv)
    report = GroupedDataDispersionAcademicReviewValidator().validate(
        args.review_path
    )
    print(json.dumps(report.as_dict(), ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report.is_valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
