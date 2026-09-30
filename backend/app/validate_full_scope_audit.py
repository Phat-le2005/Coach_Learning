from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from app.curriculum.full_scope_audit import (
    DEFAULT_FULL_SCOPE_AUDIT_PATH,
    FullScopeAuditValidator,
)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate DATA-MATH12-032 full-scope Grade 12 GDPT 2018 audit."
    )
    parser.add_argument(
        "--audit-path",
        type=Path,
        default=DEFAULT_FULL_SCOPE_AUDIT_PATH,
    )
    args = parser.parse_args(argv)
    report = FullScopeAuditValidator().validate(args.audit_path)
    print(json.dumps(report.as_dict(), ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report.is_valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
