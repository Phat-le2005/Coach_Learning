from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, Enum, ForeignKey, Index, SmallInteger, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base
from app.students.models import StudentProfile
from app.teachers.models import TeacherProfile


class EnrollmentStatus(StrEnum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    COMPLETED = "COMPLETED"


class Classroom(Base):
    __tablename__ = "classrooms"
    __table_args__ = (
        CheckConstraint("length(trim(name)) > 0", name="name_not_blank"),
        CheckConstraint("length(trim(academic_year)) > 0", name="academic_year_not_blank"),
        CheckConstraint("grade_level BETWEEN 1 AND 12", name="grade_level_range"),
        Index("ix_classrooms_created_by", "created_by"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    academic_year: Mapped[str] = mapped_column(String(20), nullable=False)
    grade_level: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    created_by: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    teacher_assignments: Mapped[list["TeacherClassroom"]] = relationship(
        back_populates="classroom", cascade="all, delete-orphan", passive_deletes=True
    )
    student_enrollments: Mapped[list["StudentEnrollment"]] = relationship(
        back_populates="classroom", cascade="all, delete-orphan", passive_deletes=True
    )


class TeacherClassroom(Base):
    __tablename__ = "teacher_classrooms"
    __table_args__ = (
        CheckConstraint("length(trim(role)) > 0", name="role_not_blank"),
        Index("ix_teacher_classrooms_classroom_id", "classroom_id"),
    )

    teacher_id: Mapped[UUID] = mapped_column(
        ForeignKey("teacher_profiles.id", ondelete="CASCADE"), primary_key=True
    )
    classroom_id: Mapped[UUID] = mapped_column(
        ForeignKey("classrooms.id", ondelete="CASCADE"), primary_key=True
    )
    role: Mapped[str] = mapped_column(String(50), nullable=False)

    teacher: Mapped[TeacherProfile] = relationship()
    classroom: Mapped[Classroom] = relationship(back_populates="teacher_assignments")


class StudentEnrollment(Base):
    __tablename__ = "student_enrollments"
    __table_args__ = (
        Index("ix_student_enrollments_classroom_status", "classroom_id", "status", "student_id"),
    )

    student_id: Mapped[UUID] = mapped_column(
        ForeignKey("student_profiles.id", ondelete="CASCADE"), primary_key=True
    )
    classroom_id: Mapped[UUID] = mapped_column(
        ForeignKey("classrooms.id", ondelete="CASCADE"), primary_key=True
    )
    status: Mapped[EnrollmentStatus] = mapped_column(
        Enum(EnrollmentStatus, native_enum=False, create_constraint=True, name="enrollment_status"),
        nullable=False,
        default=EnrollmentStatus.ACTIVE,
        server_default=EnrollmentStatus.ACTIVE.value,
    )
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    student: Mapped[StudentProfile] = relationship()
    classroom: Mapped[Classroom] = relationship(back_populates="student_enrollments")
