from uuid import uuid4

import pytest
from pydantic import SecretStr, ValidationError
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.security import verify_password
from app.classes.models import Classroom, EnrollmentStatus, StudentEnrollment, TeacherClassroom
from app.concepts.graph_service import ConceptGraphService
from app.concepts.models import Concept, ConceptRelation
from app.core.config import Settings
from app.parents.models import ParentProfile, ParentStudentRelationship
from app.practice.models import (
    EvaluationStatus,
    PracticeSession,
    PracticeSessionStatus,
    PracticeSessionType,
    QuestionAttempt,
)
from app.questions.models import Question, QuestionStatus, QuestionType
from app.seed_service import RESET_CONFIRMATION, SeedOperationError, SeedService
from app.students.models import StudentProfile
from app.subjects.models import Subject
from app.teachers.models import TeacherProfile
from app.users.models import Role, User
from data.fixtures import CLASSROOMS, PARENT_LINKS
from data.seed.demo_users import USERS
from data.seed.grade12_math import CONCEPTS, PREREQUISITES, SUBJECT
from data.seed.identifiers import stable_id
from data.synthetic import generate_students


def count(session: Session, model: type) -> int:
    return session.scalar(select(func.count()).select_from(model)) or 0


def test_seed_creates_complete_stable_dataset_and_is_idempotent(
    db_session: Session, seed_settings: Settings
) -> None:
    first = SeedService(db_session, seed_settings).seed().to_dict()
    assert first["subjects"]["created"] == 1
    assert first["concepts"]["created"] == 14
    assert first["concept_relations"]["created"] == 12
    assert first["problem_types"]["created"] == 9
    assert first["users"]["created"] == 19
    assert first["teacher_profiles"]["created"] == 2
    assert first["student_profiles"]["created"] == 12
    assert first["parent_profiles"]["created"] == 4
    assert first["classrooms"]["created"] == 2
    assert first["teacher_classrooms"]["created"] == 2
    assert first["student_enrollments"]["created"] == 12
    assert first["parent_student_relationships"]["created"] == 12
    expected_counts = {
        Subject: 1,
        Concept: 14,
        ConceptRelation: 12,
        User: 19,
        TeacherProfile: 2,
        StudentProfile: 12,
        ParentProfile: 4,
        Classroom: 2,
        TeacherClassroom: 2,
        StudentEnrollment: 12,
        ParentStudentRelationship: 12,
    }
    assert {model.__name__: count(db_session, model) for model in expected_counts} == {
        model.__name__: expected for model, expected in expected_counts.items()
    }
    admin_id = stable_id("user", "ADMIN_01")
    admin = db_session.get(User, admin_id)
    assert admin is not None and admin.email == "admin.demo@edums.local" and admin.role == Role.ADMIN
    assert verify_password(seed_settings.seed_demo_password.get_secret_value(), admin.password_hash)
    password_hash = admin.password_hash
    all_ids_before = {
        "users": set(db_session.scalars(select(User.id))),
        "concepts": set(db_session.scalars(select(Concept.id))),
        "classes": set(db_session.scalars(select(Classroom.id))),
    }
    second = SeedService(db_session, seed_settings).seed().to_dict()
    assert all("created" not in states and "updated" not in states for states in second.values())
    assert second["users"]["unchanged"] == 19
    assert db_session.get(User, admin_id).password_hash == password_hash
    assert all_ids_before == {
        "users": set(db_session.scalars(select(User.id))),
        "concepts": set(db_session.scalars(select(Concept.id))),
        "classes": set(db_session.scalars(select(Classroom.id))),
    }


def test_grade_12_mathematics_catalog_and_prerequisites(
    db_session: Session, seed_settings: Settings
) -> None:
    SeedService(db_session, seed_settings).seed()
    subject = db_session.get(Subject, stable_id("subject", SUBJECT.code))
    assert subject is not None and subject.code == "MATH_G12" and subject.grade_level == 12
    stored = list(db_session.scalars(select(Concept).order_by(Concept.order_index)))
    assert [concept.name for concept in stored] == [
        "Function", "Derivative", "Monotonicity", "Extrema", "Function Analysis",
        "Exponential Function", "Logarithm", "Integral", "Probability", "Vector",
        "3D Geometry", "Oxyz", "Inequality Solving", "Parameter Reasoning",
    ]
    by_code = {concept.code: concept for concept in stored}
    graph = ConceptGraphService(db_session)
    assert [concept.code for concept in graph.get_direct_prerequisites(by_code["OXYZ"].id)] == [
        "VECTOR", "GEOMETRY_3D"
    ]
    tree = graph.get_prerequisite_tree(by_code["FUNCTION_ANALYSIS"].id)
    assert [concept.code for concept in tree.concepts] == [
        "FUNCTION", "DERIVATIVE", "MONOTONICITY", "EXTREMA", "FUNCTION_ANALYSIS"
    ]
    assert len(tree.relations) == 4
    assert [
        concept.code
        for concept in graph.get_direct_prerequisites(by_code["PARAMETER_REASONING"].id)
    ] == ["INEQUALITY_SOLVING"]


