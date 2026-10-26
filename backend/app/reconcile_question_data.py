"""Audit local Question Bank data; --apply quarantines unsafe rows in dev/test.

Usage: python -m app.reconcile_question_data [--apply --backup PATH]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.core.config import get_settings
from app.database.session import get_session_factory
from app.questions.data_reconciliation import apply_plan, build_plan


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="quarantine unsafe rows (development/test only)")
    parser.add_argument("--backup", type=Path, help="new JSON backup path, required for --apply")
    args = parser.parse_args()
    if args.apply and not args.backup:
        parser.error("--apply requires --backup")
    if args.apply and get_settings().app_env not in {"development", "test"}:
        parser.error("database mutation is forbidden outside development/test")
    with get_session_factory()() as session:
        plan = build_plan(session)
        print(json.dumps({"mode": "apply" if args.apply else "dry_run", **plan.summary()}, indent=2))
        if args.apply:
            apply_plan(session, plan, backup_path=args.backup)
            remaining = build_plan(session)
            print(json.dumps({"backup": str(args.backup), "remaining": remaining.summary()}, indent=2))
            if remaining.questions or remaining.groups:
                return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
