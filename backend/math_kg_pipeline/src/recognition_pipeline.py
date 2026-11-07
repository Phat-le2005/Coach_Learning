"""Chạy các bước nhận diện sau khi trích xuất PDF."""
import json
from pathlib import Path

from .extract_pdf import extract_pages
from .parser import parse_document
from .recognize import (
    clean_text,
    extract_math_elements,
    split_solution_steps,
    detect_math_regions,
    extract_pdf_image_blocks,
)
from .latex_figures import crop_page_region, image_to_latex
from .llm_normalizer import normalize_question
from .config import GEMINI_API_KEY

def run_recognition(pdf_path: str, output_dir: str):
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    pages = extract_pages(pdf_path)
    for page in pages:
        page["text"] = clean_text(page["text"])
    questions = parse_document(pages)

    for question in questions:
        question["question_text"] = clean_text(question["question_text"])
        question["solution_text"] = clean_text(question["solution_text"])
        question["solution_steps"] = split_solution_steps(question.get("solution_text", ""))
        question["math_elements"] = extract_math_elements(
            question["question_text"] + "\n" + question["solution_text"]
        )

    regions = []
    for page in pages:
        regions.extend(detect_math_regions(page))

    image_blocks = extract_pdf_image_blocks(pdf_path)
    figures_dir = out / "figures"
    for image in image_blocks:
        crop_path = figures_dir / f"{image['image_id']}.png"
        image["crop_path"] = crop_page_region(
            pdf_path, image["page"], tuple(image["bbox"]), str(crop_path)
        )
        image["latex_candidate"] = image_to_latex(
            image["crop_path"], f"PDF figure {image['image_id']}"
        )
        image["kind"] = "figure_or_graph_crop"

    payload = {
        "pages": pages,
        "questions": questions,
        "math_regions": regions,
        "image_blocks": image_blocks,
        "pipeline_status": "heuristic_candidates_require_review",
    }
    (out / "recognition.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    if GEMINI_API_KEY:
        payload["questions"] = [normalize_question(q) for q in questions]
        payload["pipeline_status"] = "llm_normalized_requires_review"
        (out / "final.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    return payload
