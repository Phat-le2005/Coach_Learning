from uuid import UUID, uuid4
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import ApplicationError
from app.learning_evidence.models import LearningEvidenceEvent
from app.math_solutions.evaluator_service import MathEvaluatorService
from app.math_solutions.misconception_classifier import MisconceptionClassifier
from app.math_solutions.models import (
    EvaluationDecision,
    MathArtifact,
    SolutionAttempt,
    SolutionRubric,
    SolutionStep,
    StepEvaluation,
    StepRevision,
)
from app.math_solutions.rubric_evaluator import SolutionRubricEvaluator
from app.math_solutions.schemas import MathArtifactDraft, SolutionStepDraft
from app.math_solutions.service import MathSolutionService
from app.math_solutions.validator import DeterministicMathValidator, MathValidity
from app.practice.models import PracticeSession, PracticeSessionStatus, PracticeSessionType
from app.questions.models import Question, QuestionStatus, QuestionType
from app.students.models import StudentProfile
from app.subjects.models import Subject
from app.users.models import Role
from app.users.schemas import UserCreate
from app.users.service import UserService


def test_tier2_deterministic_validator_calculus_derivative():
    # Target function: y = 1/3 x^3 - x^2 - 3x + 1 -> y' = x^2 - 2x - 3
    target_latex = r"\frac{1}{3}x^3 - x^2 - 3x + 1"
    validator = DeterministicMathValidator(target_function_latex=target_latex)

    # 1. Correct derivative
    res_correct = validator.validate_step(
        step_type="DERIVATIVE_CALCULATION",
        content_latex=r"y' = x^2 - 2x - 3",
    )
    assert res_correct.validity == MathValidity.VALID
    assert res_correct.score == 1.0
    assert res_correct.confidence == 1.0
    assert not res_correct.error_detected

    # 2. Derivative arithmetic slip: x^2 + 2x - 3
    res_slip = validator.validate_step(
        step_type="DERIVATIVE_CALCULATION",
        content_latex=r"y' = x^2 + 2x - 3",
    )
    assert res_slip.validity == MathValidity.INVALID
    assert res_slip.score == 0.0
    assert res_slip.error_detected
    assert res_slip.error_code == "DERIVATIVE_ARITHMETIC_SLIP"

    # 3. Unparseable syntax doesn't crash, returns UNDETERMINED
    res_unparseable = validator.validate_step(
        step_type="DERIVATIVE_CALCULATION",
        content_latex=r"y' = ??? + \\invalid+++syntax",
    )
    assert res_unparseable.validity == MathValidity.UNDETERMINED
    assert res_unparseable.score is None


def test_tier2_deterministic_validator_roots_and_sign_table():
    target_latex = r"\frac{1}{3}x^3 - x^2 - 3x + 1"
    validator = DeterministicMathValidator(target_function_latex=target_latex)

    # 1. Roots correct: x = -1 \lor x = 3
    res_roots = validator.validate_step(
        step_type="ROOT_FINDING",
        content_latex=r"y' = 0 \Leftrightarrow x = -1 \lor x = 3",
    )
    assert res_roots.validity == MathValidity.VALID
    assert res_roots.score == 1.0

    # 2. Roots incorrect: x = 1 \lor x = -3
    res_wrong_roots = validator.validate_step(
        step_type="ROOT_FINDING",
        content_latex=r"y' = 0 \Leftrightarrow x = 1 \lor x = -3",
    )
    assert res_wrong_roots.validity == MathValidity.INVALID
    assert res_wrong_roots.error_code == "ROOT_FINDING_ERROR"

    # 3. Sign table correct: ['+', '-', '+'] for roots [-1, 3]
    res_sign_correct = validator.validate_step(
        step_type="SIGN_TABLE",
        content_latex=None,
        artifact_payload={"critical_points": [-1, 3], "signs": ["+", "-", "+"]},
    )
    assert res_sign_correct.validity == MathValidity.VALID
    assert res_sign_correct.score == 1.0

    # 4. Sign table inverted: ['-', '+', '-']
    res_sign_inverted = validator.validate_step(
        step_type="SIGN_TABLE",
        content_latex=None,
        artifact_payload={"critical_points": [-1, 3], "signs": ["-", "+", "-"]},
    )
    assert res_sign_inverted.validity == MathValidity.INVALID
    assert res_sign_inverted.error_code == "SIGN_TABLE_QUADRATIC_RULE_INVERTED"


