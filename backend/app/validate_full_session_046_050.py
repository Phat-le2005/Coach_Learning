from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Sequence

from app.curriculum.data_completion_snapshot import (
    DEFAULT_DATA_COMPLETION_SNAPSHOT_PATH,
    DataCompletionSnapshotValidator,
)
from app.questions.academic_web_evidence import (
    DEFAULT_ACADEMIC_WEB_EVIDENCE_PATH,
    AcademicWebEvidenceValidator,
)
from app.questions.final_acquisition_gate import (
    DEFAULT_FINAL_ACQUISITION_GATE_PATH,
    FinalAcquisitionGateValidator,
)
from app.questions.final_quality_audit import (
    DEFAULT_FINAL_QUALITY_AUDIT_PATH,
    FinalQualityAuditValidator,
)
from app.questions.pinned_depth_supplement import (
    DEFAULT_PINNED_DEPTH_SUPPLEMENT_PATH,
    PinnedDepthSupplementValidator,
)


def validate_full_session_046_050(
    *,
    academic_web_path: Path = DEFAULT_ACADEMIC_WEB_EVIDENCE_PATH,
    pinned_depth_path: Path = DEFAULT_PINNED_DEPTH_SUPPLEMENT_PATH,
    final_quality_path: Path = DEFAULT_FINAL_QUALITY_AUDIT_PATH,
    final_acquisition_path: Path = DEFAULT_FINAL_ACQUISITION_GATE_PATH,
    data_completion_path: Path = DEFAULT_DATA_COMPLETION_SNAPSHOT_PATH,
) -> dict[str, Any]:
    # 1. DATA-MATH12-046
    web_report = AcademicWebEvidenceValidator().validate(
        dataset_path=academic_web_path,
    )

    # 2. DATA-MATH12-047
    pinned_report = PinnedDepthSupplementValidator().validate(
        dataset_path=pinned_depth_path,
    )

    # 3. DATA-MATH12-048
    quality_report = FinalQualityAuditValidator().validate(
        dataset_path=final_quality_path,
    )

    # 4. DATA-MATH12-049
    acq_report = FinalAcquisitionGateValidator().validate(
        dataset_path=final_acquisition_path,
    )

    # 5. DATA-MATH12-050
    completion_report = DataCompletionSnapshotValidator().validate(
        dataset_path=data_completion_path,
    )

    all_passed = (
        web_report.is_valid
        and pinned_report.is_valid
        and quality_report.is_valid
        and acq_report.is_valid
        and completion_report.is_valid
    )

    return {
        "status": "PASS" if all_passed else "FAIL",
        "batch_code": "MATH12_046_050_FINAL_DEPTH_HARDENING",
        "datasets": {
            "DATA-MATH12-046": web_report.as_dict(),
            "DATA-MATH12-047": pinned_report.as_dict(),
            "DATA-MATH12-048": quality_report.as_dict(),
            "DATA-MATH12-049": acq_report.as_dict(),
            "DATA-MATH12-050": completion_report.as_dict(),
        },
        "summary": {
            "official_core_requirements": completion_report.official_core_requirements,
            "new_pinned_units": pinned_report.counts.get("verified_units_count", 0),
            "derivative_academic_zero_after": len(web_report.derivative_zero_academic),
            "derivative_pinned_practice_zero_after": list(web_report.derivative_zero_pinned),
            "vector_zero_after": 0,
            "statistics_practice_units_after": pinned_report.stats_practice_units_after,
            "statistics_dominant_source_share_after": pinned_report.stats_dominant_source_share,
            "statistics_source_diversity_gate": pinned_report.stats_diversity_gate,
            "probability_practice_units_after": pinned_report.prob_practice_units_after,
            "probability_dominant_source_share_after": pinned_report.prob_dominant_source_share,
            "probability_diversity_gate": pinned_report.prob_diversity_gate,
            "probability_units_needed_to_pass_70pct": pinned_report.prob_units_needed_to_pass,
            "minimum_demo_data_done": completion_report.minimum_demo_data_done,
            "official_curriculum_data_done": completion_report.official_curriculum_data_done,
            "adaptive_production_complete": completion_report.adaptive_production_data_done,
            "rights_status": completion_report.rights_status,
            "canonical_activation_allowed": completion_report.canonical_write_allowed,
            "database_import_allowed": completion_report.database_import_allowed,
            "production_release_allowed": completion_report.production_release_allowed,
        },
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate DATA-MATH12-046..050 academic web evidence, pinned depth, quality audit, acquisition freeze, and completion snapshot."
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output raw JSON report.",
    )
    args = parser.parse_args(argv)

    result = validate_full_session_046_050()

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print("=" * 72)
        print("MATH12_046_050 SESSION VALIDATION SUMMARY")
        print("=" * 72)
        print(f"Overall Status: {result['status']}")
        for dcode, dinfo in result["datasets"].items():
            print(f"  [{dinfo['status']}] {dcode}: {len(dinfo.get('errors', []))} error(s)")
        print("-" * 72)
        s = result["summary"]
        print(f"Official Requirements:        {s['official_core_requirements']}")
        print(f"New Pinned Units:             {s['new_pinned_units']}")
        print(f"Derivative Academic Zero:     {s['derivative_academic_zero_after']}")
        print(f"Derivative Pinned Zero:       {s['derivative_pinned_practice_zero_after']}")
        print(f"Vector Zero After:            {s['vector_zero_after']}")
        print(f"Stats Practice Units:         {s['statistics_practice_units_after']}")
        print(f"Stats Dominant Share:         {s['statistics_dominant_source_share_after']:.4f} ({s['statistics_source_diversity_gate']})")
        print(f"Probability Practice Units:   {s['probability_practice_units_after']}")
        print(f"Probability Dominant Share:   {s['probability_dominant_source_share_after']:.4f} ({s['probability_diversity_gate']})")
        print(f"Probability Delta to 70%:     {s['probability_units_needed_to_pass_70pct']} unit")
        print(f"Adaptive Production Done:     {s['adaptive_production_complete']}")
        print(f"Rights Status:                {s['rights_status']}")
        print(f"Canonical Write / DB Import:  BLOCKED")
        print("=" * 72)

    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
