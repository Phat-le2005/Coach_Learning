from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from app.questions.question_group_review_overlay import (
    DEFAULT_QUESTION_GROUP_REVIEW_ROOT,
)
from app.questions.question_group_review_validator import (
    QuestionGroupReviewValidator,
)
from app.questions.question_group_staging import (
    DEFAULT_QUESTION_GROUP_STAGING_PATH,
)
from app.questions.staging_validator import DEFAULT_CURRICULUM_STAGING_PATH


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate non-production QuestionGroup academic review overlays."
    )
    parser.add_argument(
        "--group-path",
        type=Path,
        default=DEFAULT_QUESTION_GROUP_STAGING_PATH,
    )
    parser.add_argument(
        "--curriculum-path",
        type=Path,
        default=DEFAULT_CURRICULUM_STAGING_PATH,
    )
    parser.add_argument(
        "--review-root",
        type=Path,
        default=DEFAULT_QUESTION_GROUP_REVIEW_ROOT,
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = QuestionGroupReviewValidator().validate(
        args.group_path,
        args.curriculum_path,
        args.review_root,
    )
    print(json.dumps(report.as_dict(), ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report.is_valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
