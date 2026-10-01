from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence

from app.curriculum.final_readiness import (
    DEFAULT_FINAL_READINESS_PATH,
    FinalPreflightComposer,
    FinalReadinessValidator,
)
from app.curriculum.full_scope_alignment import (
    DEFAULT_FULL_SCOPE_ALIGNMENT_PATH,
    REPO_ROOT,
)
from app.curriculum.schema_enrichment import (
    DEFAULT_SCHEMA_ENRICHMENT_PATH,
    SchemaEnrichmentValidator,
)
from app.questions.core_evidence_closure import (
    DEFAULT_CORE_EVIDENCE_CLOSURE_PATH,
    CoreEvidenceClosureValidator,
)
from app.questions.derivative_release_exclusion import (
    DEFAULT_DERIVATIVE_RELEASE_EXCLUSION_PATH,
    DerivativeReleaseExclusionValidator,
)


def validate_all_final_readiness(
    repo_root: Path = REPO_ROOT,
    alignment_path: Path = DEFAULT_FULL_SCOPE_ALIGNMENT_PATH,
    enrichment_path: Path = DEFAULT_SCHEMA_ENRICHMENT_PATH,
    evidence_closure_path: Path = DEFAULT_CORE_EVIDENCE_CLOSURE_PATH,
    exclusion_path: Path = DEFAULT_DERIVATIVE_RELEASE_EXCLUSION_PATH,
    readiness_path: Path = DEFAULT_FINAL_READINESS_PATH,
) -> dict[str, Any]:
    enrichment_report = SchemaEnrichmentValidator().validate(
        enrichment_path=enrichment_path,
        alignment_path=alignment_path,
        repo_root=repo_root,
    )
    evidence_report = CoreEvidenceClosureValidator().validate(
        evidence_path=evidence_closure_path
    )
    exclusion_report = DerivativeReleaseExclusionValidator().validate(
        exclusion_path=exclusion_path
    )
    readiness_report = FinalReadinessValidator().validate(
        readiness_path=readiness_path
    )
    preflight_report = FinalPreflightComposer.run_preflight(
        repo_root=repo_root,
        alignment_path=alignment_path,
        enrichment_path=enrichment_path,
        evidence_closure_path=evidence_closure_path,
        exclusion_path=exclusion_path,
        readiness_path=readiness_path,
    )

    all_passed = (
        enrichment_report.is_valid
        and evidence_report.is_valid
        and exclusion_report.is_valid
        and readiness_report.is_valid
        and preflight_report.is_valid
    )

    return {
        "status": "PASS" if all_passed else "FAIL",
        "datasets": {
            "DATA-MATH12-034": enrichment_report.as_dict(),
            "DATA-MATH12-035": evidence_report.as_dict(),
            "DATA-MATH12-036": exclusion_report.as_dict(),
            "DATA-MATH12-037": readiness_report.as_dict(),
        },
        "preflight": preflight_report.as_dict(),
        "summary": {
            "academic_or_data_blockers_remaining": 0 if all_passed else 1,
            "database_import_allowed": False,
            "canonical_write_allowed": False,
            "production_release_allowed": False,
            "rights_status": "REVIEW_REQUIRED",
            "enriched_fingerprint": preflight_report.fingerprint,
        },
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate DATA-MATH12-034..037 final readiness and execute dry-run schema preflight."
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=REPO_ROOT,
    )
    parser.add_argument(
        "--alignment-path",
        type=Path,
        default=DEFAULT_FULL_SCOPE_ALIGNMENT_PATH,
    )
    parser.add_argument(
        "--enrichment-path",
        type=Path,
        default=DEFAULT_SCHEMA_ENRICHMENT_PATH,
    )
    parser.add_argument(
        "--evidence-closure-path",
        type=Path,
        default=DEFAULT_CORE_EVIDENCE_CLOSURE_PATH,
    )
    parser.add_argument(
        "--exclusion-path",
        type=Path,
        default=DEFAULT_DERIVATIVE_RELEASE_EXCLUSION_PATH,
    )
    parser.add_argument(
        "--readiness-path",
        type=Path,
        default=DEFAULT_FINAL_READINESS_PATH,
    )
    args = parser.parse_args(argv)

    results = validate_all_final_readiness(
        repo_root=args.repo_root,
        alignment_path=args.alignment_path,
        enrichment_path=args.enrichment_path,
        evidence_closure_path=args.evidence_closure_path,
        exclusion_path=args.exclusion_path,
        readiness_path=args.readiness_path,
    )

    print(json.dumps(results, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if results["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
