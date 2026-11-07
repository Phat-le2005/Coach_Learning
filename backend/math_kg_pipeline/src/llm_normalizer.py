"""Optional LLM normalization for heuristic recognition output."""
import json
import os
from urllib import request
from urllib.parse import quote

from .config import GEMINI_API_KEY, GEMINI_MODEL


def _json_object(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    value = json.loads(text)
    if not isinstance(value, dict):
        raise ValueError("LLM response must be a JSON object")
    return value


def normalize_question(question: dict) -> dict:
    api_key = GEMINI_API_KEY
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is required to enable LLM normalization")

    endpoint = os.getenv(
        "GEMINI_API_URL",
        "https://generativelanguage.googleapis.com/v1beta/models",
    )
    prompt = {
        "question_id": question["question_id"],
        "question_text": question["question_text"],
        "solution_text": question["solution_text"],
        "solution_steps": question["solution_steps"],
        "source_pages": question["pages"],
        "math_elements": question.get("math_elements", []),
    }
    instruction = (
        "Normalize Vietnamese math exercise data. Return JSON only with "
        "question_text, solution_text, solution_steps, math_elements, needs_review. "
        "Never invent missing math or image data. Preserve uncertainty "
        "by setting needs_review=true.\n\n"
        + json.dumps(prompt, ensure_ascii=False)
    )
    body = {
        "contents": [{"parts": [{"text": instruction}]}],
        "generationConfig": {
            "temperature": 0,
            "responseMimeType": "application/json",
        },
    }
    req = request.Request(
        f"{endpoint}/{quote(GEMINI_MODEL, safe='')}:generateContent"
        f"?key={quote(api_key, safe='')}",
        data=json.dumps(body, ensure_ascii=False).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with request.urlopen(req, timeout=120) as response:
        result = json.loads(response.read())
    content = result["candidates"][0]["content"]["parts"][0]["text"]
    normalized = _json_object(content)
    for field in (
        "question_text", "solution_text", "solution_steps",
        "math_elements", "needs_review",
    ):
        if field not in normalized:
            raise ValueError(f"LLM response is missing field: {field}")
    if not isinstance(normalized["solution_steps"], list):
        raise ValueError("LLM solution_steps must be a list")
    if not isinstance(normalized["math_elements"], list):
        raise ValueError("LLM math_elements must be a list")
    return {
        **question,
        "question_text": str(normalized["question_text"]).strip(),
        "solution_text": str(normalized["solution_text"]).strip(),
        "solution_steps": normalized["solution_steps"],
        "math_elements": normalized["math_elements"],
        "needs_review": bool(normalized["needs_review"]),
        "normalization": "llm",
    }
