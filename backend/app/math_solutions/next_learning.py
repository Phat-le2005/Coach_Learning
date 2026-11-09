"""Read-only post-assessment advice; only explicit launch creates a practice attempt.

The persisted decision/evidence own the score. Suggestions never grade, update
mastery, infer misconceptions from prose, or call an LLM.
"""

from __future__ import annotations

from datetime import datetime
import math
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.assignments.models import (
    Assignment,
    AssignmentMaterialItemConcept,
    AssignmentMaterialItemProblemType,
    AssignmentDeliveryMode,
    StudentAssignment,
    StudentAssignmentStatus,
)
from app.concepts.models import Concept
from app.core.exceptions import ApplicationError
from app.curriculum.models import Chapter, ProblemType, Topic
from app.learning_evidence.models import LearningEvidenceEvent
from app.learning_evidence.skill_outcomes import KEY
from app.mastery.aggregation import MasteryAggregationService
from app.math_solutions.models import (
    EvaluationDecision,
    SolutionAttempt,
    SolutionRubric,
)
from app.math_solutions.service import MathSolutionService
from app.practice.models import (
    PracticeSession,
    PracticeSessionType,
    PracticeSessionConcept,
    PracticeSessionProblemType,
)
from app.questions.models import (
    Question,
    QuestionConcept,
    QuestionProblemType,
    QuestionType,
)
from app.questions.presentation_quality import question_has_broken_math_extraction
from app.questions.reference_solution import has_grading_reference
from app.recommendations.priority_service import LearningPriorityService
from app.recommendations.question_service import QuestionRecommendationService
from app.review.models import ReviewSchedule


class CriterionGap(BaseModel):
    title: str
    achieved: float
    maximum: float
    step_index: int | None = None


class LearningTarget(BaseModel):
    id: UUID
    kind: Literal["CONCEPT", "PROBLEM_TYPE"]
    name: str
    reason: str
    mastery_score: float | None = None
    mastery_state: str | None = None
    evidence_count: int = 0
    next_review_at: datetime | None = None


class SuggestedQuestion(BaseModel):
    id: UUID
    content: str
    difficulty: float


class NextLearningRead(BaseModel):
    attempt_id: UUID
    decision_id: UUID | None = None
    status: Literal["WAITING_REVIEW", "WAITING_SUBMISSION", "REINFORCE", "CONTINUE"]
    score: float | None = None
    evidence_recorded: bool = False
    headline: str
    explanation: str
    criterion_gaps: list[CriterionGap] = Field(default_factory=list)
    target: LearningTarget | None = None
    question: SuggestedQuestion | None = None
    supply_message: str | None = None


class LaunchNextLearning(BaseModel):
    decision_id: UUID
    question_id: UUID


REASONS = {
    "PREREQUISITE_REPAIR": "Củng cố kiến thức nền trước khi học tiếp.",
    "REVIEW_DUE": "Nội dung này đã đến lịch ôn trong kế hoạch của bạn.",
    "WEAK_CONCEPT": "Hồ sơ học tập hiện tại cho thấy kiến thức này cần được củng cố.",
    "WEAK_PROBLEM_TYPE": "Dạng bài này đang được ưu tiên luyện thêm.",
    "CURRENT_LESSON": "Tiếp tục nội dung đang học trên lớp.",
    "DIAGNOSTIC_FOLLOWUP": "Luyện thêm để bổ sung bằng chứng sau kiểm tra.",
    "VERIFIED_ROOT_CAUSE": "Ưu tiên phần nền tảng đã được xác minh cần củng cố.",
}


def _number(value):
    return type(value) in (int, float) and math.isfinite(value)


