import json
from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.attempts.analytics import real_attempts_query
from app.attempts.models import StudentAttempt, StudySession
from app.classes.models import StudentEnrollment
from app.concepts.models import Concept
from app.core.config import Settings
from app.curriculum.import_service import CurriculumImportService
from app.curriculum.models import Chapter, ProblemType, Topic
from app.generate_synthetic_students import build_parser, main
from app.questions.models import Question
from app.students.models import StudentProfile, SyntheticProfile
from app.subjects.models import Subject
from app.synthetic_student_service import SyntheticGenerationError, SyntheticStudentService
from app.users.models import User

ANCHOR = datetime(2026, 9, 18, 12, tzinfo=UTC)


def test_generator_creates_marked_students_attempts_sessions_and_enrollments(
    db_session: Session,
    settings: Settings,
    synthetic_catalog: dict[str, object],
) -> None:
    summary = SyntheticStudentService(db_session, settings).generate(
        count=5, seed=123, anchor_time=ANCHOR
    ).to_dict()
    assert summary == {
        "students_created": 5,
        "students_updated": 0,
        "attempts_created": 240,
        "study_sessions_created": 40,
        "enrollments_created": 5,
        "profiles": {
            "AVERAGE": 1,
            "INCONSISTENT": 1,
            "SPECIFIC_GAP": 1,
            "STRONG": 1,
            "WEAK": 1,
        },
    }
    profiles = list(
        db_session.scalars(
            select(StudentProfile).where(StudentProfile.is_synthetic.is_(True))
        )
    )
    assert len(profiles) == 5
    assert {profile.synthetic_profile for profile in profiles} == set(SyntheticProfile)
    users = list(db_session.scalars(select(User).where(User.id.in_([p.user_id for p in profiles]))))
    assert all(not user.is_active for user in users)
    attempts = list(db_session.scalars(select(StudentAttempt)))
    assert len(attempts) == 240
    assert all(attempt.is_synthetic and attempt.response_time_ms > 0 for attempt in attempts)
    assert all(attempt.study_session_id is not None for attempt in attempts)
    assert db_session.scalar(select(func.count()).select_from(StudySession)) == 40
    assert db_session.scalar(select(func.count()).select_from(StudentEnrollment)) == 5
    assert list(db_session.scalars(real_attempts_query())) == []
    question = synthetic_catalog["question"]
    assert isinstance(question, Question)
    assert any(attempt.question_id == question.id for attempt in attempts)
    assert all(attempt.problem_type_id is not None for attempt in attempts)

    # The student marker remains authoritative if an individual fact is
    # accidentally inserted without its synthetic marker.
    concepts = synthetic_catalog["concepts"]
    assert isinstance(concepts, list)
    db_session.add(
        StudentAttempt(
            student_id=profiles[0].id,
            concept_id=concepts[0].id,
            is_correct=True,
            response_time_ms=30_000,
            attempted_at=ANCHOR,
            is_synthetic=False,
        )
    )
    db_session.flush()
    assert list(db_session.scalars(real_attempts_query())) == []


def test_same_seed_and_profile_regenerates_same_behavior_without_duplicates(
    db_session: Session,
    settings: Settings,
    synthetic_catalog: dict[str, object],
) -> None:
    service = SyntheticStudentService(db_session, settings)
    first = service.generate(
        count=1,
        seed=456,
        profile=SyntheticProfile.SPECIFIC_GAP,
        anchor_time=ANCHOR,
    )
    assert first.students_created == 1
    before = list(db_session.execute(
        select(
            StudentAttempt.id,
            StudentAttempt.concept_id,
            StudentAttempt.is_correct,
            StudentAttempt.response_time_ms,
            StudentAttempt.attempted_at,
        ).order_by(StudentAttempt.id)
    ))
    second = SyntheticStudentService(db_session, settings).generate(
        count=1,
        seed=456,
        profile=SyntheticProfile.SPECIFIC_GAP,
        anchor_time=ANCHOR,
    )
    after = list(db_session.execute(
        select(
            StudentAttempt.id,
            StudentAttempt.concept_id,
            StudentAttempt.is_correct,
            StudentAttempt.response_time_ms,
            StudentAttempt.attempted_at,
        ).order_by(StudentAttempt.id)
    ))
    assert second.students_created == 0 and second.students_updated == 1
    assert before == after
    assert len(after) == 48
    profile = db_session.scalar(
        select(StudentProfile).where(StudentProfile.is_synthetic.is_(True))
    )
    assert profile is not None and profile.synthetic_profile == SyntheticProfile.SPECIFIC_GAP
    assert db_session.scalar(
        select(func.count())
        .select_from(StudentAttempt)
        .where(StudentAttempt.student_id == profile.id)
    ) == 48


