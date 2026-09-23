from __future__ import annotations

import json
from pathlib import Path

from app.evaluate.schemas import FullEvaluationReport


class JSONReporter:
    """Serializes FullEvaluationReport to structured JSON."""

    @staticmethod
    def write_report(report: FullEvaluationReport, output_path: Path | str) -> Path:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as f:
            json.dump(report.model_dump(), f, ensure_ascii=False, indent=2)
        return path