def test_demo_fixtures_have_expected_roles_relationships_and_statuses(
    db_session: Session, seed_settings: Settings
) -> None:
    SeedService(db_session, seed_settings).seed()
    role_counts = dict(db_session.execute(select(User.role, func.count()).group_by(User.role)).all())
    assert role_counts == {Role.ADMIN: 1, Role.TEACHER: 2, Role.STUDENT: 12, Role.PARENT: 4}
    status_counts = dict(
        db_session.execute(select(StudentEnrollment.status, func.count()).group_by(StudentEnrollment.status)).all()
    )
    assert status_counts == {
        EnrollmentStatus.ACTIVE: 10,
        EnrollmentStatus.INACTIVE: 1,
        EnrollmentStatus.COMPLETED: 1,
    }
    assert len(CLASSROOMS) == 2 and len(PARENT_LINKS) == 12
    for fixture in CLASSROOMS:
        classroom = db_session.get(Classroom, stable_id("classroom", fixture.code))
        assert classroom is not None and classroom.name == fixture.name


def test_seed_reconciles_owned_mutable_fields_without_changing_identity(
    db_session: Session, seed_settings: Settings
) -> None:
    SeedService(db_session, seed_settings).seed()
    concept_id = stable_id("concept", f"{SUBJECT.code}:DERIVATIVE")
    classroom_id = stable_id("classroom", CLASSROOMS[0].code)
    concept = db_session.get(Concept, concept_id)
    classroom = db_session.get(Classroom, classroom_id)
    assert concept is not None and classroom is not None
    concept.name = "Changed"
    classroom.name = "Changed"
    enrollment = db_session.scalar(select(StudentEnrollment).where(StudentEnrollment.classroom_id == classroom_id))
    assert enrollment is not None
    enrollment.status = EnrollmentStatus.COMPLETED
    db_session.commit()
    summary = SeedService(db_session, seed_settings).seed().to_dict()
    assert summary["concepts"]["updated"] == 1
    assert summary["classrooms"]["updated"] == 1
    assert summary["student_enrollments"]["updated"] >= 1
    assert db_session.get(Concept, concept_id).name == "Derivative"
    assert db_session.get(Classroom, classroom_id).name == CLASSROOMS[0].name


def test_reset_requires_confirmation_and_is_forbidden_in_production(
    db_session: Session, seed_settings: Settings
) -> None:
    SeedService(db_session, seed_settings).seed()
    with pytest.raises(SeedOperationError) as missing:
        SeedService(db_session, seed_settings).reset("")
    assert missing.value.code == "SEED_RESET_CONFIRMATION_REQUIRED"
    production = seed_settings.model_copy(update={"app_env": "production"})
    with pytest.raises(SeedOperationError) as forbidden:
        SeedService(db_session, production).reset(RESET_CONFIRMATION)
    assert forbidden.value.code == "SEED_RESET_FORBIDDEN"
    with pytest.raises(SeedOperationError) as seed_forbidden:
        SeedService(db_session, production).seed()
    assert seed_forbidden.value.code == "DEMO_SEED_FORBIDDEN"
    assert count(db_session, User) == 19


def test_reset_recreates_same_ids_and_preserves_unrelated_records(
    db_session: Session, seed_settings: Settings
) -> None:
    SeedService(db_session, seed_settings).seed()
    unrelated_id = uuid4()
    db_session.add(User(
        id=unrelated_id,
        email="unrelated@example.com",
        password_hash="synthetic-not-used",
        full_name="Unrelated User",
        role=Role.ADMIN,
        is_active=True,
    ))
    db_session.commit()
    ids_before = set(db_session.scalars(select(User.id).where(User.id != unrelated_id)))
    summary = SeedService(db_session, seed_settings).reset(RESET_CONFIRMATION).to_dict()
    assert summary["users"] == {"created": 19, "deleted": 19}
    assert db_session.get(User, unrelated_id) is not None
    assert set(db_session.scalars(select(User.id).where(User.id != unrelated_id))) == ids_before
    assert count(db_session, User) == 20


