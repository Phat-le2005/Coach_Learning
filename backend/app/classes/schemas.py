from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.classes.models import EnrollmentStatus
from app.students.models import SyntheticProfile


class ClassroomCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, hide_input_in_errors=True)

    name: str = Field(min_length=1, max_length=200)
    academic_year: str = Field(min_length=1, max_length=20)
    grade_level: int = Field(ge=1, le=12, strict=True)


class ClassroomRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    academic_year: str
    grade_level: int
    created_by: UUID
    created_at: datetime


class TeacherClassroomRead(ClassroomRead):
    teacher_role: str


class StudentClassroomRead(ClassroomRead):
    enrollment_status: EnrollmentStatus
    joined_at: datetime


class StudentEnrollmentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    student_id: UUID
    status: EnrollmentStatus = EnrollmentStatus.ACTIVE


class ClassroomStudentRead(BaseModel):
    student_id: UUID
    user_id: UUID
    email: EmailStr
    full_name: str
    grade_level: int
    school_name: str | None
    date_of_birth: date | None
    is_synthetic: bool
    synthetic_profile: SyntheticProfile | None
    status: EnrollmentStatus
    joined_at: datetime
