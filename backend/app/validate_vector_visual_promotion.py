from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from app.questions.vector_visual_promotion import (
    DEFAULT_VECTOR_PROMOTION_ROOT,
    DEFAULT_VECTOR_VISUAL_ASSET_ROOT,
    VectorVisualPromotionValidator,
)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate DATA-MATH12-018 Vector visual and promotion preflight."
    )
    parser.add_argument(
        "--visual-root", type=Path, default=DEFAULT_VECTOR_VISUAL_ASSET_ROOT
    )
    parser.add_argument(
        "--promotion-root", type=Path, default=DEFAULT_VECTOR_PROMOTION_ROOT
    )
    args = parser.parse_args(argv)
    report = VectorVisualPromotionValidator().validate(
        visual_root=args.visual_root,
        promotion_root=args.promotion_root,
    )
    print(json.dumps(report.as_dict(), ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report.is_valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