def criterion_gaps(metadata: dict, rubric: SolutionRubric | None) -> list[CriterionGap]:
    """Use saved criterion outcomes, never compare count of valid steps with score."""
    outcomes = metadata.get(KEY, {}) if isinstance(metadata, dict) else {}
    rows = (
        outcomes.get("criteria", [])
        if isinstance(outcomes, dict) and outcomes.get("version") == 1
        else []
    )
    criteria = rubric.criteria if rubric and isinstance(rubric.criteria, dict) else {}
    raw_definitions = criteria.get("criteria", [])
    definitions = (
        {
            c["id"]: c
            for c in raw_definitions
            if isinstance(c, dict) and isinstance(c.get("id"), str)
        }
        if isinstance(raw_definitions, list)
        else {}
    )
    gaps = []
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict):
            continue
        weight, achieved = row.get("weight"), row.get("achieved")
        if not (_number(weight) and _number(achieved) and 0 <= achieved < weight <= 1):
            continue
        identifier = row.get("criterion_id")
        definition = (
            definitions.get(identifier, {}) if isinstance(identifier, str) else {}
        )
        title = (
            definition.get("title")
            or definition.get("description")
            or "Một tiêu chí của rubric chưa đạt đủ điểm"
        )
        index = row.get("step_index")
        gaps.append(
            CriterionGap(
                title=str(title)[:220],
                achieved=achieved,
                maximum=weight,
                step_index=index if type(index) is int and index > 0 else None,
            )
        )
    return gaps[:4]


