from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.theory_maps.models import TheoryMapStatus


class NodeKind(StrEnum):
    ROOT = "ROOT"
    SECTION = "SECTION"
    CONCEPT = "CONCEPT"
    FORMULA = "FORMULA"
    EXAMPLE = "EXAMPLE"
    NOTE = "NOTE"
    METHOD = "METHOD"
    QUICK_TRICK = "QUICK_TRICK"


class TheoryLearningStep(BaseModel):
    model_config = ConfigDict(extra="forbid")
    instruction: str = Field(min_length=1, max_length=500)
    latex: str | None = Field(default=None, max_length=1000)
    source_page: int | None = Field(default=None, ge=1)
    source_quote: str | None = Field(default=None, min_length=1, max_length=500)


class TheoryNode(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1, max_length=40, pattern=r"^[a-zA-Z0-9_-]+$")
    parent_id: str | None = None
    kind: NodeKind
    title: str = Field(min_length=1, max_length=250)
    body: str = Field(default="", max_length=2000)
    latex: str | None = Field(default=None, max_length=1000)
    learning_steps: list[TheoryLearningStep] = Field(default_factory=list, max_length=12)
    source_page: int = Field(ge=1)
    source_quote: str = Field(min_length=1, max_length=500)
    reviewed: bool = False
    block_id: str | None = None
    bounding_box: dict[str, float] | None = None
    origin: str | None = None


class TheoryMapWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(ge=1)
    nodes: list[TheoryNode] = Field(min_length=1, max_length=500)


class TheoryMapSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    classroom_id: UUID
    subject_id: UUID
    title: str
    file_name: str
    sha256: str
    page_count: int
    status: TheoryMapStatus
    revision: int
    source_available: bool


class TheoryMapRead(TheoryMapSummary):
    nodes: list[TheoryNode]
    ai_model: str | None
    extraction_warning_pages: list[int]
    source_outline: list[dict[str, str | int]] = Field(default_factory=list)


