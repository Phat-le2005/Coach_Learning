import argparse
import json
import logging
import sys
from collections.abc import Sequence

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.database.session import dispose_engine, get_session_factory
from app.students.models import SyntheticProfile
from app.synthetic_student_service import SyntheticGenerationError, SyntheticStudentService

logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate deterministic synthetic student behavior for development and tests."
    )
    parser.add_argument("--count", type=int, default=20, help="Number of students (1-500).")
    parser.add_argument("--seed", type=int, default=42, help="Deterministic simulation seed.")
    parser.add_argument(
        "--profile",
        type=lambda value: SyntheticProfile(value.strip().upper()),
        choices=list(SyntheticProfile),
        default=None,
        help="One profile for the cohort; omit to distribute all profiles.",
    )
    parser.add_argument(
        "--no-study-history",
        action="store_true",
        help="Create attempts without grouping them into study sessions.",
    )
    parser.add_argument("--gap-subject", help="Target Subject code for SPECIFIC_GAP.")
    parser.add_argument("--gap-chapter", help="Filter the gap by Chapter code.")
    parser.add_argument("--gap-topic", help="Filter the gap by Topic code.")
    parser.add_argument("--gap-problem-type", help="Filter the gap by ProblemType code.")
    concepts = parser.add_mutually_exclusive_group()
    concepts.add_argument("--gap-concept", help="Filter the gap by exact Concept code.")
    concepts.add_argument(
        "--gap-prerequisite-concept",
        help="Target a prerequisite Concept and its transitive dependents.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    settings = get_settings()
    configure_logging(settings.debug and settings.app_env != "production")
    try:
        with get_session_factory()() as session:
            summary = SyntheticStudentService(session, settings).generate(
                count=arguments.count,
                seed=arguments.seed,
                profile=arguments.profile,
                include_study_history=not arguments.no_study_history,
                gap_problem_type_code=arguments.gap_problem_type,
                gap_concept_code=arguments.gap_concept,
                gap_prerequisite_concept_code=arguments.gap_prerequisite_concept,
                gap_topic_code=arguments.gap_topic,
                gap_chapter_code=arguments.gap_chapter,
                gap_subject_code=arguments.gap_subject,
            )
        print(json.dumps(summary.to_dict(), sort_keys=True))
        return 0
    except SyntheticGenerationError as error:
        print(f"{error.code}: {error.message}", file=sys.stderr)
        return 2
    except Exception as error:
        logger.error("Synthetic generation failed (%s)", type(error).__name__)
        print(
            "SYNTHETIC_GENERATION_FAILED: Transaction failed and was rolled back.",
            file=sys.stderr,
        )
        return 1
    finally:
        dispose_engine()


if __name__ == "__main__":
    raise SystemExit(main())
