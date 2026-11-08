"""Persist Gemini assessments against the actual migrated schema, without a model call."""

from datetime import datetime, timezone
from hashlib import sha256
import json
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.math_solutions import curated_ai_grading as grading
from app.math_solutions.ai_review_router import _final_review, _is_gemini_evaluation
from app.math_solutions.answer_grounded_ai import AIStepGrade, AICriterionGrade, AnswerGroundedReview, _load_confirmed_steps
from app.math_solutions.answer_reference import AnswerReference
from app.math_solutions.models import EvaluationDecision, SolutionAttempt, SolutionRubric, SolutionStep, StepEvaluation, StepRevision
from app.practice.models import PracticeSession, PracticeSessionType
from app.questions.models import Question, QuestionStatus, QuestionType
from app.students.models import StudentProfile
from app.subjects.models import Subject
from app.users.models import Role, User


@pytest.mark.parametrize("evidence_fails", [False, True])
def test_gemini_grade_persists_atomically_in_existing_evaluator_category(db_session, monkeypatch, evidence_fails):
    session = db_session
    user = User(email=f"gemini-persist-{uuid4()}@example.test", password_hash="unused-fixture-hash", full_name="Synthetic student", role=Role.STUDENT)
    subject = Subject(code="MATH-GEMINI-PERSIST", name="Synthetic math", grade_level=12)
    session.add_all([user, subject]); session.flush()
    student = StudentProfile(user_id=user.id, grade_level=12)
    question = Question(subject_id=subject.id, content="Find derivative y=x^3", question_type=QuestionType.OPEN_RESPONSE,
                        difficulty=.5, correct_answer="3x^2", explanation="Derivative: 3x^2", source_type="TEST", exam_weight=.5, status=QuestionStatus.APPROVED, created_by=user.id)
    session.add_all([student, question]); session.flush()
    criteria = [{"id":"derivative", "weight":1.0, "concept_codes":[]}]
    rubric = SolutionRubric(question_id=question.id, title="Synthetic approved rubric", status="APPROVED", criteria={"criteria":criteria})
    practice = PracticeSession(student_id=student.id, subject_id=subject.id, session_type=PracticeSessionType.PRACTICE)
    session.add_all([rubric, practice]); session.flush()
    attempt = SolutionAttempt(student_id=student.id, question_id=question.id, rubric_id=rubric.id, practice_session_id=practice.id,
                              source_kind="CANONICAL", context_type="SELF_PRACTICE", mode="INDEPENDENT_SOLUTION", status="SUBMITTED", submitted_at=datetime.now(timezone.utc))
    session.add(attempt); session.flush()
    step = SolutionStep(attempt_id=attempt.id, step_index=1, step_type="CUSTOM", content_latex="3x^2")
    session.add(step); session.flush()
    revision = StepRevision(step_id=step.id, step_revision_number=1, step_index_at_revision=1,
                            content_latex="3x^2", change_reason="STUDENT_EDIT")
    session.add(revision); session.commit()
    reference = AnswerReference("CANONICAL", question.id, question.content, question.correct_answer, question.explanation, "a"*64)
    work, _ = _load_confirmed_steps(session, attempt.id)
    review = AnswerGroundedReview(attempt.id, reference.content_sha256, (
        AIStepGrade(step_index=1, verdict="VALID", score=1.0, confidence=.95, student_quote="3x^2", answer_quote="3x^2", feedback="Đạo hàm khớp lời giải."),
    ), False, criterion_grades=(AICriterionGrade(criterion_id="derivative", score=1, confidence=.95, step_indices=[1], answer_quote="3x^2", feedback="Đúng công thức."),),
        submission_sha256=sha256(json.dumps(work,sort_keys=True,ensure_ascii=False).encode("utf-8")).hexdigest())
    monkeypatch.setattr(grading, "curated_context", lambda *_args, **_kwargs: SimpleNamespace(rubric=rubric))
    monkeypatch.setattr(grading, "resolve_answer_reference", lambda *_args: reference)
    emitted = []
    def emit(_self, decision_id, **metadata):
        if evidence_fails:
            raise RuntimeError("Synthetic evidence write failure")
        emitted.append((decision_id, metadata))
    monkeypatch.setattr("app.math_solutions.evidence_adapter.MathSolutionEvidenceAdapter.emit_evidence_for_decision", emit)
    if evidence_fails:
        with pytest.raises(RuntimeError, match="Synthetic evidence"):
            grading.finalize_curated_ai_review(session, attempt.id, review)
        session.expire_all()
        assert session.get(SolutionAttempt, attempt.id).status == "SUBMITTED"
        assert session.scalar(select(EvaluationDecision)) is None
        assert session.scalar(select(StepEvaluation)) is None
    else:
        decision = grading.finalize_curated_ai_review(session, attempt.id, review)
        stored = session.scalar(select(StepEvaluation).where(StepEvaluation.step_revision_id == revision.id))
        assert stored.evaluator_type == "AI_HEURISTIC"
        assert json.loads(stored.evidence_quote)["evaluator"] == "GEMINI_REFERENCE"
        response = _final_review(session, attempt.id, decision)
        assert response.is_final and response.review_source == "ANSWER_GROUNDED_AI"
        assert response.final_score == response.step_grades[0].score == 1
        assert len(emitted) == 1
        assert grading.finalize_curated_ai_review(session, attempt.id, review).id == decision.id
        assert len(session.scalars(select(StepEvaluation)).all()) == 1


@pytest.mark.parametrize("payload", [None, "not json", "[]", "{}", '{"evaluator":"OTHER"}'])
def test_other_ai_or_invalid_evidence_is_not_labelled_as_gemini(payload):
    assert not _is_gemini_evaluation(SimpleNamespace(evaluator_type="AI_HEURISTIC", evidence_quote=payload))
