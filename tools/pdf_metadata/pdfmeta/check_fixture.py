from __future__ import annotations

import argparse
import json
from pathlib import Path

from .storage import read_json, write_json


def main() -> None:
    parser = argparse.ArgumentParser(description="Check source-specific assertions, separate from generic parser rules")
    parser.add_argument("--pilot", type=Path, required=True)
    parser.add_argument("--fixture", type=Path, required=True)
    args = parser.parse_args()
    fixture = read_json(args.fixture)
    manifest = read_json(args.pilot / "manifest.json")
    items = [json.loads(line) for line in (args.pilot / "questions.candidates.jsonl").read_text(encoding="utf-8").splitlines()]
    failures = []
    if manifest["source_sha256"] != fixture["source_sha256"]:
        raise SystemExit("Wrong source PDF for this fixture")
    if manifest["page_count"] != fixture["expected_page_count"]:
        failures.append("page_count")
    numbers = fixture["expected_source_numbers"]
    if [i["source_number"] for i in items] != list(range(numbers["start"], numbers["end"] + 1)) or len(items) != numbers["count"]:
        failures.append("source_numbers")
    lookup = {item["source_number"]: item for item in items}
    results = []
    for case in fixture["visual_cases"]:
        item = lookup.get(case["number"])
        passed = item is not None
        if item:
            answer = (item["answer"]["text_raw"] or "").rstrip(".。 ")
            passed &= answer == case["source_answer"]
            passed &= sorted({s["page_number"] for s in item["source_regions"]}) == case["source_pages"]
            for name in ("stem", "solution"):
                if case.get(f"{name}_contains"):
                    passed &= case[f"{name}_contains"] in item[name]["text_raw"]
        results.append({"source_number": case["number"], "passed": bool(passed)})
        if not passed:
            failures.append(f"q{case['number']}")
    result = {"status": "PASS" if not failures else "FAIL", "failures": failures,
              "source_sha256": manifest["source_sha256"], "visual_cases": results,
              "scope": fixture["review_scope"], "all_formulas_verified": False}
    write_json(args.pilot / "fixture-result.json", result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
