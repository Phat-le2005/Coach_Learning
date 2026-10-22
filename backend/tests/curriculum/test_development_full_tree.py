from __future__ import annotations

import json
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.exceptions import ApplicationError
from app.curriculum.development_tree import (
    DEVELOPMENT_TREE_DATASET,
    DEVELOPMENT_TREE_EXPECTED_COUNTS,
    DEVELOPMENT_TREE_ROOT,
    DevelopmentTreeActivationService,
)
from app.curriculum.import_service import CurriculumImportService
from app.curriculum.models import Chapter, ProblemType, Topic
from app.mastery.service import MasteryQueryService
from app.students.models import StudentProfile
from app.users.models import Role, User


def test_development_tree_dataset_has_the_complete_six_chapter_hierarchy(
    db_session: Session,
) -> None:
    service = DevelopmentTreeActivationService(db_session)
    preview = service.preview()

    assert preview.dataset_code == DEVELOPMENT_TREE_DATASET
    for name, expected in DEVELOPMENT_TREE_EXPECTED_COUNTS.items():
        assert preview.counts[name] == expected

    chapters = json.loads((DEVELOPMENT_TREE_ROOT / "chapters.json").read_text("utf-8"))
    assert [chapter["code"] for chapter in chapters] == [
        "DERIVATIVE_APPLICATIONS",
        "VECTORS_GEOMETRY",
        "GROUPED_DATA_DISPERSION",
        "INTEGRALS",
        "OXYZ_CHAPTER",
        "PROBABILITY_CHAPTER",
    ]


def test_development_tree_activation_is_non_destructive_and_idempotent(
    db_session: Session,
) -> None:
    CurriculumImportService(db_session).import_dataset("MATH_G12_GDPT2018_CORE")
    service = DevelopmentTreeActivationService(db_session)

    first = service.activate(app_env="test")
    second = service.activate(app_env="test")

    assert first.active_chapters == second.active_chapters == 6
    assert first.active_topics == second.active_topics == 25
    assert first.active_problem_types == second.active_problem_types == 75
    assert first.concepts == second.concepts == 89
    assert first.learning_outcomes == second.learning_outcomes == 34
    assert "EXP_LOG_EQUATION" in first.deactivated_legacy_problem_types
    assert first.removed_stale_mappings > 0
    assert second.removed_stale_mappings == 0

    exp_log = db_session.scalar(
        select(ProblemType).where(ProblemType.code == "EXP_LOG_EQUATION")
    )
    assert exp_log is not None
    assert exp_log.is_active is False


def test_student_mastery_tree_hides_inactive_legacy_branches(
    db_session: Session,
) -> None:
    CurriculumImportService(db_session).import_dataset("MATH_G12_GDPT2018_CORE")
    DevelopmentTreeActivationService(db_session).activate(app_env="test")
    user = User(
        email="tree.student@example.com",
        password_hash="not-used-by-this-test",
        full_name="Tree Student",
        role=Role.STUDENT,
    )
    db_session.add(user)
    db_session.flush()
    student = StudentProfile(user_id=user.id, grade_level=12)
    db_session.add(student)
    db_session.commit()

    result = MasteryQueryService(db_session).overview_for_student_id(student.id)
    subject = next(item for item in result.subjects if item.code == "MATH_G12")

    assert [chapter.code for chapter in subject.chapters] == [
        "DERIVATIVE_APPLICATIONS",
        "VECTORS_GEOMETRY",
        "GROUPED_DATA_DISPERSION",
        "INTEGRALS",
        "OXYZ_CHAPTER",
        "PROBABILITY_CHAPTER",
    ]
    assert sum(len(chapter.topics) for chapter in subject.chapters) == 25
    assert sum(
        len(topic.problem_types)
        for chapter in subject.chapters
        for topic in chapter.topics
    ) == 75
    assert len(subject.concepts) == 89
    assert all(
        problem.state.value == "NOT_STARTED"
        for chapter in subject.chapters
        for topic in chapter.topics
        for problem in topic.problem_types
    )


def test_development_tree_activation_is_forbidden_in_production(
    db_session: Session,
) -> None:
    with pytest.raises(ApplicationError) as error:
        DevelopmentTreeActivationService(db_session).activate(app_env="production")

    assert error.value.code == "DEVELOPMENT_TREE_PRODUCTION_FORBIDDEN"
    assert db_session.scalar(select(func.count()).select_from(Chapter)) == 0
    assert db_session.scalar(select(func.count()).select_from(Topic)) == 0
