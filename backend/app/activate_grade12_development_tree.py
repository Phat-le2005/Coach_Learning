from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence

from app.core.config import get_settings
from app.core.exceptions import ApplicationError
from app.curriculum.development_tree import DevelopmentTreeActivationService
from app.database.session import dispose_engine, get_session_factory


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Activate the complete six-chapter Math 12 tree in development/test."
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Validate and report without database writes."
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    settings = get_settings()
    try:
        with get_session_factory()() as session:
            service = DevelopmentTreeActivationService(session)
            result = (
                service.preview()
                if arguments.dry_run
                else service.activate(app_env=settings.app_env)
            )
        print(
            json.dumps(
                result.model_dump(mode="json"), ensure_ascii=True, sort_keys=True
            )
        )
        return 0
    except ApplicationError as error:
        print(f"{error.code}: {error.message}", file=sys.stderr)
        return 2
    finally:
        dispose_engine()


if __name__ == "__main__":
    raise SystemExit(main())