def test_tier4_misconception_classifier_disentangles_4_classes(db_session: Session):
    classifier = MisconceptionClassifier(session=db_session)

    # Class (a): DERIVATIVE_ARITHMETIC_SLIP
    c_a = classifier.classify_error(
        error_code="DERIVATIVE_ARITHMETIC_SLIP",
        step_type="DERIVATIVE_CALCULATION",
        content_latex=r"y' = x^2 + 2x - 3",
        explanation_text="Tính nhầm dấu.",
    )
    assert c_a is not None
    assert c_a.code == "DERIVATIVE_ARITHMETIC_SLIP"
    assert c_a.status == "SUSPECTED"

    # Class (b): ROOT_FINDING_ERROR
    c_b = classifier.classify_error(
        error_code="ROOT_FINDING_ERROR",
        step_type="ROOT_FINDING",
        content_latex=r"x = 1 \lor x = -3",
        explanation_text="Nhầm dấu nghiệm.",
    )
    assert c_b is not None
    assert c_b.code == "ROOT_FINDING_ERROR"
    assert c_b.status == "SUSPECTED"

    # Class (c): SIGN_TABLE_QUADRATIC_RULE_INVERTED
    c_c = classifier.classify_error(
        error_code="SIGN_TABLE_QUADRATIC_RULE_INVERTED",
        step_type="SIGN_TABLE",
        content_latex=None,
        explanation_text=None,
        artifact_payload={"critical_points": [-1, 3], "signs": ["-", "+", "-"]},
    )
    assert c_c is not None
    assert c_c.code == "SIGN_TABLE_QUADRATIC_RULE_INVERTED"
    assert c_c.status == "SUSPECTED"

    # Class (d): DERIVATIVE_SIGN_DIRECTION
    c_d = classifier.classify_error(
        error_code="DERIVATIVE_SIGN_DIRECTION",
        step_type="CONCLUSION",
        content_latex=r"Hàm số nghịch biến trên (3; +\infty)",
        explanation_text="Dù y' > 0 nhưng kết luận nghịch biến.",
        sign_table_was_inverted=False,
    )
    assert c_d is not None
    assert c_d.code == "DERIVATIVE_SIGN_DIRECTION"
    assert c_d.status == "SUSPECTED"


def test_tier3_rubric_evaluator_scoring():
    evaluator = SolutionRubricEvaluator(rubric=None)
    # 2 valid steps: Domain (0.10) and Derivative (0.30), 3 invalid steps
    step_validities = [
        {"step_index": 1, "step_type": "ASSUMPTION", "validity": "VALID", "raw_score": 1.0},
        {"step_index": 2, "step_type": "DERIVATIVE_CALCULATION", "validity": "VALID", "raw_score": 1.0},
        {"step_index": 3, "step_type": "ROOT_FINDING", "validity": "INVALID", "raw_score": 0.0},
        {"step_index": 4, "step_type": "SIGN_TABLE", "validity": "INVALID", "raw_score": 0.0},
        {"step_index": 5, "step_type": "CONCLUSION", "validity": "INVALID", "raw_score": 0.0},
    ]

    final_score, matches = evaluator.evaluate(step_validities)
    assert final_score == 0.40
    assert len(matches) == 5


