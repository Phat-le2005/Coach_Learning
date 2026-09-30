from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from app.questions.grouped_data_dispersion_gap_rescan import (
    DEFAULT_GROUPED_DATA_DISPERSION_GAP_RESCAN_PATH,
    GroupedDataDispersionGapRescanValidator,
)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate curated DATA-MATH12-031 grouped-data dispersion gap rescan v0_2."
    )
    parser.add_argument(
        "--scan-path",
        type=Path,
        default=DEFAULT_GROUPED_DATA_DISPERSION_GAP_RESCAN_PATH,
    )
    args = parser.parse_args(argv)
    report = GroupedDataDispersionGapRescanValidator().validate(args.scan_path)
    print(json.dumps(report.as_dict(), ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report.is_valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