def test_generator_can_omit_study_session_history(
    db_session: Session,
    settings: Settings,
    synthetic_catalog: dict[str, object],
) -> None:
    summary = SyntheticStudentService(db_session, settings).generate(
        count=2,
        seed=5,
        profile=SyntheticProfile.AVERAGE,
        include_study_history=False,
        anchor_time=ANCHOR,
    )
    assert summary.attempts_created == 96 and summary.study_sessions_created == 0
    assert db_session.scalar(select(func.count()).select_from(StudySession)) == 0
    assert all(
        attempt.study_session_id is None
        for attempt in db_session.scalars(select(StudentAttempt))
    )


def test_production_generation_is_blocked_before_writes(
    db_session: Session,
    settings: Settings,
    synthetic_catalog: dict[str, object],
) -> None:
    production = settings.model_copy(update={"app_env": "production"})
    with pytest.raises(SyntheticGenerationError) as error:
        SyntheticStudentService(db_session, production).generate(count=1, seed=1)
    assert error.value.code == "SYNTHETIC_GENERATION_FORBIDDEN"
    assert db_session.scalar(select(func.count()).select_from(StudentAttempt)) == 0
    assert db_session.scalar(
        select(func.count()).select_from(StudentProfile).where(StudentProfile.is_synthetic.is_(True))
    ) == 0


def test_cli_parser_supports_required_options() -> None:
    args = build_parser().parse_args(
        [
            "--count", "7", "--seed", "99", "--profile", "specific_gap",
            "--gap-subject", "MATH_G12",
            "--gap-topic", "MONOTONICITY_TOPIC",
            "--gap-problem-type", "PARAMETER_MONOTONICITY",
            "--gap-prerequisite-concept", "INEQUALITY_SOLVING",
        ]
    )
    assert args.count == 7 and args.seed == 99
    assert args.profile == SyntheticProfile.SPECIFIC_GAP
    assert not args.no_study_history
    assert args.gap_subject == "MATH_G12"
    assert args.gap_prerequisite_concept == "INEQUALITY_SOLVING"


def test_targeted_problem_type_gap_is_validated(
    db_session: Session,
    settings: Settings,
    synthetic_catalog: dict[str, object],
) -> None:
    summary = SyntheticStudentService(db_session, settings).generate(
        count=1,
        seed=90,
        profile=SyntheticProfile.SPECIFIC_GAP,
        gap_problem_type_code="oxyz_line_plane_intersection",
        anchor_time=ANCHOR,
    )
    assert summary.attempts_created == 48
    attempts = list(db_session.scalars(select(StudentAttempt)))
    assert attempts and sum(item.is_correct for item in attempts) / len(attempts) < 0.35


@pytest.mark.parametrize(
    "profile,options,expected_code",
    [
        (
            SyntheticProfile.AVERAGE,
            {"gap_subject_code": "SYNTH_MATH12"},
            "SYNTHETIC_GAP_PROFILE_REQUIRED",
        ),
        (
            SyntheticProfile.SPECIFIC_GAP,
            {"gap_topic_code": "MISSING_TOPIC"},
            "SYNTHETIC_GAP_TARGET_NOT_FOUND",
        ),
        (
            SyntheticProfile.SPECIFIC_GAP,
            {
                "gap_concept_code": "OXYZ",
                "gap_prerequisite_concept_code": "FUNCTION",
            },
            "CONFLICTING_SYNTHETIC_CONCEPT_GAPS",
        ),
    ],
)
def test_targeted_gap_validation_happens_before_writes(
    db_session: Session,
    settings: Settings,
    synthetic_catalog: dict[str, object],
    profile: SyntheticProfile,
    options: dict[str, str],
    expected_code: str,
) -> None:
    with pytest.raises(SyntheticGenerationError) as error:
        SyntheticStudentService(db_session, settings).generate(
            count=1, seed=90, profile=profile, anchor_time=ANCHOR, **options
        )
    assert error.value.code == expected_code
    assert db_session.scalar(select(func.count()).select_from(StudentAttempt)) == 0


