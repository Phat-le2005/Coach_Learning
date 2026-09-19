from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, String, Uuid, func, true
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base
from app.students.models import StudentProfile


class ParentProfile(Base):
    __tablename__ = "parent_profiles"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    student_relationships: Mapped[list["ParentStudentRelationship"]] = relationship(
        back_populates="parent", cascade="all, delete-orphan", passive_deletes=True
    )


class ParentStudentRelationship(Base):
    __tablename__ = "parent_student_relationships"
    __table_args__ = (
        CheckConstraint("length(trim(relationship_type)) > 0", name="relationship_type_not_blank"),
    )

    parent_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("parent_profiles.id", ondelete="CASCADE"), primary_key=True
    )
    student_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("student_profiles.id", ondelete="CASCADE"), primary_key=True, index=True
    )
    relationship_type: Mapped[str] = mapped_column(String(50), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=true())

    parent: Mapped[ParentProfile] = relationship(back_populates="student_relationships")
    student: Mapped[StudentProfile] = relationship(back_populates="parent_relationships")
