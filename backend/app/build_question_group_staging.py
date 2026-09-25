from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from app.questions.question_group_staging import (
    DEFAULT_QUESTION_GROUP_STAGING_PATH,
    QuestionGroupStagingBuildError,
    QuestionGroupStagingBuilder,
)
from app.questions.staging_validator import (
    DEFAULT_CURRICULUM_STAGING_PATH,
    DEFAULT_QUESTION_STAGING_PATH,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build deterministic non-production QuestionGroup staging data."
    )
    parser.add_argument("--path", type=Path, default=DEFAULT_QUESTION_STAGING_PATH)
    parser.add_argument(
        "--curriculum-path",
        type=Path,
        default=DEFAULT_CURRICULUM_STAGING_PATH,
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_QUESTION_GROUP_STAGING_PATH,
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    builder = QuestionGroupStagingBuilder()
    try:
        build = builder.build(args.path, args.curriculum_path)
        builder.write(build, args.output)
    except (OSError, QuestionGroupStagingBuildError) as error:
        print(json.dumps(
            {"dataset_code": "DATA-MATH12-006", "status": "FAIL", "error": str(error)},
            ensure_ascii=False,
            indent=2,
        ))
        return 1
    print(json.dumps(
        {"status": "PASS", **build.report},
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
