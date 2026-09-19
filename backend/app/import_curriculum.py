import argparse
import json
import logging
import sys
from collections.abc import Sequence

from app.core.config import get_settings
from app.core.exceptions import ApplicationError
from app.core.logging import configure_logging
from app.curriculum.import_service import CurriculumImportService
from app.database.session import dispose_engine, get_session_factory

logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate and import a versioned curriculum dataset.")
    parser.add_argument("--dataset", required=True, help="Stable dataset_code from manifest.json.")
    parser.add_argument("--dry-run", action="store_true", help="Validate and preview without writes.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    settings = get_settings()
    configure_logging(settings.debug and settings.app_env != "production")
    try:
        with get_session_factory()() as session:
            service = CurriculumImportService(session)
            result = (
                service.preview(arguments.dataset)
                if arguments.dry_run
                else service.import_dataset(arguments.dataset)
            )
        # Keep CLI output portable on Windows consoles that do not default to UTF-8.
        print(json.dumps(result.model_dump(mode="json"), ensure_ascii=True, sort_keys=True))
        return 0
    except ApplicationError as error:
        print(f"{error.code}: {error.message}", file=sys.stderr)
        return 2
    except Exception as error:
        logger.error("Curriculum import failed (%s)", type(error).__name__)
        print("CURRICULUM_IMPORT_FAILED: Transaction rolled back.", file=sys.stderr)
        return 1
    finally:
        dispose_engine()


if __name__ == "__main__":
    raise SystemExit(main())
