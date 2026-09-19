"""Import every mapped class so SQLAlchemy can resolve string relationships.

Command-line entry points do not load FastAPI routers, so they must not rely on
router imports to populate the declarative registry.
"""

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
from app.parents.models import ParentProfile, ParentStudentRelationship
from app.mastery.models import StudentConceptMastery, StudentProblemTypeMastery
from app.practice.models import (
    PracticeSession,
    PracticeSessionConcept,
    PracticeSessionProblemType,
    QuestionAttempt,
)
from app.questions.models import (
    Question,
    QuestionConcept,
    QuestionImportBatch,
    QuestionImportRow,
    QuestionLearningOutcome,
    QuestionOption,
    QuestionProblemType,
)
from app.students.models import AcademicGoal, AcademicGoalStatus, StudentProfile, SubjectGoal
from app.subjects.models import Subject
from app.teachers.models import TeacherProfile
from app.users.models import User

__all__ = [
    "AcademicGoal",
    "AcademicGoalStatus",
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
    "LearningOutcome",
    "StudentConceptMastery",
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
    "QuestionAttempt",
    "QuestionConcept",
    "QuestionImportBatch",
    "QuestionImportRow",
    "QuestionLearningOutcome",
    "QuestionOption",
    "QuestionProblemType",
    "RefreshToken",
    "StudentAttempt",
    "StudentEnrollment",
    "StudentProfile",
    "StudySession",
    "Subject",
    "SubjectGoal",
    "TeacherClassroom",
    "TeacherProfile",
    "Topic",
    "User",
]
