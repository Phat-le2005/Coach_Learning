from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.gateway import AIGateway
from app.ai.mock_provider import MockAIProvider
from app.core.config import Settings
from app.knowledge_gap.evidence_context import DiagnosticEvidenceContext
from app.learning_evidence.models import LearningEvidenceEvent, LearningEvidenceSourceKind
from app.misconceptions.models import (
    MisconceptionCategory,
    MisconceptionDefinition,
    StudentMisconception,
)
from app.misconceptions.pipeline import MisconceptionPipeline
from app.misconceptions.schemas import MisconceptionAnalysisOutput
from app.practice.models import EvaluationStatus
from app.students.models import StudentProfile
from tests.practice.conftest import (
    PracticeContent,
    practice_content,
    practice_students,
    practice_user_factory,
    student_profile,
)


@pytest.mark.anyio
async def test_learning_evidence_adapter_is_scoped_and_advisory_only(
    db_session: Session,
    settings: Settings,
    student_profile: StudentProfile,
    practice_content: PracticeContent,
) -> None:
    definition = MisconceptionDefinition(
        code="EVIDENCE-SIGN-CONFUSION",
        concept_id=practice_content.concept.id,
        problem_type_id=practice_content.problem_type.id,
        name="Sign confusion from evidence",
        description="Confuses the derivative sign and monotonic direction.",
        category=MisconceptionCategory.CONCEPTUAL,
        is_active=True,
    )
    event = LearningEvidenceEvent(
        student_id=student_profile.id,
        subject_id=practice_content.subject.id,
        source_kind=LearningEvidenceSourceKind.PRACTICE_QUESTION,
        source_entity_id=uuid4(),
        is_correct=False,
        score=0.0,
        difficulty=0.5,
        hint_count=0,
        evaluation_status=EvaluationStatus.EVALUATED,
        occurred_at=datetime.now(timezone.utc),
    )
    db_session.add_all([definition, event])
    db_session.flush()
    output = MisconceptionAnalysisOutput(
        concept_id=practice_content.concept.id,
        problem_type_id=practice_content.problem_type.id,
        misconception_code=definition.code,
        error_category=MisconceptionCategory.CONCEPTUAL,
        first_wrong_step="Interpreted a positive derivative as decreasing.",
        confidence=0.9,
    )
    gateway = AIGateway(provider=MockAIProvider(canned_structured=output), settings=settings)
    context = DiagnosticEvidenceContext(
        evidence_event=event,
        student_id=student_profile.id,
        subject_id=practice_content.subject.id,
        concept_weights={practice_content.concept.id: 1.0},
        problem_type_weights={practice_content.problem_type.id: 1.0},
        primary_problem_type_id=practice_content.problem_type.id,
        student_response=(
            "Em tính đạo hàm rồi suy luận từng bước rằng dấu dương làm hàm nghịch biến."
        ),
        content=practice_content.mcq.content,
        expected_answer=practice_content.mcq.correct_answer,
        explanation=practice_content.mcq.explanation,
        difficulty=practice_content.mcq.difficulty,
        source_kind=LearningEvidenceSourceKind.PRACTICE_QUESTION,
        source_entity_id=event.source_entity_id,
        canonical_question=None,
    )
    result = await MisconceptionPipeline(db_session, gateway=gateway).run_for_evidence(
        context
    )
    assert result.detected
    assert result.misconception_code == definition.code
    assert not result.evidence_recorded
    assert db_session.scalar(select(StudentMisconception)) is None
