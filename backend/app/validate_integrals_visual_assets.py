from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from app.questions.integrals_visual_assets import (
    DEFAULT_INTEGRALS_VISUAL_ASSET_PATH,
    IntegralsVisualAssetValidator,
)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate curated DATA-MATH12-027 visual/source assets."
    )
    parser.add_argument(
        "--visual-path",
        type=Path,
        default=DEFAULT_INTEGRALS_VISUAL_ASSET_PATH,
    )
    args = parser.parse_args(argv)
    report = IntegralsVisualAssetValidator().validate(args.visual_path)
    print(json.dumps(report.as_dict(), ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report.is_valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
