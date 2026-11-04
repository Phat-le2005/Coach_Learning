"""Static local inspection of model proposals and the exact images sent to Gemini."""
from __future__ import annotations

import json
from pathlib import Path
import shutil


def build_view(output: Path, records: list[dict], report: dict):
    katex = Path(__file__).parents[3] / "frontend" / "node_modules" / "katex" / "dist"
    target = output / "review-assets" / "katex"
    if katex.exists() and not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(katex, target)
    payload = json.dumps({"records": records, "report": report}, ensure_ascii=False).replace("<", "\\u003c")
    (output / "review.html").write_text(Path(__file__).with_name("gemini_review.html").read_text(encoding="utf-8").replace("__PAYLOAD__", payload), encoding="utf-8")
