from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, Enum, ForeignKey, Index, Integer, SmallInteger, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class RelationType(StrEnum):
    PREREQUISITE = "PREREQUISITE"
    PART_OF = "PART_OF"
    RELATED_TO = "RELATED_TO"


class Concept(Base):
    __tablename__ = "concepts"
    __table_args__ = (
        UniqueConstraint("subject_id", "code", name="uq_concepts_subject_code"),
        CheckConstraint("code = upper(trim(code)) AND length(code) > 0", name="code_normalized"),
        CheckConstraint("length(trim(name)) > 0", name="name_not_blank"),
        CheckConstraint("description IS NULL OR length(trim(description)) > 0", name="description_not_blank"),
        CheckConstraint("grade_level IS NULL OR grade_level BETWEEN 1 AND 12", name="grade_level_range"),
        CheckConstraint("order_index IS NULL OR order_index >= 0", name="order_index_nonnegative"),
        Index("ix_concepts_subject_order", "subject_id", "order_index", "code"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    subject_id: Mapped[UUID] = mapped_column(ForeignKey("subjects.id", ondelete="RESTRICT"), nullable=False)
    code: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    grade_level: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    order_index: Mapped[int | None] = mapped_column(Integer, nullable=True)


class ConceptRelation(Base):
    __tablename__ = "concept_relations"
    __table_args__ = (
        UniqueConstraint("source_concept_id", "target_concept_id", "relation_type", name="uq_concept_relations_edge"),
        CheckConstraint("source_concept_id <> target_concept_id", name="no_self_relation"),
        CheckConstraint("relation_type <> 'RELATED_TO' OR source_concept_id < target_concept_id", name="related_canonical_order"),
        Index("ix_concept_relations_type_source", "relation_type", "source_concept_id"),
        Index("ix_concept_relations_type_target", "relation_type", "target_concept_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    source_concept_id: Mapped[UUID] = mapped_column(ForeignKey("concepts.id", ondelete="RESTRICT"), nullable=False)
    target_concept_id: Mapped[UUID] = mapped_column(ForeignKey("concepts.id", ondelete="RESTRICT"), nullable=False)
    relation_type: Mapped[RelationType] = mapped_column(
        Enum(RelationType, native_enum=False, create_constraint=True, name="concept_relation_type"), nullable=False
    )
