from dataclasses import dataclass

from app.classes.models import EnrollmentStatus
from app.users.models import Role


@dataclass(frozen=True, slots=True)
class SubjectSeed:
    code: str
    name: str
    grade_level: int
    description: str


@dataclass(frozen=True, slots=True)
class ConceptSeed:
    code: str
    name: str
    description: str
    grade_level: int
    order_index: int


@dataclass(frozen=True, slots=True)
class UserSeed:
    code: str
    email: str
    full_name: str
    role: Role


@dataclass(frozen=True, slots=True)
class ClassroomFixture:
    code: str
    name: str
    academic_year: str
    grade_level: int
    teacher_code: str
    enrollments: tuple[tuple[str, EnrollmentStatus], ...]


@dataclass(frozen=True, slots=True)
class ParentLinkFixture:
    parent_code: str
    student_code: str
    relationship_type: str = "GUARDIAN"
