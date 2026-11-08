"""Public image references shared by question previews and assigned work."""
import re
from typing import Literal

from pydantic import BaseModel, Field


class QuestionVisualRead(BaseModel):
    index: int = Field(ge=0)
    path: str
    url: str
    role: Literal["question", "answer", "solution"] = "question"


def markdown_image_paths(content: str) -> set[str]:
    return {
        (angle or plain).removeprefix("./")
        for angle, plain in re.findall(r"!\[[^\]\n]*\]\(\s*(?:<([^>\n]+)>|([^\s)]+))\s*\)", content)
    }
