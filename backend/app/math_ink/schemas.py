"""Strict bounds protect API workers and storage from unbounded pen events."""
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class InkPoint(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    x: float = Field(ge=0, le=1, allow_inf_nan=False)
    y: float = Field(ge=0, le=1, allow_inf_nan=False)
    pressure: float = Field(default=0.5, ge=0, le=1, allow_inf_nan=False)


class InkStroke(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    id: UUID
    tool: Literal["PEN", "HIGHLIGHTER"]
    color: str = Field(pattern=r"^#[0-9a-fA-F]{6}$")
    width: float = Field(ge=0.25, le=24, allow_inf_nan=False)
    points: list[InkPoint] = Field(min_length=1, max_length=3000)


class InkPageWrite(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    expected_document_revision: int = Field(ge=0)
    client_action_id: UUID
    strokes: list[InkStroke] = Field(max_length=400)

    @field_validator("strokes")
    @classmethod
    def unique_strokes(cls, value: list[InkStroke]) -> list[InkStroke]:
        if len({stroke.id for stroke in value}) != len(value):
            raise ValueError("Duplicate stroke IDs")
        if sum(len(stroke.points) for stroke in value) > 15000:
            raise ValueError("Too many points on one page")
        return value


class InkPageSummary(BaseModel):
    page_index: int
    stroke_count: int
    point_count: int
    sha256: str


class InkDocumentRead(BaseModel):
    document_revision: int
    pages: list[InkPageSummary]


class InkPageRead(BaseModel):
    document_revision: int
    page_index: int
    strokes: list[InkStroke]


class InkSaveRead(BaseModel):
    document_revision: int
    page_index: int
    sha256: str
