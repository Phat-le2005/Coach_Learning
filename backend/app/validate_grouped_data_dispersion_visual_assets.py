from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from app.questions.grouped_data_dispersion_visual_assets import (
    DEFAULT_GROUPED_DATA_DISPERSION_VISUAL_ASSET_PATH,
    GroupedDataDispersionVisualAssetValidator,
)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate curated DATA-MATH12-022 visual/source assets."
    )
    parser.add_argument(
        "--visual-path",
        type=Path,
        default=DEFAULT_GROUPED_DATA_DISPERSION_VISUAL_ASSET_PATH,
    )
    args = parser.parse_args(argv)
    report = GroupedDataDispersionVisualAssetValidator().validate(args.visual_path)
    print(json.dumps(report.as_dict(), ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report.is_valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
