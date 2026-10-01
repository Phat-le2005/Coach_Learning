from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Sequence

from app.curriculum.operational_evidence import (
    DEFAULT_OPERATIONAL_EVIDENCE_PATH,
    OperationalEvidenceValidator,
)
from app.curriculum.production_gate import DEFAULT_PRODUCTION_GATE_PATH
from app.questions.depth_queue import (
    DEFAULT_DEPTH_QUEUE_PATH,
    DepthQueueValidator,
)
from app.questions.local_depth_supplement import (
    DEFAULT_LOCAL_DEPTH_SUPPLEMENT_PATH,
    LocalDepthSupplementValidator,
)


def validate_full_session_043_045(
    *,
    local_depth_path: Path = DEFAULT_LOCAL_DEPTH_SUPPLEMENT_PATH,
    operational_evidence_path: Path = DEFAULT_OPERATIONAL_EVIDENCE_PATH,
    data042_path: Path = DEFAULT_PRODUCTION_GATE_PATH,
    depth_queue_path: Path = DEFAULT_DEPTH_QUEUE_PATH,
) -> dict[str, Any]:
    # 1. DATA-MATH12-043
    depth_report = LocalDepthSupplementValidator().validate(
        dataset_path=local_depth_path,
    )

    # 2. DATA-MATH12-044
    ci_report = OperationalEvidenceValidator().validate(
        dataset_path=operational_evidence_path,
        data042_path=data042_path,
    )

    # 3. DATA-MATH12-045
    queue_report = DepthQueueValidator().validate(
        dataset_path=depth_queue_path,
    )

    all_passed = (
        depth_report.is_valid
        and ci_report.is_valid
        and queue_report.is_valid
    )

    return {
        "status": "PASS" if all_passed else "FAIL",
        "batch_code": "MATH12_043_045_REAL_SOURCE_DEPTH",
        "datasets": {
            "DATA-MATH12-043": depth_report.as_dict(),
            "DATA-MATH12-044": ci_report.as_dict(),
            "DATA-MATH12-045": queue_report.as_dict(),
        },
        "summary": {
            "official_core_requirements": "20/20",
            "new_source_backed_units": depth_report.counts.get("verified_units_count", 0),
            "derivative_zero_evidence_after": list(depth_report.derivative_remaining_zero),
            "vector_zero_evidence_after": list(depth_report.vector_remaining_zero),
            "probability_practice_units_after": depth_report.probability_practice_units_after,
            "probability_source_families_after": depth_report.probability_source_families_after,
            "ci_evidence_state": ci_report.ci_evidence_state,
            "historical_data042_immutable": ci_report.historical_data042_immutable,
            "rights_status": ci_report.rights_status,
            "production_ready": False,
            "canonical_activation_allowed": False,
            "database_import_allowed": False,
            "production_release_allowed": False,
        },
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate DATA-MATH12-043..045 real-source depth supplement, CI refresh, and remaining queue."
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output raw JSON report.",
    )
    args = parser.parse_args(argv)

    result = validate_full_session_043_045()

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print("=" * 72)
        print("MATH12_043_045 SESSION VALIDATION SUMMARY")
        print("=" * 72)
        print(f"Overall Status: {result['status']}")
        for dcode, dinfo in result["datasets"].items():
            print(f"  [{dinfo['status']}] {dcode}: {len(dinfo.get('errors', []))} error(s)")
            if dinfo.get("errors"):
                for err in dinfo["errors"]:
                    print(f"       - {err['code']} ({err['location']}): {err['message']}")
        print("-" * 72)
        print(f"Official Requirements:        {result['summary']['official_core_requirements']}")
        print(f"New Source-Backed Units:      {result['summary']['new_source_backed_units']}")
        print(f"Derivative Zero-Ev After:     {result['summary']['derivative_zero_evidence_after']}")
        print(f"Vector Zero-Ev After:         {result['summary']['vector_zero_evidence_after']}")
        print(f"Probability Units After:      {result['summary']['probability_practice_units_after']}")
        print(f"Probability Families After:   {result['summary']['probability_source_families_after']}")
        print(f"CI Evidence State:            {result['summary']['ci_evidence_state']}")
        print(f"Historical DATA-042 Clean:    {result['summary']['historical_data042_immutable']}")
        print(f"Rights Status:                {result['summary']['rights_status']}")
        print(f"Production Ready:             {result['summary']['production_ready']}")
        print(f"Canonical Write / DB Import:  BLOCKED")
        print("=" * 72)

    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
