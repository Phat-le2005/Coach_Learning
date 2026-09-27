from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from app.questions.question_group_review_overlay import (
    DEFAULT_QUESTION_GROUP_REVIEW_ROOT,
)
from app.questions.question_group_staging import (
    DEFAULT_QUESTION_GROUP_STAGING_PATH,
)
from app.questions.question_group_visual_assets import (
    DEFAULT_QUESTION_GROUP_VISUAL_ASSET_ROOT,
    QuestionGroupVisualAssetValidator,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate the read-only QuestionGroup visual asset registry."
    )
    parser.add_argument(
        "--asset-root", type=Path, default=DEFAULT_QUESTION_GROUP_VISUAL_ASSET_ROOT
    )
    parser.add_argument(
        "--group-path", type=Path, default=DEFAULT_QUESTION_GROUP_STAGING_PATH
    )
    parser.add_argument(
        "--review-root", type=Path, default=DEFAULT_QUESTION_GROUP_REVIEW_ROOT
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = QuestionGroupVisualAssetValidator().validate(
        args.asset_root, args.group_path, args.review_root
    )
    print(json.dumps(report.as_dict(), ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report.is_valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
