"""Preview a private reviewed OCR overlay; --apply explicitly publishes it.

Run from backend: .venv/Scripts/python.exe -B scripts/import_curated_ocr.py --help
The default mode never constructs a database engine or writes import batches.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from uuid import UUID

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.questions.ocr_curated import CuratedOCRImportService, PreparedOCR, prepare_overlay


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--overlay", type=Path, required=True)
    parser.add_argument("--source", action="append", default=[], metavar="DATASET=PATH")
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--actor-id", type=UUID)
    parser.add_argument("--batch-size", type=int, default=200,
                        help="Maximum questions per atomic import transaction (default: 200)")
    parser.add_argument("--add-missing-cubic-catalog", action="store_true",
                        help="Add only missing cubic-profile concepts/outcomes to an existing subject/version")
    parser.add_argument("--add-missing-probability-catalog", action="store_true")
    parser.add_argument("--add-missing-reviewed-catalog", choices=["grouped_statistics", "definite_integral", "polynomial_extrema"], action="append", default=[])
    args = parser.parse_args()
    if not 1 <= args.batch_size <= 1000:
        parser.error("--batch-size must be between 1 and 1000")
    if args.apply and not args.actor_id:
        parser.error("--apply requires an existing active admin --actor-id")
    paths = {}
    for entry in args.source:
        name, separator, path = entry.partition("=")
        if not separator or name in paths:
            parser.error("Each --source must have a unique DATASET=PATH")
        paths[name] = Path(path)
    overlay = json.loads(args.overlay.read_text(encoding="utf-8-sig"))
    prepared = prepare_overlay(overlay, paths)
    report = prepared.report
    if args.apply:
        from app.database.session import get_session_factory
        from app.users.models import User
        report = {**prepared.report, "applied_rows": [], "catalog_additions": [], "batch_size": args.batch_size, "completed_batches": 0}
        # Persist each completed batch report before starting the next transaction;
        # a later rejected batch does not erase the earlier committed audit trail.
        args.report.parent.mkdir(parents=True, exist_ok=True)
        for start in range(0, len(prepared.items), args.batch_size):
            chunk = prepared.items[start:start + args.batch_size]
            with get_session_factory()() as session, session.begin():
                actor = session.get(User, args.actor_id)
                if actor is None:
                    raise ValueError("Import actor does not exist")
                additions = []
                catalogs = {(item.record.subject_code, item.record.curriculum_version_code) for item in chunk}
                for subject, version in sorted(catalogs):
                    if args.add_missing_cubic_catalog or args.add_missing_probability_catalog or args.add_missing_reviewed_catalog:
                        if not version:
                            raise ValueError("An explicit curriculum version is required for catalog additions")
                    if args.add_missing_cubic_catalog:
                        from app.questions.ocr_catalog import add_missing_cubic_catalog
                        additions.append(add_missing_cubic_catalog(session, subject_code=subject, version_code=version))
                    if args.add_missing_probability_catalog:
                        from app.questions.ocr_catalog import add_missing_probability_catalog
                        additions.append(add_missing_probability_catalog(session, subject_code=subject, version_code=version))
                    for family in args.add_missing_reviewed_catalog:
                        from app.questions.ocr_catalog import add_missing_reviewed_catalog
                        additions.append(add_missing_reviewed_catalog(session, subject_code=subject, version_code=version, family=family))
                result = CuratedOCRImportService(session).apply(PreparedOCR(chunk, prepared.report), actor)
            report["applied_rows"].extend(result["applied_rows"])
            report["catalog_additions"].extend(additions)
            report["completed_batches"] += 1
            args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
            print(json.dumps({"batch_completed": report["completed_batches"], "processed": len(report["applied_rows"]),
                              "total": len(prepared.items)}, ensure_ascii=False), flush=True)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"mode": "APPLIED" if args.apply else "OFFLINE_PREVIEW",
                      "ready": report["ready"], "not_selected": report["not_selected"],
                      "report": str(args.report)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
