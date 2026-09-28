from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from app.questions.vector_source_staging import (
    DEFAULT_VECTOR_SOURCE_STAGING_PATH,
    VectorQuestionSourceValidator,
)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate vector question source staging.")
    parser.add_argument("--path", type=Path, default=DEFAULT_VECTOR_SOURCE_STAGING_PATH)
    args = parser.parse_args(argv)
    report = VectorQuestionSourceValidator().validate(args.path)
    print(json.dumps(report.as_dict(), ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report.is_valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
