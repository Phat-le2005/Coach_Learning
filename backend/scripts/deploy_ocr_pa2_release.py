"""Build a private 345-question bundle, or install it with the additive knowledge tree.

Build needs the authoritative source files; deploying the bundle does not.
Default execution is read-only validation. --apply writes the configured dev DB.
"""
import argparse
import json
from pathlib import Path
import sys
from uuid import UUID

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.questions.ocr_curated import CuratedOCRImportService, prepare_overlay
from app.questions.ocr_release import build_release, prepare_release


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--build-overlay", type=Path, action="append", default=[])
    parser.add_argument("--source", action="append", default=[], metavar="DATASET=PATH")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--actor-id", type=UUID)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    if args.build_overlay:
        sources = {}
        for value in args.source:
            name, separator, path = value.partition("=")
            if not separator or name in sources:
                parser.error("Expected unique --source DATASET=PATH")
            sources[name] = Path(path)
        prepared = [prepare_overlay(json.loads(p.read_text(encoding="utf-8-sig")), sources) for p in args.build_overlay]
        release = build_release(prepared)
        args.bundle.parent.mkdir(parents=True, exist_ok=True)
        args.bundle.write_text(json.dumps(release, ensure_ascii=False, indent=2), encoding="utf-8")
    release = json.loads(args.bundle.read_text(encoding="utf-8-sig"))
    prepared = prepare_release(release)
    report = {**prepared.report, "mode": "OFFLINE_VALIDATION"}
    if args.apply:
        from sqlalchemy import select
        from app.core.config import get_settings
        from app.curriculum.ocr_pa2_tree import ensure_ocr_pa2_tree
        from app.database.session import get_session_factory
        from app.questions.ocr_catalog import add_missing_cubic_catalog, add_missing_probability_catalog
        from app.users.models import Role, User
        settings = get_settings()
        with get_session_factory()() as session, session.begin():
            if args.actor_id:
                actor = session.get(User, args.actor_id)
            else:
                # Local CLI only; do not create an account or export credentials.
                actor = session.scalar(select(User).where(User.role == Role.ADMIN, User.is_active.is_(True)).order_by(User.id))
            if actor is None or not actor.is_active or actor.role != Role.ADMIN:
                raise ValueError("An existing active administrator is required")
            tree = ensure_ocr_pa2_tree(session, app_env=settings.app_env)
            subject = prepared.items[0].record.subject_code
            version = prepared.items[0].record.curriculum_version_code
            add_missing_cubic_catalog(session, subject_code=subject, version_code=version)
            add_missing_probability_catalog(session, subject_code=subject, version_code=version)
            report = {**CuratedOCRImportService(session).apply(prepared, actor), "tree": tree, "mode": "APPLIED"}
        # The complete tree and all questions/rubrics commit in one transaction.
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    from collections import Counter
    print(json.dumps({"mode": report["mode"], "questions": report["ready"],
                      "question_dispositions": dict(Counter(r["status"] for r in report.get("applied_rows", []))),
                      "tree": report.get("tree"), "report": str(args.report)}, ensure_ascii=True))


if __name__ == "__main__":
    main()
