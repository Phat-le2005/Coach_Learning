from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.concepts.models import ConceptRelation, RelationType
from app.core.exceptions import ApplicationError
from app.curriculum.models import ProblemTypeConcept
from app.digital_twin.schemas import (
    DigitalTwinBasicProfileRead,
    KnownMisconceptionRead,
    ProblemTypeConceptLinkRead,
    RecentAttemptRead,
    StudyBehaviorRead,
)
from app.misconceptions.models import (
    MisconceptionDefinition,
    StudentMisconception,
    StudentMisconceptionStatus,
)
from app.practice.models import PracticeSession, PracticeSessionStatus, PracticeSessionType, QuestionAttempt
from app.questions.models import Question, QuestionConcept, QuestionProblemType
from app.students.models import StudentProfile
from app.users.models import User


@dataclass(frozen=True, slots=True)
class PrerequisiteEdge:
    prerequisite_concept_id: UUID
    target_concept_id: UUID


class StudentDigitalTwinRepository:
    """Batch-oriented read queries used to compose the transient twin."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def get_basic_profile(self, student_id: UUID) -> DigitalTwinBasicProfileRead:
        row = self.session.execute(
            select(StudentProfile, User)
            .join(User, User.id == StudentProfile.user_id)
            .where(StudentProfile.id == student_id)
        ).one_or_none()
        if row is None:
            raise ApplicationError(404, "STUDENT_NOT_FOUND", "Student profile was not found.")
        profile, user = row
        return DigitalTwinBasicProfileRead(
            student_id=profile.id,
            user_id=profile.user_id,
            email=user.email,
            full_name=user.full_name,
            grade_level=profile.grade_level,
            school_name=profile.school_name,
            date_of_birth=profile.date_of_birth,
            is_synthetic=profile.is_synthetic,
            synthetic_profile=profile.synthetic_profile,
        )

    def get_recent_attempts(
        self,
        student_id: UUID,
        *,
        limit: int = 20,
        session_type: PracticeSessionType | None = None,
    ) -> list[RecentAttemptRead]:
        statement = (
            select(QuestionAttempt, PracticeSession, Question)
            .join(
                PracticeSession,
                PracticeSession.id == QuestionAttempt.practice_session_id,
            )
            .join(Question, Question.id == QuestionAttempt.question_id)
            .where(QuestionAttempt.student_id == student_id)
            .order_by(QuestionAttempt.created_at.desc(), QuestionAttempt.id.desc())
            .limit(limit)
        )
        if session_type is not None:
            statement = statement.where(PracticeSession.session_type == session_type)
        rows = list(self.session.execute(statement))
        question_ids = {question.id for _, _, question in rows}
        concept_ids: dict[UUID, list[UUID]] = {question_id: [] for question_id in question_ids}
        problem_type_ids: dict[UUID, list[UUID]] = {
            question_id: [] for question_id in question_ids
        }
        if question_ids:
            for question_id, concept_id in self.session.execute(
                select(QuestionConcept.question_id, QuestionConcept.concept_id)
                .where(QuestionConcept.question_id.in_(question_ids))
                .order_by(QuestionConcept.question_id, QuestionConcept.concept_id)
            ):
                concept_ids[question_id].append(concept_id)
            for question_id, problem_type_id in self.session.execute(
                select(
                    QuestionProblemType.question_id,
                    QuestionProblemType.problem_type_id,
                )
                .where(QuestionProblemType.question_id.in_(question_ids))
                .order_by(
                    QuestionProblemType.question_id,
                    QuestionProblemType.problem_type_id,
                )
            ):
                problem_type_ids[question_id].append(problem_type_id)

        return [
            RecentAttemptRead(
                attempt_id=attempt.id,
                practice_session_id=attempt.practice_session_id,
                question_id=question.id,
                subject_id=question.subject_id,
                session_type=practice_session.session_type,
                question_type=question.question_type,
                question_content=question.content,
                student_answer=attempt.student_answer,
                is_correct=attempt.is_correct,
                score=attempt.score,
                evaluation_status=attempt.evaluation_status,
                response_time_seconds=attempt.response_time_seconds,
                hint_count=attempt.hint_count,
                attempted_at=attempt.created_at,
                concept_ids=concept_ids[question.id],
                problem_type_ids=problem_type_ids[question.id],
            )
            for attempt, practice_session, question in rows
        ]

    def get_prerequisite_edges(self, concept_ids: set[UUID]) -> list[PrerequisiteEdge]:
        if not concept_ids:
            return []
        return [
            PrerequisiteEdge(
                prerequisite_concept_id=source_id,
                target_concept_id=target_id,
            )
            for source_id, target_id in self.session.execute(
                select(
                    ConceptRelation.source_concept_id,
                    ConceptRelation.target_concept_id,
                )
                .where(
                    ConceptRelation.relation_type == RelationType.PREREQUISITE,
                    ConceptRelation.target_concept_id.in_(concept_ids),
                )
                .order_by(
                    ConceptRelation.target_concept_id,
                    ConceptRelation.source_concept_id,
                )
            )
        ]

    def get_problem_type_concept_links(
        self, problem_type_ids: set[UUID]
    ) -> list[ProblemTypeConceptLinkRead]:
        if not problem_type_ids:
            return []
        return [
            ProblemTypeConceptLinkRead(
                problem_type_id=problem_type_id,
                concept_id=concept_id,
                weight=weight,
                is_primary=is_primary,
            )
            for problem_type_id, concept_id, weight, is_primary in self.session.execute(
                select(
                    ProblemTypeConcept.problem_type_id,
                    ProblemTypeConcept.concept_id,
                    ProblemTypeConcept.weight,
                    ProblemTypeConcept.is_primary,
                )
                .where(ProblemTypeConcept.problem_type_id.in_(problem_type_ids))
                .order_by(
                    ProblemTypeConcept.problem_type_id,
                    ProblemTypeConcept.concept_id,
                )
            )
        ]

    def get_study_behavior(self, student_id: UUID) -> StudyBehaviorRead:
        total_sessions, completed_sessions = self.session.execute(
            select(
                func.count(PracticeSession.id),
                func.coalesce(
                    func.sum(
                        case(
                            (PracticeSession.status == PracticeSessionStatus.COMPLETED, 1),
                            else_=0,
                        )
                    ),
                    0,
                ),
            ).where(PracticeSession.student_id == student_id)
        ).one()
        (
            total_attempts,
            correct_attempts,
            average_response_time,
            total_hints,
            last_activity_at,
        ) = self.session.execute(
            select(
                func.count(QuestionAttempt.id),
                func.coalesce(
                    func.sum(case((QuestionAttempt.is_correct.is_(True), 1), else_=0)),
                    0,
                ),
                func.avg(QuestionAttempt.response_time_seconds),
                func.coalesce(func.sum(QuestionAttempt.hint_count), 0),
                func.max(QuestionAttempt.created_at),
            ).where(QuestionAttempt.student_id == student_id)
        ).one()
        return StudyBehaviorRead(
            total_sessions=int(total_sessions),
            completed_sessions=int(completed_sessions),
            total_attempts=int(total_attempts),
            correct_attempts=int(correct_attempts),
            average_response_time_seconds=(
                round(float(average_response_time), 3)
                if average_response_time is not None
                else None
            ),
            total_hints=int(total_hints),
            last_activity_at=last_activity_at,
        )

    def get_known_misconceptions(
        self, student_id: UUID
    ) -> list[KnownMisconceptionRead]:
        rows = self.session.execute(
            select(StudentMisconception, MisconceptionDefinition)
            .join(
                MisconceptionDefinition,
                MisconceptionDefinition.id
                == StudentMisconception.misconception_definition_id,
            )
            .where(
                StudentMisconception.student_id == student_id,
                StudentMisconception.status
                != StudentMisconceptionStatus.RESOLVED,
                MisconceptionDefinition.is_active.is_(True),
            )
            .order_by(
                case(
                    (
                        StudentMisconception.status
                        == StudentMisconceptionStatus.CONFIRMED,
                        0,
                    ),
                    else_=1,
                ),
                StudentMisconception.confidence.desc(),
                MisconceptionDefinition.code,
            )
        )
        return [
            KnownMisconceptionRead(
                misconception_definition_id=definition.id,
                code=definition.code,
                name=definition.name,
                category=definition.category,
                concept_id=definition.concept_id,
                problem_type_id=definition.problem_type_id,
                confidence=state.confidence,
                occurrence_count=state.occurrence_count,
                status=state.status,
                first_detected_at=state.first_detected_at,
                last_detected_at=state.last_detected_at,
            )
            for state, definition in rows
        ]