def test_reset_removes_practice_data_owned_by_demo_students(
    db_session: Session, seed_settings: Settings
) -> None:
    SeedService(db_session, seed_settings).seed()
    student_id = stable_id("profile", "STUDENT_01")
    subject = db_session.get(Subject, stable_id("subject", SUBJECT.code))
    assert subject is not None
    unrelated_author = User(
        id=uuid4(),
        email="seed-reset-question-author@example.com",
        password_hash="synthetic-not-used",
        full_name="Unrelated Question Author",
        role=Role.ADMIN,
        is_active=True,
    )
    db_session.add(unrelated_author)
    db_session.flush()
    question = Question(
        subject_id=subject.id,
        content="Seed reset practice reference",
        question_type=QuestionType.TRUE_FALSE,
        difficulty=0.2,
        correct_answer="TRUE",
        explanation="Test-only question.",
        source_type="TEST",
        source_reference="seed-reset-test",
        exam_weight=0.1,
        status=QuestionStatus.APPROVED,
        created_by=unrelated_author.id,
    )
    practice_session = PracticeSession(
        student_id=student_id,
        subject_id=subject.id,
        session_type=PracticeSessionType.PRACTICE,
        status=PracticeSessionStatus.ACTIVE,
    )
    db_session.add_all([question, practice_session])
    db_session.flush()
    attempt = QuestionAttempt(
        practice_session_id=practice_session.id,
        student_id=student_id,
        question_id=question.id,
        student_answer="TRUE",
        is_correct=True,
        score=1.0,
        response_time_seconds=10.0,
        hint_count=0,
        attempt_number=1,
        evaluation_status=EvaluationStatus.AUTO_EVALUATED,
    )
    db_session.add(attempt)
    db_session.commit()

    SeedService(db_session, seed_settings).reset(RESET_CONFIRMATION)

    assert db_session.scalar(
        select(func.count())
        .select_from(QuestionAttempt)
        .where(QuestionAttempt.id == attempt.id)
    ) == 0
    assert db_session.scalar(
        select(func.count())
        .select_from(PracticeSession)
        .where(PracticeSession.id == practice_session.id)
    ) == 0
    assert db_session.get(Question, question.id) is not None
    assert db_session.get(StudentProfile, student_id) is not None


def test_reset_rolls_back_if_nonseed_data_references_demo_user(
    db_session: Session, seed_settings: Settings
) -> None:
    SeedService(db_session, seed_settings).seed()
    teacher = db_session.get(User, stable_id("user", "TEACHER_MATH_01"))
    assert teacher is not None
    manual = Classroom(
        id=uuid4(), name="Manual class", academic_year="2026-2027", grade_level=12, created_by=teacher.id
    )
    db_session.add(manual)
    db_session.commit()
    with pytest.raises(IntegrityError):
        SeedService(db_session, seed_settings).reset(RESET_CONFIRMATION)
    db_session.rollback()
    assert db_session.get(Classroom, manual.id) is not None
    assert count(db_session, User) == 19 and count(db_session, Concept) == 14


def test_identity_collision_rolls_back_entire_seed(
    db_session: Session, seed_settings: Settings
) -> None:
    db_session.add(User(
        id=uuid4(), email="admin.demo@edums.local", password_hash="synthetic-not-used",
        full_name="Collision", role=Role.ADMIN, is_active=True,
    ))
    db_session.commit()
    with pytest.raises(SeedOperationError) as error:
        SeedService(db_session, seed_settings).seed()
    assert error.value.code == "SEED_IDENTITY_CONFLICT"
    assert count(db_session, Subject) == 0 and count(db_session, Concept) == 0
    assert count(db_session, User) == 1


def test_seed_password_is_required_and_validated(db_session: Session, settings: Settings) -> None:
    with pytest.raises(SeedOperationError) as error:
        SeedService(db_session, settings).seed()
    assert error.value.code == "SEED_PASSWORD_REQUIRED"
    assert count(db_session, Subject) == 0
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            database_name="test",
            database_user="test",
            seed_demo_password="too-short",
        )


def test_synthetic_students_are_deterministic_and_fixture_references_are_valid() -> None:
    first = generate_students(12)
    second = generate_students(12)
    assert first == second
    assert len({record.code for record in first}) == len({record.email for record in first}) == 12
    assert all(record.role == Role.STUDENT for record in first)
    user_codes = {record.code for record in USERS}
    assert all(fixture.teacher_code in user_codes for fixture in CLASSROOMS)
    assert all(student_code in user_codes for fixture in CLASSROOMS for student_code, status in fixture.enrollments)
    assert all(link.parent_code in user_codes and link.student_code in user_codes for link in PARENT_LINKS)
    with pytest.raises(ValueError):
        generate_students(0)


def test_stable_ids_are_deterministic_and_namespaced() -> None:
    assert stable_id("user", "ADMIN_01") == stable_id("user", " admin_01 ")
    assert stable_id("user", "ADMIN_01") != stable_id("profile", "ADMIN_01")
    assert stable_id("concept", "MATH_G12:FUNCTION") != stable_id("concept", "MATH_G12:DERIVATIVE")
    assert len({stable_id("user", record.code) for record in USERS}) == 19
    assert len(PREREQUISITES) == 11
    assert len(CONCEPTS) == 14
