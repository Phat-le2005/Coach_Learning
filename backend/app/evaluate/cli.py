from __future__ import annotations

import argparse
import sys
from pathlib import Path

from app.evaluate.runner import EvaluationRunner
from app.evaluate.schemas import EvaluationGroup


def main() -> None:
    parser = argparse.ArgumentParser(
        description="CoachLearning Evaluation Framework — Multi-Group System Benchmark."
    )
    parser.add_argument(
        "--groups",
        type=str,
        default="all",
        help="Comma-separated evaluation groups (LEARNING_ENGINE, MISCONCEPTION, RAG, AI_TUTOR, TEACHER_COPILOT, PARENT_SUMMARY, SYSTEM_AI) or 'all'.",
    )
    parser.add_argument(
        "--data-dir",
        type=str,
        default="data/evaluation",
        help="Directory containing dedicated evaluation datasets (default: data/evaluation).",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="data/evaluation/reports",
        help="Target output directory for evaluation reports (default: data/evaluation/reports).",
    )
    args = parser.parse_args()

    selected_groups = None
    if args.groups and args.groups.lower() != "all":
        selected_groups = [g.strip() for g in args.groups.split(",") if g.strip()]

    print(f"[*] Starting CoachLearning Evaluation Framework...")
    print(f"    - Datasets directory: {args.data_dir}")
    print(f"    - Output directory:   {args.output_dir}")

    runner = EvaluationRunner(data_dir=args.data_dir, output_dir=args.output_dir)
    try:
        report, files = runner.run(selected_groups=selected_groups)
    except Exception as e:
        print(f"[!] Evaluation failed with error: {e}", file=sys.stderr)
        sys.exit(1)

    print("\n" + "=" * 70)
    print("           EVALUATION SUMMARY REPORT           ")
    print("=" * 70)
    for group_name, g_res in report.groups.items():
        status_tag = "[PASS]" if g_res.passed else "[FAIL]"
        pct = round(g_res.overall_score * 100, 1)
        print(f"  {status_tag:6s} {group_name:<20s} Score: {pct:>5.1f}%  ({g_res.sample_count} samples)")
    print("-" * 70)
    final_status = "ALL GROUPS PASSED" if report.overall_passed else "SOME GROUPS FAILED"
    print(f"  Status: {final_status} | Total samples: {report.total_samples_evaluated}")
    print("=" * 70)
    print(f"[+] Reports generated:")
    print(f"    - JSON:     {files['json']}")
    print(f"    - Markdown: {files['markdown']}")
    print("[OK] Evaluation run completed successfully.")

    if not report.overall_passed:
        sys.exit(1)


if __name__ == "__main__":
    main()
