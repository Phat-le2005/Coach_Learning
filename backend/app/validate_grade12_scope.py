from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from app.curriculum.grade12_scope import (
    DEFAULT_GRADE12_SCOPE_PATH,
    Grade12ScopeValidator,
)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate the Grade-12 scope registry.")
    parser.add_argument("--path", type=Path, default=DEFAULT_GRADE12_SCOPE_PATH)
    args = parser.parse_args(argv)
    report = Grade12ScopeValidator().validate(args.path)
    print(json.dumps(report.as_dict(), ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report.is_valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