def test_e2e_vertical_slice_monotonicity_evaluation(db_session: Session):
    """
    VERTICAL SLICE SCENARIO from VERTICAL_SLICE.md:
    Student solves: y = 1/3 x^3 - x^2 - 3x + 1
    Step 1 (Domain): D = R -> VALID
    Step 2 (Derivative): y' = x^2 - 2x - 3 -> VALID
    Step 3 (Roots): y' = 0 <=> x = -1 or x = 3 -> VALID
    Step 4 (Sign Table): inverted signs ['-', '+', '-'] -> INVALID (SIGN_TABLE_QUADRATIC_RULE_INVERTED)
    Step 5 (Conclusion): increasing on (-1, 3) -> INVALID
    Expected Result:
    - final_score = 0.40 (or 0.60 if roots scored 0.20)
    - is_correct = False
    - confirmed_misconceptions contains SIGN_TABLE_QUADRATIC_RULE_INVERTED
    """
    users = UserService(db_session)
    student_user = users.create_user(
        UserCreate(
            email="eval-student@example.com",
            password="Eval-Test-Password-2026!",
            full_name="Eval Student",
            role=Role.STUDENT,
        )
    )
    teacher_user = users.create_user(
        UserCreate(
            email="eval-teacher@example.com",
            password="Eval-Test-Password-2026!",
            full_name="Eval Teacher",
            role=Role.TEACHER,
        )
    )

    profile = db_session.scalar(
        select(StudentProfile).where(StudentProfile.user_id == student_user.id)
    )
    subject = Subject(code="MATH-EVAL-12", name="Math Eval 12", grade_level=12)
    db_session.add(subject)
    db_session.flush()

    question = Question(
        subject_id=subject.id,
        content=r"Tìm các khoảng đơn điệu của hàm số: y = \frac{1}{3}x^3 - x^2 - 3x + 1",
        question_type=QuestionType.OPEN_RESPONSE,
        difficulty=0.5,
        correct_answer=None,
        explanation="Đáp án mẫu",
        source_type="TEST",
        exam_weight=0.5,
        status=QuestionStatus.APPROVED,
        created_by=teacher_user.id,
    )
    db_session.add(question)
    db_session.flush()

    rubric = SolutionRubric(
        question_id=question.id,
        title="Reviewed polynomial monotonicity rubric",
        status="APPROVED",
        approved_by=teacher_user.id,
        criteria=[
            {"id": "domain", "step_type": "ASSUMPTION", "weight": 0.10},
            {"id": "derivative", "step_type": "DERIVATIVE_CALCULATION", "weight": 0.30},
            {"id": "roots", "step_type": "ROOT_FINDING", "weight": 0.20},
            {"id": "signs", "step_type": "SIGN_TABLE", "weight": 0.25},
            {"id": "conclusion", "step_type": "CONCLUSION", "weight": 0.15},
        ],
    )
    db_session.add(rubric)
    db_session.flush()
    practice = PracticeSession(
        student_id=profile.id,
        subject_id=subject.id,
        session_type=PracticeSessionType.PRACTICE,
        status=PracticeSessionStatus.ACTIVE,
    )
    db_session.add(practice)
    db_session.commit()

    service = MathSolutionService(db_session)
    attempt_dict = service.create(
        student_user.id,
        source_kind="CANONICAL",
        context_type="SELF_PRACTICE",
        mode="INDEPENDENT_SOLUTION",
        create_idempotency_key="eval-attempt-slice",
        question_id=question.id,
        practice_session_id=practice.id,
        rubric_id=rubric.id,
    )
    attempt_id = UUID(attempt_dict["id"])

    # Step 1: Assumption D = R
    rev = attempt_dict["attempt_revision_number"]
    curr = service.add_step(
        student_user.id,
        attempt_id,
        expected_attempt_revision=rev,
        client_action_id=uuid4(),
        draft=SolutionStepDraft(
            step_type="ASSUMPTION",
            content_latex=r"D = \mathbb{R}",
            explanation_text="Tập xác định của hàm đa thức.",
        ),
    )

    # Step 2: Derivative Calculation
    curr = service.add_step(
        student_user.id,
        attempt_id,
        expected_attempt_revision=curr["attempt_revision_number"],
        client_action_id=uuid4(),
        draft=SolutionStepDraft(
            step_type="DERIVATIVE_CALCULATION",
            content_latex=r"y' = x^2 - 2x - 3",
            explanation_text="Tính đạo hàm bậc nhất của hàm số.",
        ),
    )

    # Step 3: Roots
    curr = service.add_step(
        student_user.id,
        attempt_id,
        expected_attempt_revision=curr["attempt_revision_number"],
        client_action_id=uuid4(),
        draft=SolutionStepDraft(
            step_type="ROOT_FINDING",
            content_latex=r"y' = 0 \Leftrightarrow x = -1 \lor x = 3",
            explanation_text="Tìm nghiệm đạo hàm.",
        ),
    )

    # Step 4: Sign Table (with inverted mistake: ['-', '+', '-'])
    curr = service.add_step(
        student_user.id,
        attempt_id,
        expected_attempt_revision=curr["attempt_revision_number"],
        client_action_id=uuid4(),
        draft=SolutionStepDraft(
            step_type="SIGN_TABLE",
            content_latex=r"\text{Bảng xét dấu } y'",
            explanation_text="Xét dấu tam thức bậc hai.",
            artifact=MathArtifactDraft(
                artifact_type="SIGN_TABLE",
                payload={"critical_points": [-1, 3], "signs": ["-", "+", "-"]},
            ),
        ),
    )

    # Step 5: Conclusion based on inverted sign table
    curr = service.add_step(
        student_user.id,
        attempt_id,
        expected_attempt_revision=curr["attempt_revision_number"],
        client_action_id=uuid4(),
        draft=SolutionStepDraft(
            step_type="CONCLUSION",
            content_latex=r"\text{Hàm số đồng biến trên } (-1, 3)",
            explanation_text="Do y' mang dấu + trên khoảng (-1, 3).",
        ),
    )

    # Submit solution
    submitted = service.submit(
        student_user.id,
        attempt_id,
        expected_attempt_revision=curr["attempt_revision_number"],
        client_action_id=uuid4(),
    )
    assert submitted["status"] == "SUBMITTED"

    # Evaluate solution using MathEvaluatorService
    eval_service = MathEvaluatorService(db_session)
    decision = eval_service.evaluate_attempt(attempt_id)

    assert decision is not None
    assert decision.decision_source == "AUTOMATED_CONSENSUS"
    assert not decision.is_correct
    assert "SIGN_TABLE_QUADRATIC_RULE_INVERTED" in decision.confirmed_misconceptions

    # Verify attempt updated
    db_session.expire_all()
    attempt_db = db_session.get(SolutionAttempt, attempt_id)
    assert attempt_db.status == "EVALUATED"
    assert not attempt_db.is_correct
    assert attempt_db.total_score == decision.final_score

    # Verify StepEvaluation records exist and are linked to revisions
    evaluations = db_session.scalars(
        select(StepEvaluation)
    ).all()
    assert len(evaluations) >= 5
    for ev in evaluations:
        assert ev.step_revision_id is not None
        assert ev.math_validity in ("VALID", "INVALID", "UNDETERMINED", "NEEDS_REVIEW")


    # Unknown handwritten/explanation content must not be converted into a
    # zero or a final score; no evidence is emitted for this submitted work.
    from app.learning_evidence.models import LearningEvidenceEvent

    evidence_before = len(db_session.scalars(select(LearningEvidenceEvent)).all())
    unresolved = service.create(
        student_user.id,
        source_kind="CANONICAL",
        context_type="SELF_PRACTICE",
        mode="INDEPENDENT_SOLUTION",
        create_idempotency_key="eval-attempt-unresolved",
        question_id=question.id,
        practice_session_id=practice.id,
        rubric_id=rubric.id,
    )
    unresolved_id = UUID(unresolved["id"])
    updated = service.add_step(
        student_user.id,
        unresolved_id,
        expected_attempt_revision=unresolved["attempt_revision_number"],
        client_action_id=uuid4(),
        draft=SolutionStepDraft(step_type="EXPLANATION", explanation_text="Needs human review."),
    )
    service.submit(
        student_user.id,
        unresolved_id,
        expected_attempt_revision=updated["attempt_revision_number"],
        client_action_id=uuid4(),
    )
    with pytest.raises(ApplicationError) as exc:
        eval_service.evaluate_attempt(unresolved_id)
    assert exc.value.code == "GRADING_REVIEW_REQUIRED"
    assert db_session.get(SolutionAttempt, unresolved_id).status == "SUBMITTED"
    assert db_session.scalar(
        select(EvaluationDecision).where(EvaluationDecision.attempt_id == unresolved_id)
    ) is None
    assert len(db_session.scalars(select(LearningEvidenceEvent)).all()) == evidence_before

