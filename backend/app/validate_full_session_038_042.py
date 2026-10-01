from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Sequence

from app.curriculum.canonical_snapshot_candidate import (
    DEFAULT_CANDIDATE_PATH,
    DEFAULT_SNAPSHOT_DIR,
    ROOT_CANONICAL_PATH,
    CanonicalSnapshotCandidateGenerator,
    CanonicalSnapshotCandidateValidator,
)
from app.curriculum.diagnostic_graph import (
    DEFAULT_DIAGNOSTIC_GRAPH_PATH,
    DiagnosticGraphValidator,
)
from app.curriculum.full_scope_alignment import (
    DEFAULT_FULL_SCOPE_ALIGNMENT_PATH,
    REPO_ROOT,
)
from app.curriculum.production_gate import (
    DEFAULT_PRODUCTION_GATE_PATH,
    WORKFLOW_FILE_PATH,
    ProductionGateValidator,
)
from app.curriculum.schema_enrichment import DEFAULT_SCHEMA_ENRICHMENT_PATH
from app.questions.depth_correction_overlay import (
    BASE_DERIVATIVE_GROUPS_PATH,
    BASE_OXYZ_DATA_PATH,
    BASE_PROBABILITY_DATA_PATH,
    DEFAULT_DEPTH_CORRECTION_PATH,
    DepthCorrectionOverlayValidator,
)
from app.questions.quality_audit import (
    DEFAULT_QUALITY_AUDIT_PATH,
    QualityAuditValidator,
)