def test_specific_gap_combines_hierarchy_and_prerequisite_filters(
    db_session: Session,
    settings: Settings,
    synthetic_catalog: dict[str, object],
) -> None:
    CurriculumImportService(db_session).import_dataset("MATH_G12_GDPT2018_CORE")
    service = SyntheticStudentService(db_session, settings)
    service.ATTEMPTS_PER_STUDENT = 400
    service.generate(
        count=1,
        seed=91,
        profile=SyntheticProfile.SPECIFIC_GAP,
        gap_subject_code="math_g12",
        gap_topic_code="monotonicity_topic",
        gap_problem_type_code="parameter_monotonicity",
        gap_prerequisite_concept_code="inequality_solving",
        anchor_time=ANCHOR,
    )
    rows = list(db_session.execute(
        select(StudentAttempt.is_correct, ProblemType.code, Concept.code)
        .join(ProblemType, ProblemType.id == StudentAttempt.problem_type_id)
        .join(Concept, Concept.id == StudentAttempt.concept_id)
    ))
    targeted = [
        row for row in rows
        if row[1] == "PARAMETER_MONOTONICITY"
        and row[2] in {"INEQUALITY_SOLVING", "PARAMETER_REASONING"}
    ]
    other = [row for row in rows if row not in targeted]
    assert {row[2] for row in targeted} == {
        "INEQUALITY_SOLVING", "PARAMETER_REASONING"
    }
    assert sum(row[0] for row in targeted) / len(targeted) < 0.35
    assert sum(row[0] for row in other) / len(other) > 0.65


def test_specific_gap_can_target_an_entire_subject(
    db_session: Session,
    settings: Settings,
    synthetic_catalog: dict[str, object],
) -> None:
    CurriculumImportService(db_session).import_dataset("MATH_G12_GDPT2018_CORE")
    service = SyntheticStudentService(db_session, settings)
    service.ATTEMPTS_PER_STUDENT = 400
    service.generate(
        count=1,
        seed=92,
        profile=SyntheticProfile.SPECIFIC_GAP,
        gap_subject_code="MATH_G12",
        anchor_time=ANCHOR,
    )
    rows = list(db_session.execute(
        select(StudentAttempt.is_correct, Subject.code)
        .join(ProblemType, ProblemType.id == StudentAttempt.problem_type_id)
        .join(Topic, Topic.id == ProblemType.topic_id)
        .join(Chapter, Chapter.id == Topic.chapter_id)
        .join(Subject, Subject.id == Chapter.subject_id)
    ))
    targeted = [row for row in rows if row[1] == "MATH_G12"]
    other = [row for row in rows if row[1] != "MATH_G12"]
    assert targeted and other
    assert sum(row[0] for row in targeted) / len(targeted) < 0.30
    assert sum(row[0] for row in other) / len(other) > 0.60


def test_cli_runs_generator_and_prints_summary(
    db_engine,
    settings: Settings,
    synthetic_catalog: dict[str, object],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    factory = sessionmaker(db_engine, expire_on_commit=False, autoflush=False)
    monkeypatch.setattr("app.generate_synthetic_students.get_settings", lambda: settings)
    monkeypatch.setattr("app.generate_synthetic_students.get_session_factory", lambda: factory)
    monkeypatch.setattr("app.generate_synthetic_students.dispose_engine", lambda: None)
    assert main(["--count", "2", "--seed", "11", "--profile", "WEAK"]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["students_created"] == 2
    assert output["attempts_created"] == 96
    assert output["profiles"] == {"WEAK": 2}
