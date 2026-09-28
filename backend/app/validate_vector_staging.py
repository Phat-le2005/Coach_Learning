from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from app.curriculum.vector_staging import (
    DEFAULT_VECTOR_STAGING_PATH,
    VectorCurriculumStagingValidator,
)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate vector curriculum staging.")
    parser.add_argument("--path", type=Path, default=DEFAULT_VECTOR_STAGING_PATH)
    args = parser.parse_args(argv)
    report = VectorCurriculumStagingValidator().validate(args.path)
    print(json.dumps(report.as_dict(), ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report.is_valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