class NextLearningService:
    def __init__(self, session: Session):
        self.session = session

    def _context(self, actor: UUID, attempt_id: UUID):
        attempt = MathSolutionService(self.session)._attempt(
            actor, attempt_id, lock=False
        )
        assignment = (
            self.session.get(Assignment, attempt.assignment_id)
            if attempt.assignment_id
            else None
        )
        question = (
            self.session.get(Question, attempt.question_id)
            if attempt.question_id
            else None
        )
        subject_id = (
            assignment.subject_id
            if assignment
            else question.subject_id
            if question
            else None
        )
        if subject_id is None:
            raise ApplicationError(
                409,
                "LEARNING_CONTEXT_UNAVAILABLE",
                "Chưa xác định được môn học của bài làm.",
            )
        return attempt, assignment, subject_id

    def _links(self, attempt, subject_id):
        if attempt.question_id:
            concepts = self.session.scalars(
                select(QuestionConcept.concept_id).where(
                    QuestionConcept.question_id == attempt.question_id
                )
            ).all()
            types = self.session.scalars(
                select(QuestionProblemType.problem_type_id).where(
                    QuestionProblemType.question_id == attempt.question_id
                )
            ).all()
        else:
            concepts = self.session.scalars(
                select(AssignmentMaterialItemConcept.concept_id).where(
                    AssignmentMaterialItemConcept.assignment_material_item_id
                    == attempt.assignment_material_item_id
                )
            ).all()
            types = self.session.scalars(
                select(AssignmentMaterialItemProblemType.problem_type_id).where(
                    AssignmentMaterialItemProblemType.assignment_material_item_id
                    == attempt.assignment_material_item_id
                )
            ).all()
        # Only explicit curriculum links in this subject, never keyword guesses.
        return {
            ("CONCEPT", c.id): c
            for c in self.session.scalars(
                select(Concept).where(
                    Concept.id.in_(concepts), Concept.subject_id == subject_id
                )
            )
        } | {
            ("PROBLEM_TYPE", p.id): p
            for p in self.session.scalars(
                select(ProblemType)
                .join(Topic)
                .join(Chapter)
                .where(
                    ProblemType.id.in_(types),
                    Chapter.subject_id == subject_id,
                    ProblemType.is_active.is_(True),
                )
            )
        }

    def get(self, actor: UUID, attempt_id: UUID) -> NextLearningRead:
        attempt, assignment, subject_id = self._context(actor, attempt_id)
        if assignment and assignment.delivery_mode == AssignmentDeliveryMode.EXAM:
            assigned = self.session.get(
                StudentAssignment, attempt.student_assignment_id
            )
            if assigned is None or assigned.status not in {
                StudentAssignmentStatus.SUBMITTED,
                StudentAssignmentStatus.GRADED,
            }:
                return NextLearningRead(
                    attempt_id=attempt_id,
                    status="WAITING_SUBMISSION",
                    headline="Hoàn thành bài kiểm tra trước",
                    explanation="Đề xuất cá nhân sẽ mở sau khi bạn nộp toàn bộ bài kiểm tra.",
                )
        decision = self.session.scalar(
            select(EvaluationDecision).where(
                EvaluationDecision.attempt_id == attempt.id
            )
        )
        if decision is None:
            return NextLearningRead(
                attempt_id=attempt_id,
                status="WAITING_REVIEW",
                headline="Đối chiếu bài làm trước khi học tiếp",
                explanation="Bài này chưa có điểm chính thức được lưu. Hãy xem lại góp ý và nhờ giáo viên kiểm tra phần chưa rõ.",
            )
        evidence = (
            self.session.get(LearningEvidenceEvent, decision.learning_evidence_event_id)
            if decision.learning_evidence_event_id
            else None
        )
        recorded = bool(
            evidence
            and evidence.student_id == attempt.student_id
            and evidence.source_entity_id == decision.id
            and evidence.subject_id == subject_id
            and evidence.score == decision.final_score
        )
        metadata = evidence.event_metadata if recorded else {}
        rubric = (
            self.session.get(SolutionRubric, decision.rubric_id)
            if decision.rubric_id
            else None
        )
        gaps = criterion_gaps(metadata, rubric)
        reinforce = decision.final_score < 0.85 or not decision.is_correct or bool(gaps)
        result = NextLearningRead(
            attempt_id=attempt.id,
            decision_id=decision.id,
            status="REINFORCE" if reinforce else "CONTINUE",
            score=decision.final_score,
            evidence_recorded=recorded,
            criterion_gaps=gaps,
            headline="Củng cố một chút, tiến bộ thêm một bước"
            if reinforce
            else "Tiếp tục giữ nhịp học của bạn",
            explanation=(
                "Bài đã có điểm, nhưng một số yêu cầu vẫn chưa đạt đủ. Ưu tiên củng cố trước khi tăng độ khó."
                if reinforce
                else "Bạn đã hoàn thành tốt bài này. Bước tiếp theo được chọn từ ưu tiên học tập hiện tại; một bài đúng chưa có nghĩa đã nắm vững toàn bộ kiến thức."
            ),
        )
        linked = self._links(attempt, subject_id)
        if not linked:
            result.supply_message = "Bài này chưa được gắn kiến thức hoặc dạng bài. Bạn có thể xem kế hoạch học; giáo viên cần bổ sung liên kết để gợi ý chính xác."
            return result
        priorities = LearningPriorityService(self.session).get_priorities(
            attempt.student_id, subject_id
        )
        chosen, reason = None, None
        # Prefer the weakest explicitly assessed concept in this very decision.
        outcomes = metadata.get(KEY, {}) if isinstance(metadata, dict) else {}
        concept_scores = (
            outcomes.get("concepts", {})
            if isinstance(outcomes, dict) and outcomes.get("version") == 1
            else {}
        )
        if reinforce and isinstance(concept_scores, dict):
            weak = [
                (float(row["score"]), ("CONCEPT", identifier))
                for kind, identifier in linked
                if kind == "CONCEPT"
                and isinstance(row := concept_scores.get(str(identifier)), dict)
                and _number(row.get("score"))
                and 0 <= row["score"] < 0.85
            ]
            if weak:
                chosen = min(weak, key=lambda item: (item[0], str(item[1][1])))[1]
                reason = "Tiêu chí đã chấm của bài vừa làm cho thấy phần kiến thức này cần củng cố."
        if chosen is None:
            eligible = [
                p
                for p in priorities
                if (p.target_type.value, p.concept_id or p.problem_type_id) in linked
            ]
            priority = eligible[0] if eligible else None
            chosen = (
                (
                    priority.target_type.value,
                    priority.concept_id or priority.problem_type_id,
                )
                if priority
                else next(iter(linked))
            )
            reason = (
                "Bài vừa làm chưa đạt đủ điểm. Luyện lại một nội dung được gắn với bài để kiểm tra mức hiểu."
                if reinforce
                else REASONS.get(
                    str(priority.reason_code),
                    "Luyện thêm nội dung liên quan để củng cố kết quả vừa đạt.",
                )
                if priority
                else "Luyện thêm nội dung liên quan để có thêm bằng chứng học tập."
            )
        kind, identifier = chosen
        entity = linked[chosen]
        aggregation = MasteryAggregationService(self.session)
        snapshot = (
            aggregation.get_concept_mastery(attempt.student_id, identifier)
            if kind == "CONCEPT"
            else aggregation.get_problem_type_mastery(attempt.student_id, identifier)
        )
        schedule = self.session.scalar(
            select(ReviewSchedule).where(
                ReviewSchedule.student_id == attempt.student_id,
                (
                    ReviewSchedule.concept_id == identifier
                    if kind == "CONCEPT"
                    else ReviewSchedule.problem_type_id == identifier
                ),
            )
        )
        result.target = LearningTarget(
            id=identifier,
            kind=kind,
            name=entity.name,
            reason=reason,
            mastery_score=snapshot.mastery_score if snapshot.attempt_count else None,
            mastery_state=str(snapshot.state) if snapshot.attempt_count else None,
            evidence_count=snapshot.attempt_count,
            next_review_at=schedule.next_review_at if schedule else None,
        )
        exclusions = set(
            self.session.scalars(
                select(SolutionAttempt.question_id).where(
                    SolutionAttempt.student_id == attempt.student_id,
                    SolutionAttempt.question_id.is_not(None),
                )
            )
        )
        rec = QuestionRecommendationService(self.session).recommend(
            attempt.student_id,
            subject_id,
            target_concept_id=identifier if kind == "CONCEPT" else None,
            target_problem_type_id=identifier if kind == "PROBLEM_TYPE" else None,
            exclude_question_ids=exclusions,
            allowed_question_types={QuestionType.OPEN_RESPONSE},
            question_filter=lambda q: has_grading_reference(
                q.correct_answer, q.explanation
            )
            and not question_has_broken_math_extraction(q),
        )
        if rec:
            question = self.session.get(Question, rec.question_id)
            result.question = SuggestedQuestion(
                id=question.id, content=question.content, difficulty=rec.difficulty
            )
        else:
            result.supply_message = "Chưa có bài tự luận mới phù hợp cho mục tiêu này. Bạn vẫn có thể ôn lý thuyết hoặc xem kế hoạch học."
        return result

    def launch(
        self, actor: UUID, attempt_id: UUID, request: LaunchNextLearning
    ) -> UUID:
        attempt, _, subject_id = self._context(actor, attempt_id)
        # Serialize double clicks/replays on the source attempt. No GET writes.
        self.session.scalar(
            select(SolutionAttempt)
            .where(SolutionAttempt.id == attempt.id)
            .with_for_update()
        )
        key = f"next-learning:{attempt.id.hex}:{request.question_id.hex}"
        decision = self.session.get(EvaluationDecision, request.decision_id)
        if decision is None or decision.attempt_id != attempt_id:
            raise ApplicationError(
                409,
                "LEARNING_SUGGESTION_CHANGED",
                "Kết quả bài làm đã thay đổi. Hãy tải lại đề xuất.",
            )
        previous = self.session.scalar(
            select(SolutionAttempt).where(
                SolutionAttempt.student_id == attempt.student_id,
                SolutionAttempt.create_idempotency_key == key,
            )
        )
        if previous is not None:
            return previous.id
        suggestion = self.get(actor, attempt_id)
        if (
            suggestion.decision_id != request.decision_id
            or suggestion.question is None
            or suggestion.question.id != request.question_id
        ):
            raise ApplicationError(
                409,
                "LEARNING_SUGGESTION_CHANGED",
                "Bài luyện được đề xuất đã thay đổi. Hãy tải lại đề xuất.",
            )
        target = suggestion.target
        practice = PracticeSession(
            student_id=attempt.student_id,
            subject_id=subject_id,
            session_type=PracticeSessionType.PRACTICE,
            concept_links=[PracticeSessionConcept(concept_id=target.id)]
            if target.kind == "CONCEPT"
            else [],
            problem_type_links=[PracticeSessionProblemType(problem_type_id=target.id)]
            if target.kind == "PROBLEM_TYPE"
            else [],
        )
        try:
            self.session.add(practice)
            self.session.flush()
            created = MathSolutionService(self.session).create(
                actor,
                source_kind="CANONICAL",
                context_type="SELF_PRACTICE",
                mode="INDEPENDENT_SOLUTION",
                create_idempotency_key=key,
                question_id=request.question_id,
                practice_session_id=practice.id,
            )
        except Exception:
            self.session.rollback()
            raise
        return UUID(created["id"])
