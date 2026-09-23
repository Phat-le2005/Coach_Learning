from __future__ import annotations

import argparse
import sys
from pathlib import Path

from app.misconceptions.dataset.clusterer import QuestionClusterer
from app.misconceptions.dataset.curator import build_curated_samples
from app.misconceptions.dataset.exporter import DatasetExporter
from app.misconceptions.dataset.schemas import DatasetReport
from app.misconceptions.dataset.splitter import LeakFreeSplitter
from app.misconceptions.dataset.validator import QualityValidator


def run_pipeline(
    output_dir: Path | str = "data/datasets/misconception_dataset_v1",
    train_ratio: float = 0.70,
    val_ratio: float = 0.15,
    test_ratio: float = 0.15,
    similarity_threshold: float = 0.60,
) -> DatasetReport:
    """Execute complete dataset preparation, validation, clustering, splitting, and export pipeline."""
    output_path = Path(output_dir)
    print(f"[*] Starting Misconception Detection Dataset Pipeline -> {output_path}")

    # 1. Curate samples
    raw_samples = build_curated_samples()
    print(f"[+] Loaded {len(raw_samples)} candidate samples.")

    # 2. Validate quality & PII
    validator = QualityValidator()
    approved_samples = []
    for sample in raw_samples:
        errors = validator.validate_sample(sample)
        if errors:
            print(f"[!] Sample {sample.id} rejected: {errors}", file=sys.stderr)
            raise ValueError(f"Quality gate failed for {sample.id}: {errors}")
        approved_samples.append(sample)
    print(f"[+] Quality approval gate passed: {len(approved_samples)}/{len(raw_samples)} approved (100%).")

    # 3. Cluster near-duplicates and identical questions
    clusterer = QuestionClusterer(similarity_threshold=similarity_threshold)
    clustered_samples = clusterer.assign_clusters(approved_samples)
    unique_clusters = len({s.cluster_id for s in clustered_samples})
    print(f"[+] Near-duplicate clustering complete: grouped into {unique_clusters} unique Question Clusters.")

    # 4. Leak-free splitting
    splitter = LeakFreeSplitter(
        train_ratio=train_ratio,
        val_ratio=val_ratio,
        test_ratio=test_ratio,
        random_seed=42,
    )
    train_samples, val_samples, test_samples = splitter.split(clustered_samples)
    print(
        f"[+] Partitioning complete (Leak-free verified):\n"
        f"    - Train: {len(train_samples)} samples ({len({s.cluster_id for s in train_samples})} clusters)\n"
        f"    - Validation: {len(val_samples)} samples ({len({s.cluster_id for s in val_samples})} clusters)\n"
        f"    - Test: {len(test_samples)} samples ({len({s.cluster_id for s in test_samples})} clusters)"
    )

    # 5. Export JSONL & generate reports
    exporter = DatasetExporter(output_dir=output_path)
    report = exporter.generate_report(
        samples=clustered_samples,
        train_samples=train_samples,
        val_samples=val_samples,
        test_samples=test_samples,
        splitter=splitter,
    )
    exported_files = exporter.export(
        samples=clustered_samples,
        train_samples=train_samples,
        val_samples=val_samples,
        test_samples=test_samples,
        report=report,
    )

    print(f"[+] Exported {len(exported_files)} files successfully to {output_path}:")
    for name, path in exported_files.items():
        print(f"    - {name}: {path.name}")

    print("[OK] Pipeline execution finished successfully.")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Prepare, validate, cluster, and export Misconception Detection dataset."
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="data/datasets/misconception_dataset_v1",
        help="Target output directory for exported files and reports.",
    )
    parser.add_argument(
        "--train-ratio",
        type=float,
        default=0.70,
        help="Train split ratio (default 0.70)",
    )
    parser.add_argument(
        "--val-ratio",
        type=float,
        default=0.15,
        help="Validation split ratio (default 0.15)",
    )
    parser.add_argument(
        "--test-ratio",
        type=float,
        default=0.15,
        help="Test split ratio (default 0.15)",
    )
    parser.add_argument(
        "--similarity-threshold",
        type=float,
        default=0.60,
        help="Jaccard similarity threshold for near-duplicate question clustering.",
    )
    args = parser.parse_args()

    run_pipeline(
        output_dir=args.output_dir,
        train_ratio=args.train_ratio,
        val_ratio=args.val_ratio,
        test_ratio=args.test_ratio,
        similarity_threshold=args.similarity_threshold,
    )


if __name__ == "__main__":
    main()
