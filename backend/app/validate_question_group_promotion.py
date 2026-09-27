from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from app.questions.question_group_promotion import (
    DEFAULT_QUESTION_GROUP_PROMOTION_ROOT,
    DEFAULT_SOURCE_CATALOG_PATH,
    QuestionGroupPromotionValidator,
)
from app.questions.question_group_review_overlay import (
    DEFAULT_QUESTION_GROUP_REVIEW_ROOT,
)
from app.questions.question_group_staging import (
    DEFAULT_QUESTION_GROUP_STAGING_PATH,
)
from app.questions.question_group_visual_assets import (
    DEFAULT_QUESTION_GROUP_VISUAL_ASSET_ROOT,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate DATA-MATH12-011 and materialize its internal snapshot."
    )
    parser.add_argument(
        "--promotion-root", type=Path, default=DEFAULT_QUESTION_GROUP_PROMOTION_ROOT
    )
    parser.add_argument(
        "--group-path", type=Path, default=DEFAULT_QUESTION_GROUP_STAGING_PATH
    )
    parser.add_argument(
        "--review-root", type=Path, default=DEFAULT_QUESTION_GROUP_REVIEW_ROOT
    )
    parser.add_argument(
        "--visual-root", type=Path, default=DEFAULT_QUESTION_GROUP_VISUAL_ASSET_ROOT
    )
    parser.add_argument(
        "--source-catalog", type=Path, default=DEFAULT_SOURCE_CATALOG_PATH
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = QuestionGroupPromotionValidator().validate(
        promotion_root=args.promotion_root,
        group_staging_path=args.group_path,
        review_root=args.review_root,
        visual_root=args.visual_root,
        source_catalog_path=args.source_catalog,
    )
    print(json.dumps(report.as_dict(), ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report.is_valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
