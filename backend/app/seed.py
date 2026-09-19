import argparse
import json
import logging
import sys
from collections.abc import Sequence

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.database.session import dispose_engine, get_session_factory
from app.seed_service import RESET_CONFIRMATION, SeedOperationError, SeedService

logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage deterministic EduMS development seed data.")
    parser.add_argument("command", nargs="?", choices=("seed", "reset"), default="seed")
    parser.add_argument(
        "--confirm",
        default="",
        help=f"Required for reset; exact value: {RESET_CONFIRMATION}",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    settings = get_settings()
    configure_logging(settings.debug and settings.app_env != "production")
    try:
        with get_session_factory()() as session:
            service = SeedService(session, settings)
            summary = service.reset(arguments.confirm) if arguments.command == "reset" else service.seed()
        print(json.dumps(summary.to_dict(), sort_keys=True))
        return 0
    except SeedOperationError as error:
        print(f"{error.code}: {error.message}", file=sys.stderr)
        return 2
    except Exception as error:
        logger.error("Seed command failed (%s)", type(error).__name__)
        print("SEED_FAILED: Seed transaction failed and was rolled back.", file=sys.stderr)
        return 1
    finally:
        dispose_engine()


if __name__ == "__main__":
    raise SystemExit(main())
