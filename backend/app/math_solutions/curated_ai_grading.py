"""Publish reference-grounded Gemini grades for the reviewed PA2 question set."""
from datetime import datetime, timezone
import json
from hashlib import sha256
import math
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import ApplicationError
from app.math_solutions.answer_reference import resolve_answer_reference
from app.math_solutions.grading_context import resolve_grading_context
from app.math_solutions.grading_profile import OCR_SOURCE
from app.math_solutions.models import EvaluationDecision, SolutionAttempt, SolutionRubric, SolutionStep, StepEvaluation, StepRevision
from app.math_solutions.rubric_evaluator import RubricCriterionMatch
from app.questions.models import Question


def criterion_matches(criteria, reviews, step_indices, reference_text):
    """Validate all criterion/check citations and preserve per-concept scores."""
    from app.math_solutions.answer_grounded_ai import _is_valid_evidence_quote
    grades = {g.criterion_id: g for g in reviews}
    if len(grades) != len(reviews) or set(grades) != {c["id"] for c in criteria}:
        raise ApplicationError(422, "AI_CRITERION_COVERAGE_INVALID", "Every approved criterion must be assessed once.")
    matches = []
    for criterion in criteria:
        grade = grades[criterion["id"]]
        details = {"evaluator": "GEMINI_REFERENCE", "criterion_review": grade.model_dump(mode="json")}
        for assessment in [grade, *grade.checks]:
            if (not set(assessment.step_indices) <= set(step_indices)
                    or len(set(assessment.step_indices)) != len(assessment.step_indices)
                    or (assessment.score > 0 and not assessment.step_indices)
                    or not _is_valid_evidence_quote(assessment.answer_quote, reference_text)):
                raise ApplicationError(422, "AI_CRITERION_EVIDENCE_INVALID", "Criterion evidence must identify submitted work and the reference.")
        expected = {check["label"]: check for check in criterion.get("checks", [])}
        actual = {check.label: check for check in grade.checks}
        if len(actual) != len(grade.checks) or set(actual) != set(expected):
            raise ApplicationError(422, "AI_CHECK_COVERAGE_INVALID", "Every approved numeric check must be assessed once.")
        if expected:
            score = sum(check.score for check in actual.values()) / len(expected)
            if not math.isclose(score, grade.score, abs_tol=1e-5):
                raise ApplicationError(422, "AI_CRITERION_SCORE_INVALID", "Criterion score must equal the mean check score.")
            details["numeric_checks"] = [
                {"label": label, "score": actual[label].score,
                 "concept_codes": [check["concept_code"]] if check.get("concept_code") else criterion["concept_codes"]}
                for label, check in expected.items()
            ]
        else:
            score = grade.score
        matches.append(RubricCriterionMatch(
            criterion_id=criterion["id"], weight=criterion["weight"],
            score_achieved=round(criterion["weight"] * score, 6),
            matched_step_index=grade.step_indices[0] if grade.step_indices else -1, details=details,
        ))
    return matches


def curated_context(session: Session, attempt: SolutionAttempt, *, refresh: bool = False):
    source_kind = getattr(attempt, "source_kind", None)
    question_id = getattr(attempt, "question_id", None)
    rubric_id = getattr(attempt, "rubric_id", None)
    if source_kind != "CANONICAL" or not question_id or not rubric_id:
        return None
    question = session.get(Question, question_id)
    if refresh and question is not None:
        session.refresh(question)
        rubric = session.get(SolutionRubric, rubric_id)
        if rubric is not None:
            session.refresh(rubric)
    if question is None or question.source_type != OCR_SOURCE:
        return None
    # Reuse approval, pinned-rubric and reference-hash checks, not the CAS matcher.
    return resolve_grading_context(session, attempt)


