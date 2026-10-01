from uuid import UUID
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload
from app.classes.models import EnrollmentStatus, StudentEnrollment, TeacherClassroom
from app.core.exceptions import ApplicationError
from app.learning_evidence.models import LearningEvidenceConcept, LearningEvidenceEvent, LearningEvidenceProblemType
from app.students.models import StudentProfile
from app.teachers.models import TeacherProfile

class StudentLearningEvidenceService:
    def __init__(self, session: Session) -> None: self.session = session

    def recent_for_student(self, actor_user_id: UUID, student_id: UUID, *, is_teacher: bool, limit: int = 50, assignment_id: UUID | None = None, problem_type_id: UUID | None = None, concept_id: UUID | None = None) -> list[LearningEvidenceEvent]:
        self._authorize(actor_user_id, student_id, is_teacher)
        stmt = select(LearningEvidenceEvent).options(selectinload(LearningEvidenceEvent.concepts), selectinload(LearningEvidenceEvent.problem_types)).where(LearningEvidenceEvent.student_id == student_id)
        if assignment_id: stmt = stmt.where(LearningEvidenceEvent.assignment_id == assignment_id)
        if problem_type_id: stmt = stmt.where(LearningEvidenceEvent.problem_types.any(LearningEvidenceProblemType.problem_type_id == problem_type_id))
        if concept_id: stmt = stmt.where(LearningEvidenceEvent.concepts.any(LearningEvidenceConcept.concept_id == concept_id))
        return list(self.session.scalars(stmt.order_by(LearningEvidenceEvent.occurred_at.desc()).limit(limit)))

    def by_assignment(self, actor_user_id: UUID, student_id: UUID, assignment_id: UUID, *, is_teacher: bool, limit: int = 100) -> list[LearningEvidenceEvent]:
        return self.recent_for_student(actor_user_id, student_id, is_teacher=is_teacher, assignment_id=assignment_id, limit=limit)

    def by_problem_type(self, actor_user_id: UUID, student_id: UUID, problem_type_id: UUID, *, is_teacher: bool, limit: int = 100) -> list[LearningEvidenceEvent]:
        return self.recent_for_student(actor_user_id, student_id, is_teacher=is_teacher, problem_type_id=problem_type_id, limit=limit)

    def by_concept(self, actor_user_id: UUID, student_id: UUID, concept_id: UUID, *, is_teacher: bool, limit: int = 100) -> list[LearningEvidenceEvent]:
        return self.recent_for_student(actor_user_id, student_id, is_teacher=is_teacher, concept_id=concept_id, limit=limit)

    def _authorize(self, user_id: UUID, student_id: UUID, is_teacher: bool) -> None:
        student = self.session.get(StudentProfile, student_id)
        if student is None: raise ApplicationError(404, "STUDENT_NOT_FOUND", "Student was not found.")
        if not is_teacher:
            if student.user_id != user_id: raise ApplicationError(403, "EVIDENCE_ACCESS_DENIED", "You cannot access this evidence.")
            return
        teacher = self.session.scalar(select(TeacherProfile).where(TeacherProfile.user_id == user_id))
        allowed = teacher is not None and self.session.scalar(select(StudentEnrollment.student_id).join(TeacherClassroom, TeacherClassroom.classroom_id == StudentEnrollment.classroom_id).where(TeacherClassroom.teacher_id == teacher.id, StudentEnrollment.student_id == student_id, StudentEnrollment.status == EnrollmentStatus.ACTIVE).limit(1)) is not None
        if not allowed: raise ApplicationError(403, "EVIDENCE_ACCESS_DENIED", "Teacher has no classroom relationship with this student.")