def validate_full_session_038_042(
    *,
    candidate_path: Path = DEFAULT_CANDIDATE_PATH,
    snapshot_dir: Path = DEFAULT_SNAPSHOT_DIR,
    root_canonical_path: Path = ROOT_CANONICAL_PATH,
    alignment_path: Path = DEFAULT_FULL_SCOPE_ALIGNMENT_PATH,
    enrichment_path: Path = DEFAULT_SCHEMA_ENRICHMENT_PATH,
    repo_root: Path = REPO_ROOT,
    depth_correction_path: Path = DEFAULT_DEPTH_CORRECTION_PATH,
    base_probability_path: Path = BASE_PROBABILITY_DATA_PATH,
    base_derivative_groups_path: Path = BASE_DERIVATIVE_GROUPS_PATH,
    base_oxyz_path: Path = BASE_OXYZ_DATA_PATH,
    diagnostic_graph_path: Path = DEFAULT_DIAGNOSTIC_GRAPH_PATH,
    quality_audit_path: Path = DEFAULT_QUALITY_AUDIT_PATH,
    production_gate_path: Path = DEFAULT_PRODUCTION_GATE_PATH,
    workflow_path: Path = WORKFLOW_FILE_PATH,
    auto_generate_snapshot: bool = True,
) -> dict[str, Any]:
    # Ensure candidate snapshot exists before validation if requested
    generation_result = None
    if auto_generate_snapshot and not (snapshot_dir / "manifest.json").is_file():
        generation_result = CanonicalSnapshotCandidateGenerator.generate(
            target_dir=snapshot_dir,
            alignment_path=alignment_path,
            enrichment_path=enrichment_path,
            repo_root=repo_root,
            root_canonical_path=root_canonical_path,
        )

    # 1. DATA-MATH12-038
    snap_report = CanonicalSnapshotCandidateValidator().validate(
        candidate_path=candidate_path,
        snapshot_dir=snapshot_dir,
        root_canonical_path=root_canonical_path,
        alignment_path=alignment_path,
        enrichment_path=enrichment_path,
        repo_root=repo_root,
    )

    # 2. DATA-MATH12-039
    depth_report = DepthCorrectionOverlayValidator().validate(
        dataset_path=depth_correction_path,
        base_probability_path=base_probability_path,
        base_derivative_groups_path=base_derivative_groups_path,
        base_oxyz_path=base_oxyz_path,
    )

    # 3. DATA-MATH12-040
    diag_report = DiagnosticGraphValidator().validate(
        dataset_path=diagnostic_graph_path,
        snapshot_dir=snapshot_dir,
    )

    # 4. DATA-MATH12-041
    qa_report = QualityAuditValidator().validate(
        dataset_path=quality_audit_path,
    )

    # 5. DATA-MATH12-042
    prod_report = ProductionGateValidator().validate(
        dataset_path=production_gate_path,
        workflow_path=workflow_path,
    )

    all_passed = (
        snap_report.is_valid
        and depth_report.is_valid
        and diag_report.is_valid
        and qa_report.is_valid
        and prod_report.is_valid
    )

    return {
        "status": "PASS" if all_passed else "FAIL",
        "batch_code": "MATH12_038_042_SESSION_FIX",
        "datasets": {
            "DATA-MATH12-038": snap_report.as_dict(),
            "DATA-MATH12-039": depth_report.as_dict(),
            "DATA-MATH12-040": diag_report.as_dict(),
            "DATA-MATH12-041": qa_report.as_dict(),
            "DATA-MATH12-042": prod_report.as_dict(),
        },
        "snapshot_generation": generation_result,
        "summary": {
            "official_core_requirements": "20/20",
            "canonical_candidate_version": snap_report.candidate_manifest_version,
            "composed_fingerprint": snap_report.bound_composed_fingerprint,
            "probability_verified_after_overlay": depth_report.probability_verified_count_after,
            "derivative_zero_evidence_after_secondary": depth_report.derivative_zero_evidence_count,
            "vector_zero_evidence_after_secondary": depth_report.vector_zero_evidence_count,
            "misconception_nodes": diag_report.counts.get("misconceptions", 0),
            "diagnostic_density_gate": qa_report.diagnostic_density_gate,
            "source_diversity_gate": qa_report.source_diversity_gate,
            "rights_status": prod_report.rights_status,
            "ci_workflow_present": prod_report.workflow_exists,
            "production_ready": False,
            "canonical_activation_allowed": False,
            "database_import_allowed": False,
        },
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate DATA-MATH12-038..042 session datasets, snapshot candidate, overlays, and production gates."
    )
    parser.add_argument(
        "--generate-snapshot",
        action="store_true",
        help="Generate snapshot candidate JSON files before running validation.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output raw JSON report.",
    )
    args = parser.parse_args(argv)

    if args.generate_snapshot:
        CanonicalSnapshotCandidateGenerator.generate()

    result = validate_full_session_038_042()

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print("=" * 72)
        print("MATH12_038_042 SESSION VALIDATION SUMMARY")
        print("=" * 72)
        print(f"Overall Status: {result['status']}")
        for dcode, dinfo in result["datasets"].items():
            print(f"  [{dinfo['status']}] {dcode}: {len(dinfo.get('errors', []))} error(s)")
            if dinfo.get("errors"):
                for err in dinfo["errors"]:
                    print(f"       - {err['code']} ({err['location']}): {err['message']}")
        print("-" * 72)
        print(f"Candidate Version:            {result['summary']['canonical_candidate_version']}")
        print(f"Composed Fingerprint:         {result['summary']['composed_fingerprint']}")
        print(f"Official Requirements:        {result['summary']['official_core_requirements']}")
        print(f"Probability Verified Units:   {result['summary']['probability_verified_after_overlay']}")
        print(f"Derivative Zero-Ev PTs:       {result['summary']['derivative_zero_evidence_after_secondary']}")
        print(f"Vector Zero-Ev PTs:           {result['summary']['vector_zero_evidence_after_secondary']}")
        print(f"Misconception Nodes:          {result['summary']['misconception_nodes']}")
        print(f"Density Gate:                 {result['summary']['diagnostic_density_gate']}")
        print(f"Diversity Gate:               {result['summary']['source_diversity_gate']}")
        print(f"Rights Status:                {result['summary']['rights_status']}")
        print(f"CI Workflow Present:          {result['summary']['ci_workflow_present']}")
        print(f"Production Ready:             {result['summary']['production_ready']}")
        print(f"Canonical Write / DB Import:  BLOCKED")
        print("=" * 72)

    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
