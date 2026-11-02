"""Re-evaluate cached fallback transcriptions after changing notation checks."""
from __future__ import annotations

import argparse
from pathlib import Path

from .quality import compare_transcriptions, nearby_native_text
from .storage import read_json, write_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pilot", type=Path, required=True)
    args = parser.parse_args()
    prior = read_json(args.pilot / "formula-fallback" / "report.json")
    observations = []
    for region in prior["regions"]:
        number = region["page_number"]
        native = read_json(args.pilot / "pages" / f"page-{number:03}.json")
        result = read_json(args.pilot / "formula-fallback" / f"page-{number:03}.blocks.json")
        block = next(b for b in result["blocks"] if b["block_id"] == region["source_block_id"] + "-fallback-M")
        flags = compare_transcriptions(nearby_native_text(native, block["bbox"]), block["text_raw"])["flags"]
        observations.append({"page_number": number, "block_id": block["block_id"],
                             "previous_flags": region["after_flags"], "current_flags": flags})
    output = {"schema_version": "quality-recheck/v2", "source_sha256": prior["source_sha256"],
              "model_inference_repeated": False, "regions_checked": len(observations),
              "previous_flagged_regions": sum(bool(r["previous_flags"]) for r in observations),
              "current_flagged_regions": sum(bool(r["current_flags"]) for r in observations),
              "regions": observations, "academic_status": "NOT_VERIFIED"}
    write_json(args.pilot / "quality-recheck-v2.json", output)
    print(f"Rechecked {len(observations)} cached regions: {output['previous_flagged_regions']} -> {output['current_flagged_regions']} flagged")


if __name__ == "__main__":
    main()
