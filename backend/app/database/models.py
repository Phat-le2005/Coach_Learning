"""Import every mapped class so SQLAlchemy can resolve string relationships.

Command-line entry points do not load FastAPI routers, so they must not rely on
router imports to populate the declarative registry.
"""

from app.admission.models import (
    AdmissionDataSource,
    AdmissionImportFormat,
    AdmissionImportHistory,
    AdmissionImportStatus,
    AdmissionMethod,
    AdmissionRule,
    AdmissionTarget,
    AdmissionTargetType,
    Major,
    University,
)
from app.ai.models import AIRequestLog
from app.assignments.models import (
    Assignment,
    AssignmentConcept,
    AssignmentLearningObjective,
    AssignmentProblemType,
    AssignmentQuestion,
    AssignmentStudentQuestion,
    StudentAssignment,
)
from app.attempts.models import StudentAttempt, StudySession
from app.auth.models import AuthSession, RefreshToken
from app.classes.models import Classroom, StudentEnrollment, TeacherClassroom
from app.concepts.models import Concept, ConceptRelation
from app.curriculum.models import (
    Chapter,
    Curriculum,
    CurriculumImportHistory,
    CurriculumVersion,
    LearningOutcome,
    ProblemType,
    ProblemTypeConcept,
    ProblemTypeLearningOutcome,
    Topic,
)
from app.diagnostics.models import (
    DiagnosticAssessment,
    DiagnosticAttemptContext,
    DiagnosticBlueprintItem,
)
from app.exams.models import (
    Exam,
    ExamAttempt,
    ExamAttemptStatus,
    ExamQuestion,
    ExamResponse,
    ExamSection,
    ExamStatus,
    ExamType,
)
from app.hints.models import PracticeQuestionHint, QuestionHint
from app.parents.models import ParentProfile, ParentStudentRelationship
from app.mastery.models import StudentConceptMastery, StudentProblemTypeMastery
from app.misconceptions.models import MisconceptionDefinition, StudentMisconception
from app.practice.models import (
    PracticeSession,
    PracticeSessionConcept,
    PracticeSessionProblemType,
    QuestionAttempt,
    QuestionGroupAttempt,
    QuestionGroupAttemptItem,
)
from app.questions.models import (
    Question,
    QuestionConcept,
    QuestionGroup,
    QuestionGroupItem,
    QuestionImportBatch,
    QuestionImportRow,
    QuestionLearningOutcome,
    QuestionOption,
    QuestionProblemType,
)
from app.learning.models import (
    ConceptSignalLevel,
    QuickCheckQuestion,
    QuickCheckQuestionRole,
    QuickCheckSession,
    QuickCheckVerdict,
)
from app.planning.models import (
    StudyPlan,
    StudyPlanStatus,
    StudyTask,
    StudyTaskReasonCode,
    StudyTaskStatus,
    StudyTaskType,
    TeachingPlan,
    TeachingPlanItem,
    TeachingPlanStatus,
)
from app.review.models import ReviewResult, ReviewSchedule
from app.students.models import AcademicGoal, AcademicGoalStatus, StudentProfile, SubjectGoal
from app.subjects.models import Subject
from app.teachers.models import TeacherProfile
from app.rag.models import Document, DocumentChunk, DocumentSourceType, DocumentStatus
from app.tutor.models import (
    LearningMemoryType,
    StudentLearningMemory,
    TutorSession,
    TutorSessionStatus,
    TutorSessionSummary,
)
from app.users.models import User

__all__ = [
    "AcademicGoal",
    "AcademicGoalStatus",
    "AdmissionDataSource",
    "AdmissionMethod",
    "AdmissionRule",
    "AdmissionTarget",
    "AdmissionTargetType",
    "AIRequestLog",
    "Assignment",
    "AssignmentConcept",
    "AssignmentLearningObjective",
    "AssignmentProblemType",
    "AssignmentQuestion",
    "AssignmentStudentQuestion",
    "AuthSession",
    "Chapter",
    "Classroom",
    "Concept",
    "ConceptRelation",
    "Curriculum",
    "CurriculumImportHistory",
    "CurriculumVersion",
    "DiagnosticAssessment",
    "DiagnosticAttemptContext",
    "DiagnosticBlueprintItem",
    "Document",
    "DocumentChunk",
    "DocumentSourceType",
    "DocumentStatus",
    "Exam",
    "ExamAttempt",
    "ExamAttemptStatus",
    "ExamQuestion",
    "ExamResponse",
    "ExamSection",
    "ExamStatus",
    "ExamType",
    "LearningOutcome",
    "Major",
    "MisconceptionDefinition",
    "PracticeQuestionHint",
    "StudentConceptMastery",
    "StudentMisconception",
    "StudentProblemTypeMastery",
    "ParentProfile",
    "ParentStudentRelationship",
    "PracticeSession",
    "PracticeSessionConcept",
    "PracticeSessionProblemType",
    "ProblemType",
    "ProblemTypeConcept",
    "ProblemTypeLearningOutcome",
    "Question",
    "QuestionHint",
    "QuestionAttempt",
    "QuestionGroupAttempt",
    "QuestionGroupAttemptItem",
    "QuestionConcept",
    "QuestionGroup",
    "QuestionGroupItem",
    "QuestionImportBatch",
    "QuestionImportRow",
    "QuestionLearningOutcome",
    "QuestionOption",
    "QuestionProblemType",
    "QuickCheckQuestion",
    "QuickCheckQuestionRole",
    "QuickCheckSession",
    "QuickCheckVerdict",
    "RefreshToken",
    "ReviewResult",
    "ReviewSchedule",
    "StudentAssignment",
    "StudentAttempt",
    "StudentEnrollment",
    "StudentLearningMemory",
    "StudentProfile",
    "StudyPlan",
    "StudyPlanStatus",
    "StudySession",
    "StudyTask",
    "StudyTaskReasonCode",
    "StudyTaskStatus",
    "StudyTaskType",
    "Subject",
    "SubjectGoal",
    "TeacherClassroom",
    "TeacherProfile",
    "TeachingPlan",
    "TeachingPlanItem",
    "TeachingPlanStatus",
    "Topic",
    "TutorSession",
    "TutorSessionStatus",
    "TutorSessionSummary",
    "LearningMemoryType",
    "University",
    "User",
]
