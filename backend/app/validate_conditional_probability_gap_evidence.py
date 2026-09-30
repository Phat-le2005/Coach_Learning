from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from app.questions.conditional_probability_gap_evidence import (
    DEFAULT_CONDITIONAL_PROBABILITY_GAP_EVIDENCE_PATH,
    ConditionalProbabilityGapEvidenceValidator,
)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate curated DATA-MATH12-030 conditional probability gap evidence."
    )
    parser.add_argument(
        "--evidence-path",
        type=Path,
        default=DEFAULT_CONDITIONAL_PROBABILITY_GAP_EVIDENCE_PATH,
    )
    args = parser.parse_args(argv)
    report = ConditionalProbabilityGapEvidenceValidator().validate(args.evidence_path)
    print(json.dumps(report.as_dict(), ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report.is_valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
