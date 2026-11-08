"""Map untrusted image step boxes to a complete, disjoint partition of pen ink.

These are reading/boundary proposals only. No answer, rubric, score or database
mutation participates in segmentation. Unusable boxes never erase source ink.
"""
from pydantic import BaseModel, Field, model_validator
from typing import Literal

from app.math_ink.schemas import InkStroke
from app.math_ocr.schemas import OCRStepProposal
from app.math_solutions.schemas import StepKind


class GeminiStepOutput(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    content_kind: Literal["MATH", "TEXT"]
    latex: str = Field(max_length=12000)
    explanation_text: str | None = Field(default=None, max_length=12000)
    suggested_step_type: StepKind
    box_2d: list[int] = Field(min_length=4, max_length=4, description="[ymin,xmin,ymax,xmax] in the supplied image, normalized 0..1000")

    @model_validator(mode="after")
    def validate_content_and_box(self):
        y0, x0, y1, x1 = self.box_2d
        if not (0 <= y0 < y1 <= 1000 and 0 <= x0 < x1 <= 1000):
            raise ValueError("Invalid step box")
        if not (self.latex.strip() or (self.explanation_text or "").strip()):
            raise ValueError("Empty step")
        if self.content_kind == "MATH" and not self.latex.strip():
            raise ValueError("Math step requires a visible formula")
        return self


def map_step_proposals(raw_steps, strokes: list[InkStroke], crop_box: tuple[int, int, int, int]) -> list[OCRStepProposal]:
    if not isinstance(raw_steps, list) or not 1 <= len(raw_steps) <= 24:
        raise ValueError("Missing logical step proposals")
    steps = [GeminiStepOutput.model_validate(step) for step in raw_steps]
    pens = [stroke for stroke in strokes if stroke.tool == "PEN" and stroke.points]
    if len(steps) > len(pens):
        raise ValueError("More proposed steps than source ink")
    left, top, width, height = crop_box
    owners: list[list] = [[] for _ in steps]
    for stroke in pens:
        points = [(1000 * (min(point.x * 794, 793) - left) / width,
                   1000 * (min(point.y * 1123, 1122) - top) / height) for point in stroke.points]
        cx = sum(x for x, _ in points) / len(points)
        cy = sum(y for _, y in points) / len(points)
        def relevance(index):
            y0, x0, y1, x1 = steps[index].box_2d
            inside = sum(x0 <= x <= x1 and y0 <= y <= y1 for x, y in points) / len(points)
            distance = max(x0 - cx, 0, cx - x1)**2 + max(y0 - cy, 0, cy - y1)**2
            center_distance = (cx - (x0+x1)/2)**2 + (cy - (y0+y1)/2)**2
            return inside, -distance, -center_distance
        owners[max(range(len(steps)), key=relevance)].append(stroke.id)
    if any(not ids for ids in owners):
        raise ValueError("A proposed step has no supporting source strokes")
    return [OCRStepProposal(title=step.title, content_kind=step.content_kind,
                latex=step.latex.strip(), explanation_text=(step.explanation_text or "").strip() or None,
                suggested_step_type=step.suggested_step_type, source_stroke_ids=ids)
            for step, ids in zip(steps, owners)]
