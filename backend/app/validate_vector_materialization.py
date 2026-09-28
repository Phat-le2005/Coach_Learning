from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from app.questions.vector_materialization import (
    DEFAULT_VECTOR_MATERIALIZATION_PATH,
    VectorQuestionMaterializationValidator,
)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate the read-only DATA-MATH12-016 vector materialization."
    )
    parser.add_argument(
        "--dataset-path",
        type=Path,
        default=DEFAULT_VECTOR_MATERIALIZATION_PATH,
    )
    args = parser.parse_args(argv)
    report = VectorQuestionMaterializationValidator().validate(args.dataset_path)
    print(json.dumps(report.as_dict(), ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report.is_valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