def test_evaluation_rolls_back_if_learning_evidence_write_fails(db_session: Session):
    """Never publish a grading decision without its linked learning evidence."""
    from unittest.mock import patch

    users = UserService(db_session)
    student_user = users.create_user(
        UserCreate(
            email="eval-atomic-student@example.com",
            password="Eval-Test-Password-2026!",
            full_name="Atomicity Student",
            role=Role.STUDENT,
        )
    )
    teacher_user = users.create_user(
        UserCreate(
            email="eval-atomic-teacher@example.com",
            password="Eval-Test-Password-2026!",
            full_name="Atomicity Teacher",
            role=Role.TEACHER,
        )
    )
    student = db_session.scalar(
        select(StudentProfile).where(StudentProfile.user_id == student_user.id)
    )
    subject = Subject(code="MATH-EVAL-ATOMIC", name="Math Eval Atomic", grade_level=12)
    db_session.add(subject)
    db_session.flush()
    question = Question(
        subject_id=subject.id,
        content="Tính đạo hàm của hàm số y = x^3",
        question_type=QuestionType.OPEN_RESPONSE,
        difficulty=0.5,
        source_type="TEST",
        exam_weight=0.5,
        status=QuestionStatus.APPROVED,
        created_by=teacher_user.id,
    )
    db_session.add(question)
    db_session.flush()
    rubric = SolutionRubric(
        question_id=question.id,
        title="Reviewed derivative rubric",
        status="APPROVED",
        approved_by=teacher_user.id,
        criteria=[{"id": "derivative", "step_type": "DERIVATIVE_CALCULATION", "weight": 1.0}],
    )
    db_session.add(rubric)
    db_session.flush()
    practice = PracticeSession(
        student_id=student.id,
        subject_id=subject.id,
        session_type=PracticeSessionType.PRACTICE,
        status=PracticeSessionStatus.ACTIVE,
    )
    db_session.add(practice)
    db_session.commit()

    service = MathSolutionService(db_session)
    created = service.create(
        student_user.id,
        source_kind="CANONICAL",
        context_type="SELF_PRACTICE",
        mode="INDEPENDENT_SOLUTION",
        create_idempotency_key="eval-atomicity-test",
        question_id=question.id,
        practice_session_id=practice.id,
        rubric_id=rubric.id,
    )
    attempt_id = UUID(created["id"])
    updated = service.add_step(
        student_user.id,
        attempt_id,
        expected_attempt_revision=created["attempt_revision_number"],
        client_action_id=uuid4(),
        draft=SolutionStepDraft(
            step_type="DERIVATIVE_CALCULATION",
            content_latex="y' = 3x^2",
        ),
    )
    service.submit(
        student_user.id,
        attempt_id,
        expected_attempt_revision=updated["attempt_revision_number"],
        client_action_id=uuid4(),
    )

    with patch(
        "app.math_solutions.evidence_adapter.MathSolutionEvidenceAdapter.emit_evidence_for_decision",
        side_effect=RuntimeError("evidence database unavailable"),
    ):
        with pytest.raises(RuntimeError, match="evidence database unavailable"):
            MathEvaluatorService(db_session).evaluate_attempt(attempt_id)

    db_session.expire_all()
    assert db_session.get(SolutionAttempt, attempt_id).status == "SUBMITTED"
    assert db_session.scalar(
        select(EvaluationDecision).where(EvaluationDecision.attempt_id == attempt_id)
    ) is None
    assert db_session.scalars(select(StepEvaluation)).all() == []