def finalize_curated_ai_review(session: Session, attempt_id: UUID, review):
    """Commit one score and its evidence together; uncertain reviews stay provisional.

    AUTOMATED_CONSENSUS is the existing automatic-decision category. The actual
    evaluator and Gemini citations are persisted separately, without a migration.
    """
    if review.needs_teacher_review or not review.criterion_grades:
        return None
    attempt = session.scalar(select(SolutionAttempt).where(
        SolutionAttempt.id == attempt_id).with_for_update().execution_options(populate_existing=True))
    if attempt is None:
        raise ApplicationError(404, "ATTEMPT_NOT_FOUND", "Solution attempt not found.")
    existing = session.scalar(select(EvaluationDecision).where(EvaluationDecision.attempt_id == attempt_id))
    if existing is not None:
        return existing
    context = curated_context(session, attempt, refresh=True)
    if context is None:
        return None
    reference = resolve_answer_reference(session, attempt)
    if review.attempt_id != attempt_id or review.answer_sha256 != reference.content_sha256:
        raise ApplicationError(409, "GRADING_REFERENCE_CHANGED", "The reviewed reference has changed.")
    criteria = context.rubric.criteria["criteria"]
    from app.math_solutions.answer_grounded_ai import _load_confirmed_steps
    work, _ = _load_confirmed_steps(session, attempt_id)
    current_hash = sha256(json.dumps(work, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
    if review.submission_sha256 != current_hash:
        raise ApplicationError(409, "GRADING_SUBMISSION_CHANGED", "The submitted work changed during review.")
    steps = list(session.scalars(select(SolutionStep).where(
        SolutionStep.attempt_id == attempt_id, SolutionStep.is_deleted.is_(False)).order_by(SolutionStep.step_index)))
    step_grades = {grade.step_index: grade for grade in review.step_grades}
    if len(step_grades) != len(review.step_grades) or set(step_grades) != {s.step_index for s in steps}:
        raise ApplicationError(422, "AI_STEP_COVERAGE_INVALID", "Every submitted step must be assessed once.")
    if any(g.verdict not in {"VALID", "INVALID"} or g.confidence < .8 for g in review.step_grades):
        return None
    if any(g.confidence < .8 for g in review.criterion_grades) or any(
        check.confidence < .8 for grade in review.criterion_grades for check in grade.checks
    ):
        return None
    reference_text = "\n".join(filter(None, (reference.problem_content, reference.correct_answer, reference.explanation)))
    matches = criterion_matches(criteria, review.criterion_grades, set(step_grades),
                                reference_text + "\n" + json.dumps(criteria, ensure_ascii=False))
    now = datetime.now(timezone.utc)
    for step in steps:
        revision = session.scalar(select(StepRevision).where(StepRevision.step_id == step.id)
                                  .order_by(StepRevision.step_revision_number.desc()))
        if revision is None:
            raise ApplicationError(409, "STEP_REVISION_MISSING", "A submitted step has no revision.")
        grade = step_grades[step.step_index]
        session.add(StepEvaluation(
            step_revision_id=revision.id, rubric_id=context.rubric.id,
            evaluator_type="AI_HEURISTIC", math_validity=grade.verdict,
            score=grade.score, confidence=grade.confidence, error_detected=grade.verdict == "INVALID",
            error_description=grade.feedback,
            evidence_quote=json.dumps({"evaluator": "GEMINI_REFERENCE", "reference_sha256": review.answer_sha256,
                                       "review": grade.model_dump(mode="json")}, ensure_ascii=False),
            evaluated_at=now,
        ))
    score = round(min(1.0, max(0.0, sum(m.score_achieved for m in matches))), 2)
    decision = EvaluationDecision(
        id=uuid4(), attempt_id=attempt_id, rubric_id=context.rubric.id,
        decision_source="AUTOMATED_CONSENSUS", final_score=score,
        is_correct=score >= .85, confirmed_misconceptions=[], decided_at=now,
    )
    session.add(decision)
    attempt.status, attempt.total_score, attempt.is_correct = "EVALUATED", score, decision.is_correct
    attempt.evaluated_at = now
    from app.math_solutions.evidence_adapter import MathSolutionEvidenceAdapter

    try:
        session.flush()
        MathSolutionEvidenceAdapter(session).emit_evidence_for_decision(
            decision.id, rubric_matches=matches,
            evaluation_metadata={"evaluator": "GEMINI_REFERENCE", "review_source": "ANSWER_GROUNDED_AI",
                                 "reference_sha256": review.answer_sha256, "submission_sha256": current_hash})
        session.commit()
    except Exception:
        session.rollback()
        raise
    return decision
