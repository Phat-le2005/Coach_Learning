from __future__ import annotations

import json
from pathlib import Path
from uuid import UUID

import pytest
from sqlalchemy.orm import Session

from app.questions.data_reconciliation import (
    DATA_ROOT, ReconciliationPlan, _review_exclusions, apply_plan, build_plan,
)
from app.questions.models import Question, QuestionStatus, QuestionType
from app.questions.service import QuestionService
from app.core.exceptions import ApplicationError
from app.core.config import get_settings
from app.subjects.models import Subject
from app.users.models import Role


def test_source_review_exclusions_follow_curated_files() -> None:
    standalone, groups = _review_exclusions(DATA_ROOT)
    assert "M12_VECTOR_CAND_0019" in standalone  # scope override
    assert "M12_VECTOR_CAND_0046" in standalone  # boundary hold
    assert "M12_DISP_CAND_0014" in standalone  # duplicate rejection
    assert "M12_DISP_CAND_0032" in groups  # mixed-scope group
    assert "EVID_VECTOR_GROUP_0006" in groups
    assert "M12_VECTOR_CAND_0001" not in standalone


def test_quarantine_preserves_content_and_is_idempotent(
    db_session: Session, question_user_factory, tmp_path: Path,
) -> None:
    author = question_user_factory(Role.TEACHER, "reconciliation@example.com")
    subject = Subject(code="RECON-MATH12", name="Math", grade_level=12)
    db_session.add(subject)
    db_session.flush()
    question = Question(
        subject_id=subject.id,
        content="Original reviewed source text",
        question_type=QuestionType.MULTIPLE_CHOICE,
        difficulty=0.5,
        correct_answer="A",
        source_type="VECTOR",
        source_reference="M12_VECTOR_CAND_0019",
        exam_weight=0.5,
        status=QuestionStatus.APPROVED,
        created_by=author.id,
    )
    db_session.add(question)
    db_session.commit()
    original_content, original_hash = question.content, question.content_hash

    plan = build_plan(db_session)
    assert len(plan.questions) == 1
    assert "SOURCE_REVIEW_NOT_VERIFIED" in plan.questions[0].reasons
    backup_path = tmp_path / "backup.json"
    apply_plan(db_session, plan, backup_path=backup_path)

    db_session.refresh(question)
    assert question.status == QuestionStatus.REVIEW
    assert (question.content, question.content_hash) == (original_content, original_hash)
    assert build_plan(db_session).summary()["questions"] == 0
    backup = json.loads(backup_path.read_text(encoding="utf-8"))
    assert backup["questions"][0]["old_status"] == "APPROVED"
    with pytest.raises(ValueError, match="already exists"):
        apply_plan(db_session, plan, backup_path=backup_path)


def test_broken_pdf_text_requires_review_even_with_answer(
    db_session: Session, question_user_factory,
) -> None:
    author = question_user_factory(Role.TEACHER, "reconciliation-pdf@example.com")
    subject = Subject(code="RECON-PDF", name="Math", grade_level=12)
    db_session.add(subject)
    db_session.flush()
    question = Question(
        subject_id=subject.id, content="f(x) = \ue000", question_type=QuestionType.SHORT_ANSWER,
        difficulty=0.5, correct_answer="1", source_type="TEST", exam_weight=0.5,
        status=QuestionStatus.APPROVED, created_by=author.id,
    )
    db_session.add(question)
    db_session.commit()
    plan = build_plan(db_session)
    assert len(plan.questions) == 1
    assert "PDF_TEXT_NEEDS_SOURCE_REVIEW" in plan.questions[0].reasons


def test_approval_rejects_unverified_source_and_broken_pdf_text(
    db_session: Session, question_user_factory,
) -> None:
    author = question_user_factory(Role.TEACHER, "reconciliation-approval@example.com")
    subject = Subject(code="RECON-APPROVAL", name="Math", grade_level=12)
    db_session.add(subject)
    db_session.flush()
    question = Question(subject_id=subject.id, content="Text", question_type=QuestionType.SHORT_ANSWER,
                        difficulty=0.5, correct_answer="1", source_type="VECTOR",
                        source_reference="M12_VECTOR_CAND_0019", exam_weight=0.5,
                        status=QuestionStatus.REVIEW, created_by=author.id)
    with pytest.raises(ApplicationError, match="Source review"):
        QuestionService(db_session)._validate_ready(question)
    question.source_reference = "external-worksheet"
    question.content = "f(x)=\ue000"
    with pytest.raises(ApplicationError, match="presentation review"):
        QuestionService(db_session)._validate_ready(question)


def test_handwriting_sandbox_remains_available_without_academic_mappings(
    db_session: Session, question_user_factory,
) -> None:
    author = question_user_factory(Role.TEACHER, "reconciliation-sandbox@example.com")
    subject = Subject(code="RECON-SANDBOX", name="Math", grade_level=12)
    db_session.add(subject)
    db_session.flush()
    question = Question(subject_id=subject.id, content="Write a solution", question_type=QuestionType.OPEN_RESPONSE,
                        difficulty=0.5, correct_answer=None, source_type="SAMPLE_TEST",
                        exam_weight=0.5, status=QuestionStatus.APPROVED, created_by=author.id)
    db_session.add(question)
    db_session.commit()
    assert build_plan(db_session).questions == ()


def test_reconciliation_cannot_mutate_production(
    db_session: Session, monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    get_settings.cache_clear()
    try:
        with pytest.raises(ValueError, match="development/test only"):
            apply_plan(db_session, ReconciliationPlan((), ()), backup_path=tmp_path / "no.json")
        assert not (tmp_path / "no.json").exists()
    finally:
        get_settings.cache_clear()


def test_stale_audit_rolls_back_all_status_updates(
    db_session: Session, question_user_factory, tmp_path: Path,
) -> None:
    author = question_user_factory(Role.TEACHER, "reconciliation-race@example.com")
    subject = Subject(code="RECON-RACE", name="Math", grade_level=12)
    db_session.add(subject)
    db_session.flush()
    for reference in ("M12_VECTOR_CAND_0019", "M12_DISP_CAND_0014"):
        db_session.add(Question(
            subject_id=subject.id, content=reference, question_type=QuestionType.SHORT_ANSWER,
            difficulty=0.5, correct_answer="1", source_type="TEST",
            source_reference=reference, exam_weight=0.5,
            status=QuestionStatus.APPROVED, created_by=author.id,
        ))
    db_session.commit()
    plan = build_plan(db_session)
    assert len(plan.questions) == 2
    stale = db_session.get(Question, UUID(plan.questions[-1].id))
    assert stale is not None
    stale.content = "Changed after audit"
    db_session.commit()
    with pytest.raises(RuntimeError, match="changed since audit"):
        apply_plan(db_session, plan, backup_path=tmp_path / "before-rollback.json")
    assert all(db_session.get(Question, UUID(row.id)).status == QuestionStatus.APPROVED
               for row in plan.questions)
