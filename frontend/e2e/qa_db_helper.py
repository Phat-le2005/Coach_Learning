"""Isolated PostgreSQL QA fixture provisioner and authoritative database oracle.

Establishes an isolated QA student, isolated practice session, and isolated SolutionAttempt
records in PostgreSQL without modifying shared demo users or production records.
Never prints passwords or tokens to stdout.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from uuid import UUID, uuid4

# Ensure backend directory is in sys.path
BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "backend"))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from sqlalchemy import select
from app.database.session import dispose_engine, get_session_factory
from app.users.models import Role, User
from app.users.schemas import UserCreate
from app.users.service import UserService
from app.students.models import StudentProfile
from app.subjects.models import Subject
from app.questions.models import Question, QuestionStatus, QuestionType
from app.questions.fingerprint import question_content_hash
from app.practice.models import PracticeSession, PracticeSessionStatus, PracticeSessionType
from app.math_solutions.models import (
    SolutionAttempt,
    SolutionOperation,
    SolutionStep,
    StepRevision,
)
from app.math_solutions.service import MathSolutionService
from app.math_solutions.schemas import SolutionStepDraft
from app.math_ink.models import MathInkDocument, MathInkPage

QA_STUDENT_EMAIL = "qa.ocr.e2e.isolated@edums.edu.vn"
QA_STUDENT_NAME = "QA Isolated E2E Student"
QA_DEFAULT_PASSWORD = os.environ.get("QA_E2E_PASSWORD", "QaOcrE2e!2026#Isolated")


def ensure_qa_student_and_question(session) -> tuple[User, StudentProfile, Subject, Question]:
    user_svc = UserService(session)
    user = user_svc.find_by_email(QA_STUDENT_EMAIL)
    if user is None:
        user = user_svc.create_user(
            UserCreate(
                email=QA_STUDENT_EMAIL,
                full_name=QA_STUDENT_NAME,
                role=Role.STUDENT,
                password=QA_DEFAULT_PASSWORD,
            )
        )
    student = session.scalar(select(StudentProfile).where(StudentProfile.user_id == user.id))
    assert student is not None, "StudentProfile missing for QA user"

    subject = session.scalar(select(Subject).where(Subject.code == "MATH_G12"))
    if subject is None:
        subject = session.scalar(select(Subject))
    assert subject is not None, "No Subject found in database"

    # Find or create an isolated QA approved question
    qa_q_content = "[QA-ISOLATED-OCR-E2E] Khảo sát sự biến thiên và vẽ đồ thị của hàm số $y = x^3 - 3x^2 + 2$."
    question = session.scalar(
        select(Question).where(
            Question.subject_id == subject.id,
            Question.content == qa_q_content,
        )
    )
    if question is None:
        question = Question(
            subject_id=subject.id,
            question_type=QuestionType.OPEN_RESPONSE,
            difficulty=0.5,
            source_type="QA_ISOLATED_FIXTURE",
            exam_weight=0.5,
            status=QuestionStatus.APPROVED,
            content=qa_q_content,
            content_hash=question_content_hash(qa_q_content),
            explanation="TXĐ: D = R. y' = 3x^2 - 6x. Cho y' = 0 <=> x = 0 hoặc x = 2.",
            created_by=user.id,
        )
        session.add(question)
        session.commit()
        session.refresh(question)
    elif question.status != QuestionStatus.APPROVED:
        question.status = QuestionStatus.APPROVED
        session.commit()

    return user, student, subject, question


def create_isolated_attempt(session, label: str = "") -> dict:
    user, student, subject, question = ensure_qa_student_and_question(session)
    practice = PracticeSession(
        student_id=student.id,
        subject_id=subject.id,
        session_type=PracticeSessionType.PRACTICE,
        status=PracticeSessionStatus.ACTIVE,
    )
    session.add(practice)
    session.flush()

    idem_key = f"qa-e2e:{label}:{uuid4()}"[:95]
    svc = MathSolutionService(session)
    snapshot = svc.create(
        user.id,
        source_kind="CANONICAL",
        context_type="SELF_PRACTICE",
        mode="INDEPENDENT_SOLUTION",
        create_idempotency_key=idem_key,
        question_id=question.id,
        practice_session_id=practice.id,
    )
    return {
        "attempt_id": snapshot["id"],
        "question_id": str(question.id),
        "practice_session_id": str(practice.id),
        "student_email": QA_STUDENT_EMAIL,
        "initial_revision": snapshot["attempt_revision_number"],
        "status": snapshot["status"],
    }


def inspect_attempt(session, attempt_id: UUID) -> dict:
    attempt = session.get(SolutionAttempt, attempt_id)
    if attempt is None:
        return {"exists": False, "attempt_id": str(attempt_id)}

    steps_rows = list(
        session.scalars(
            select(SolutionStep)
            .where(SolutionStep.attempt_id == attempt.id)
            .order_by(SolutionStep.step_index, SolutionStep.created_at)
        ).all()
    )
    active_steps = []
    all_steps = []
    for s in steps_rows:
        latest_rev = session.scalar(
            select(StepRevision)
            .where(StepRevision.step_id == s.id)
            .order_by(StepRevision.step_revision_number.desc())
            .limit(1)
        )
        item = {
            "id": str(s.id),
            "step_index": s.step_index,
            "step_type": s.step_type,
            "status": s.status,
            "is_deleted": s.is_deleted,
            "content_latex": s.content_latex,
            "explanation_text": s.explanation_text,
            "step_revision_number": latest_rev.step_revision_number if latest_rev else 0,
        }
        all_steps.append(item)
        if not s.is_deleted:
            active_steps.append(item)

    ops_rows = list(
        session.scalars(
            select(SolutionOperation)
            .where(SolutionOperation.attempt_id == attempt.id)
            .order_by(SolutionOperation.result_attempt_revision, SolutionOperation.created_at)
        ).all()
    )
    operations = [
        {
            "id": str(op.id),
            "client_action_id": str(op.client_action_id),
            "operation_type": op.operation_type,
            "request_hash": op.request_hash,
            "result_attempt_revision": op.result_attempt_revision,
        }
        for op in ops_rows
    ]

    ink_doc = session.scalar(
        select(MathInkDocument).where(MathInkDocument.attempt_id == attempt.id)
    )
    ink_info = None
    if ink_doc is not None:
        ink_pages = list(
            session.scalars(
                select(MathInkPage)
                .where(MathInkPage.document_id == ink_doc.id)
                .order_by(MathInkPage.page_index)
            ).all()
        )
        ink_info = {
            "id": str(ink_doc.id),
            "revision": ink_doc.revision,
            "pages": [
                {
                    "page_index": p.page_index,
                    "stroke_count": p.stroke_count,
                    "point_count": p.point_count,
                    "sha256": p.sha256,
                }
                for p in ink_pages
            ],
        }

    return {
        "exists": True,
        "attempt": {
            "id": str(attempt.id),
            "status": attempt.status,
            "attempt_revision_number": attempt.attempt_revision_number,
            "question_id": str(attempt.question_id) if attempt.question_id else None,
            "practice_session_id": str(attempt.practice_session_id) if attempt.practice_session_id else None,
        },
        "active_step_count": len(active_steps),
        "active_steps": active_steps,
        "all_steps": all_steps,
        "operation_count": len(operations),
        "operations": operations,
        "ink_document": ink_info,
    }


def bump_revision(session, attempt_id: UUID, latex: str = "x \\in \\mathbb{R}") -> dict:
    user, _, _, _ = ensure_qa_student_and_question(session)
    attempt = session.get(SolutionAttempt, attempt_id)
    if attempt is None:
        raise ValueError(f"Attempt {attempt_id} not found")
    svc = MathSolutionService(session)
    updated = svc.add_step(
        user.id,
        attempt_id,
        expected_attempt_revision=attempt.attempt_revision_number,
        client_action_id=uuid4(),
        draft=SolutionStepDraft(
            step_type="ASSUMPTION",
            content_latex=latex,
            explanation_text="External concurrent step",
            artifact=None,
        ),
    )
    return {
        "attempt_id": str(attempt_id),
        "new_revision": updated["attempt_revision_number"],
        "step_count": len(updated["steps"]),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="QA E2E Database Helper")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_create = sub.add_parser("create-attempt")
    p_create.add_argument("--label", default="test")

    p_inspect = sub.add_parser("inspect-attempt")
    p_inspect.add_argument("--attempt-id", required=True)

    p_bump = sub.add_parser("bump-revision")
    p_bump.add_argument("--attempt-id", required=True)
    p_bump.add_argument("--latex", default="D = \\mathbb{R}")

    args = parser.parse_args()
    try:
        with get_session_factory()() as session:
            if args.cmd == "create-attempt":
                out = create_isolated_attempt(session, args.label)
                print(json.dumps(out))
            elif args.cmd == "inspect-attempt":
                out = inspect_attempt(session, UUID(args.attempt_id))
                print(json.dumps(out))
            elif args.cmd == "bump-revision":
                out = bump_revision(session, UUID(args.attempt_id), args.latex)
                print(json.dumps(out))
        return 0
    finally:
        dispose_engine()


if __name__ == "__main__":
    raise SystemExit(main())
