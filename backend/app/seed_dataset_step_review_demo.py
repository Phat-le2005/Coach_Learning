"""Install PDF Example 7 as an isolated local OCR/step-review question.

Run ``python -m app.seed_dataset_step_review_demo`` from backend. Example 7
is on PDF page 5 of the same source as the 200-record draft; it is not a
selected record in that draft. Source files and publication flags stay intact.
The sample has no curriculum mappings or rubric. Normal practice cannot pick
it and AI feedback remains provisional.
"""

import argparse
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import re
from uuid import UUID
from zipfile import ZipFile

from pypdf import PdfReader

from app.core.config import BACKEND_DIR, get_settings
from app.database.session import get_session_factory
from app.questions.models import Question, QuestionStatus, QuestionType
from app.seed_step_review_demo import DEMO_CONTENT_MARKER, DEMO_QUESTION_ID

QUESTION_ID = UUID("c0000000-0000-0000-0000-000000000002")
# This selected record establishes the PDF lineage, not an Example 7 record ID.
SOURCE_ANCHOR_ID = "a287830565130826:q8:n8"
DATASET_SHA256 = "fd37836351a2adcc059fe0cff52d5afd8ac6656a2b5805492243ec3abb644c4d"
PDF_SHA256 = "a287830565130826c0f48c8c43ffa3dcef4b6c57477e8621650800506fe72e56"
CONTENT = r"Ví dụ 7. Chứng minh rằng hàm số $g(x)=\frac{x}{x-1}$ nghịch biến trên khoảng $(1;+\infty)$."
ANSWER = r"Hàm số $g(x)=\frac{x}{x-1}$ nghịch biến trên khoảng $(1;+\infty)$."
EXPLANATION = (
    "Đối chiếu Ví dụ 7, trang PDF 5 của tài liệu gốc.\n"
    "Bước 1: Hàm số xác định và có đạo hàm trên khoảng (1;+∞).\n"
    "Bước 2: g'(x)=((x-1)-x)/(x-1)²=-1/(x-1)²<0 với mọi x>1.\n"
    "Bước 3: Vậy g(x) nghịch biến trên khoảng (1;+∞)."
)


def load_source(dataset_file: Path, sources_zip: Path) -> tuple[str, str]:
    data = dataset_file.read_bytes()
    if sha256(data).hexdigest() != DATASET_SHA256:
        raise RuntimeError("Dataset hash changed; check the source again before installation.")
    rows = json.loads(data.decode("utf-8-sig"))
    selected = [row for row in rows if row.get("question_id") == SOURCE_ANCHOR_ID]
    if len(selected) != 1:
        raise RuntimeError("The PDF source anchor is missing or duplicated.")
    source = selected[0]["source"]
    if source["sha256"] != PDF_SHA256:
        raise RuntimeError("The source PDF identity changed.")
    with ZipFile(sources_zip) as archive:
        pdf = archive.read(source["catalog_label"])
    if sha256(pdf).hexdigest() != PDF_SHA256:
        raise RuntimeError("The local PDF does not match the supplied dataset.")
    page = PdfReader(BytesIO(pdf)).pages[4].extract_text()
    if not re.search(r"Ví\s+dụ\s+7\.", page):
        raise RuntimeError("Example 7 was not found on the checked source page.")
    reference = f"DEV_ONLY | PDF Example 7 | {source['name']} | PDF p.5 | sha256:{PDF_SHA256}"
    return CONTENT, reference


def install(dataset_file: Path | None = None, sources_zip: Path | None = None) -> str:
    if get_settings().app_env not in {"development", "test"}:
        raise RuntimeError("Development sample is disabled in production.")
    content, reference = load_source(
        dataset_file or BACKEND_DIR / "data" / "content.draft.pretty.json",
        sources_zip or BACKEND_DIR.parent / "Toan12.zip",
    )
    with get_session_factory()() as session:
        base = session.get(Question, DEMO_QUESTION_ID)
        if (base is None or base.source_type != "SAMPLE_TEST"
                or base.question_type != QuestionType.OPEN_RESPONSE
                or base.status != QuestionStatus.APPROVED
                or DEMO_CONTENT_MARKER not in base.content):
            raise RuntimeError("The expected existing development sample is missing or changed.")
        expected = dict(
            subject_id=base.subject_id, content=content,
            question_type=QuestionType.OPEN_RESPONSE,
            # Technical local-test defaults, not academic difficulty/exam labels.
            difficulty=0.5, exam_weight=0.0,
            correct_answer=ANSWER, explanation=EXPLANATION,
            source_type="SAMPLE_TEST", source_reference=reference,
            status=QuestionStatus.APPROVED, created_by=base.created_by,
        )
        existing = session.get(Question, QUESTION_ID)
        if existing is not None:
            if (any(getattr(existing, field) != value for field, value in expected.items())
                    or existing.concept_links or existing.problem_type_links or existing.learning_outcome_links):
                raise RuntimeError("The sample ID contains different data; nothing was overwritten.")
            return "already_installed"
        session.add(Question(id=QUESTION_ID, **expected))
        session.commit()
        return "installed"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-file", type=Path)
    parser.add_argument("--sources-zip", type=Path)
    args = parser.parse_args()
    print(f"dataset_step_review_demo: {install(args.dataset_file, args.sources_zip)} ({QUESTION_ID})")
