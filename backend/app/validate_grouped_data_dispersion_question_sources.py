from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from app.questions.grouped_data_dispersion_source_staging import (
    DEFAULT_GROUPED_DATA_DISPERSION_SOURCE_PATH,
    GroupedDataDispersionQuestionSourceValidator,
)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate grouped-data dispersion question source staging."
    )
    parser.add_argument(
        "--path",
        type=Path,
        default=DEFAULT_GROUPED_DATA_DISPERSION_SOURCE_PATH,
    )
    args = parser.parse_args(argv)
    report = GroupedDataDispersionQuestionSourceValidator().validate(args.path)
    print(json.dumps(report.as_dict(), ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report.is_valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
