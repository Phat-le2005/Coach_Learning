from __future__ import annotations

import argparse
from pathlib import Path
import sys

from .storage import configure_storage, write_json, write_jsonl


def main() -> int:
    parser = argparse.ArgumentParser(description="Offline PDF-to-metadata pilot; no database writes")
    parser.add_argument("--pdf", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--runtime", type=Path, required=True, help="All model, package and temp caches live here")
    parser.add_argument("--dpi", type=int, default=120)
    args = parser.parse_args()
    if not args.pdf.is_file() or args.pdf.suffix.lower() != ".pdf":
        parser.error("--pdf must name an existing PDF")
    if not 72 <= args.dpi <= 240:
        parser.error("--dpi must be between 72 and 240")
    caches = configure_storage(args.runtime)
    from .native import extract_native
    from .assemble import assemble
    from .review import build_review, crop_sources
    from .validate import validate_candidates

    manifest, pages = extract_native(args.pdf, args.output, dpi=args.dpi)
    items, orphans = assemble(pages, manifest["source_sha256"])
    crop_sources(items, pages, args.output)
    report = validate_candidates(items, pages, args.output)
    report["source_sha256"] = manifest["source_sha256"]
    report["orphan_block_count"] = len(orphans)
    report["storage"] = caches
    write_jsonl(args.output / "questions.candidates.jsonl", items)
    write_jsonl(args.output / "unassigned-blocks.jsonl", orphans)
    write_json(args.output / "report.json", report)
    build_review(items, report, args.output)
    print(f"{report['structural_status']}: {len(items)} candidates; {report['answers_found']} answers; {len(report['structural_errors'])} structural errors")
    print(f"Review: {(args.output / 'review.html').resolve()}")
    return 0 if report["structural_status"] == "PASS" else 2


if __name__ == "__main__":
    sys.exit(main())
