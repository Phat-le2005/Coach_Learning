from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Sequence

from app.misconceptions.dataset.schemas import (
    DatasetReport,
    MisconceptionSample,
    SFTRecord,
    SplitStats,
)
from app.misconceptions.dataset.splitter import LeakFreeSplitter


class DatasetExporter:
    """Exports dataset to raw JSONL, SFT-compatible JSONL, and generates comprehensive reports."""

    DATASET_VERSION = "misconception_dataset_v1"
    INSTRUCTION_PROMPT = (
        "Bạn là chuyên gia chẩn đoán giáo dục. Hãy phân tích bài làm của học sinh "
        "dựa trên câu hỏi và đáp án tham chiếu để xác định: nhãn quan niệm sai lầm chuẩn hóa (misconception label), "
        "danh mục lỗi (error category), mức độ nghiêm trọng (severity) và chiến lược gợi ý sư phạm đề xuất (recommended hint type)."
    )

    def __init__(self, output_dir: Path | str) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def sample_to_sft_record(self, sample: MisconceptionSample) -> SFTRecord:
        """Convert sample into standard SFT instruction format."""
        return SFTRecord(
            id=sample.id,
            instruction=self.INSTRUCTION_PROMPT,
            input={
                "question": sample.question,
                "problem_type": sample.problem_type,
                "concepts": sample.concepts,
                "learning_outcomes": sample.learning_outcomes,
                "taxonomy": sample.taxonomy.value,
                "student_solution": sample.student_solution,
                "reference_solution": sample.reference_solution,
            },
            output={
                "misconception_label": sample.verified_misconception_label,
                "error_category": sample.error_category.value,
                "severity": sample.severity.value,
                "recommended_hint_type": sample.recommended_hint_type.value,
            },
        )

    def generate_report(
        self,
        samples: Sequence[MisconceptionSample],
        train_samples: Sequence[MisconceptionSample],
        val_samples: Sequence[MisconceptionSample],
        test_samples: Sequence[MisconceptionSample],
        splitter: LeakFreeSplitter,
    ) -> DatasetReport:
        """Compile detailed statistics across curriculum, classes, splits, and quality metrics."""
        total = len(samples)
        clusters = {s.cluster_id for s in samples if s.cluster_id}

        # Distributions
        pt_dist = dict(Counter(s.problem_type for s in samples).most_common())

        concept_counter: Counter[str] = Counter()
        for s in samples:
            concept_counter.update(s.concepts)
        concept_dist = dict(concept_counter.most_common())

        class_dist = dict(Counter(s.verified_misconception_label for s in samples).most_common())
        error_cat_dist = dict(Counter(s.error_category.value for s in samples).most_common())
        severity_dist = dict(Counter(s.severity.value for s in samples).most_common())
        hint_type_dist = dict(Counter(s.recommended_hint_type.value for s in samples).most_common())
        taxonomy_dist = dict(Counter(s.taxonomy.value for s in samples).most_common())

        # Missing values check
        missing_values: dict[str, int] = {
            "question": sum(1 for s in samples if not s.question),
            "problem_type": sum(1 for s in samples if not s.problem_type),
            "concepts": sum(1 for s in samples if not s.concepts),
            "learning_outcomes (optional)": sum(1 for s in samples if s.learning_outcomes is None),
            "taxonomy": sum(1 for s in samples if not s.taxonomy),
            "student_solution": sum(1 for s in samples if not s.student_solution),
            "reference_solution": sum(1 for s in samples if not s.reference_solution),
            "verified_misconception_label": sum(1 for s in samples if not s.verified_misconception_label),
            "error_category": sum(1 for s in samples if not s.error_category),
            "severity": sum(1 for s in samples if not s.severity),
            "recommended_hint_type": sum(1 for s in samples if not s.recommended_hint_type),
        }

        # Duplicates count (samples sharing cluster with another sample)
        cluster_counts = Counter(s.cluster_id for s in samples if s.cluster_id)
        duplicates_detected = sum(count - 1 for count in cluster_counts.values() if count > 1)

        # Split stats
        def make_split_stats(partition: Sequence[MisconceptionSample]) -> SplitStats:
            p_clusters = sorted(list({s.cluster_id for s in partition if s.cluster_id}))
            pct = round((len(partition) / total * 100), 2) if total > 0 else 0.0
            return SplitStats(
                sample_count=len(partition),
                percentage=pct,
                question_clusters_count=len(p_clusters),
                cluster_ids=p_clusters,
            )

        splits_stats = {
            "train": make_split_stats(train_samples),
            "validation": make_split_stats(val_samples),
            "test": make_split_stats(test_samples),
        }

        leakage_check = splitter.verify_leak_free(train_samples, val_samples, test_samples)

        return DatasetReport(
            dataset_version=self.DATASET_VERSION,
            total_samples=total,
            unique_question_clusters=len(clusters),
            problem_type_distribution=pt_dist,
            concept_distribution=concept_dist,
            class_distribution=class_dist,
            error_category_distribution=error_cat_dist,
            severity_distribution=severity_dist,
            recommended_hint_type_distribution=hint_type_dist,
            taxonomy_distribution=taxonomy_dist,
            missing_values=missing_values,
            duplicates_detected=duplicates_detected,
            splits=splits_stats,
            leakage_check=leakage_check,
        )

    def export(
        self,
        samples: Sequence[MisconceptionSample],
        train_samples: Sequence[MisconceptionSample],
        val_samples: Sequence[MisconceptionSample],
        test_samples: Sequence[MisconceptionSample],
        report: DatasetReport,
    ) -> dict[str, Path]:
        """Write all dataset files and reports to the output directory."""
        exported_files: dict[str, Path] = {}

        # 1. Full raw JSONL
        full_jsonl = self.output_dir / "dataset_v1.jsonl"
        with full_jsonl.open("w", encoding="utf-8") as f:
            for s in samples:
                f.write(s.model_dump_json() + "\n")
        exported_files["dataset_v1"] = full_jsonl

        # 2. Partitioned raw JSONL
        for name, partition in [
            ("train", train_samples),
            ("val", val_samples),
            ("test", test_samples),
        ]:
            path = self.output_dir / f"{name}.jsonl"
            with path.open("w", encoding="utf-8") as f:
                for s in partition:
                    f.write(s.model_dump_json() + "\n")
            exported_files[name] = path

        # 3. SFT formatted JSONL
        for name, partition in [
            ("sft_train", train_samples),
            ("sft_val", val_samples),
            ("sft_test", test_samples),
        ]:
            path = self.output_dir / f"{name}.jsonl"
            with path.open("w", encoding="utf-8") as f:
                for s in partition:
                    sft_record = self.sample_to_sft_record(s)
                    f.write(sft_record.model_dump_json() + "\n")
            exported_files[name] = path

        # 4. Report JSON
        report_json_path = self.output_dir / "report.json"
        with report_json_path.open("w", encoding="utf-8") as f:
            json.dump(report.model_dump(), f, ensure_ascii=False, indent=2)
        exported_files["report_json"] = report_json_path

        # 5. Markdown Report DATASET_REPORT.md
        md_report_path = self.output_dir / "DATASET_REPORT.md"
        md_content = self.render_markdown_report(report)
        with md_report_path.open("w", encoding="utf-8") as f:
            f.write(md_content)
        exported_files["report_md"] = md_report_path

        return exported_files

    def render_markdown_report(self, report: DatasetReport) -> str:
        """Render a clean GitHub Markdown dataset report."""
        lines = [
            f"# Báo cáo Tập Dữ liệu Nhận Diện Quan Niệm Sai Lầm (`{report.dataset_version}`)",
            "",
            "## 1. Tổng Quan Kích Thước & Phân Cụm",
            f"- **Tổng số mẫu (Sample count)**: `{report.total_samples}`",
            f"- **Số cụm câu hỏi duy nhất (Unique question clusters)**: `{report.unique_question_clusters}`",
            f"- **Số mẫu trùng/gần trùng lặp đã gom cụm (Duplicates grouped)**: `{report.duplicates_detected}`",
            "",
            "## 2. Phân Chia Tập Huấn Luyện / Đánh Giá / Kiểm Thử (Split Statistics)",
            "| Phân tập (Split) | Số mẫu (Samples) | Tỷ lệ (%) | Số cụm câu hỏi (Clusters) |",
            "| :--- | :--- | :--- | :--- |",
        ]

        for split_name, stats in report.splits.items():
            lines.append(
                f"| `{split_name}` | {stats.sample_count} | {stats.percentage}% | {stats.question_clusters_count} |"
            )

        lines.extend([
            "",
            "### Kiểm Tra Rò Rỉ Dữ Liệu (Leakage Verification)",
            f"- **Trạng thái**: `{'✅ LEAK-FREE' if report.leakage_check.is_leak_free else '❌ LEAKAGE DETECTED'}`",
            f"- **Train-Val Cluster Overlap**: `{report.leakage_check.train_val_cluster_overlap}`",
            f"- **Train-Test Cluster Overlap**: `{report.leakage_check.train_test_cluster_overlap}`",
            f"- **Val-Test Cluster Overlap**: `{report.leakage_check.val_test_cluster_overlap}`",
            f"- **Ghi chú**: {report.leakage_check.notes}",
            "",
            "## 3. Phân Phối Dạng Bài (ProblemType Distribution)",
            "| Dạng bài (ProblemType) | Số mẫu | Tỷ lệ (%) |",
            "| :--- | :--- | :--- |",
        ])

        for pt, count in report.problem_type_distribution.items():
            pct = round(count / report.total_samples * 100, 2) if report.total_samples > 0 else 0
            lines.append(f"| `{pt}` | {count} | {pct}% |")

        lines.extend([
            "",
            "## 4. Phân Phối Khái Niệm (Concept Distribution)",
            "| Khái niệm (Concept) | Tần suất xuất hiện |",
            "| :--- | :--- |",
        ])

        for concept, count in report.concept_distribution.items():
            lines.append(f"| `{concept}` | {count} |")

        lines.extend([
            "",
            "## 5. Phân Phối Nhãn Quan Niệm Sai Lầm (Class Distribution)",
            "| Mã sai lầm (Misconception Label) | Số mẫu | Tỷ lệ (%) |",
            "| :--- | :--- | :--- |",
        ])

        for label, count in report.class_distribution.items():
            pct = round(count / report.total_samples * 100, 2) if report.total_samples > 0 else 0
            lines.append(f"| `{label}` | {count} | {pct}% |")

        lines.extend([
            "",
            "## 6. Phân Phối Danh Mục Lỗi & Mức Độ Nghiêm Trọng",
            "### Danh Mục Lỗi (Error Category)",
            "| Danh mục | Số mẫu |",
            "| :--- | :--- |",
        ])
        for cat, count in report.error_category_distribution.items():
            lines.append(f"| `{cat}` | {count} |")

        lines.extend([
            "",
            "### Mức Độ Nghiêm Trọng (Severity)",
            "| Mức độ | Số mẫu |",
            "| :--- | :--- |",
        ])
        for sev, count in report.severity_distribution.items():
            lines.append(f"| `{sev}` | {count} |")

        lines.extend([
            "",
            "### Loại Gợi Ý Sư Phạm (Recommended Hint Type)",
            "| Loại gợi ý | Số mẫu |",
            "| :--- | :--- |",
        ])
        for ht, count in report.recommended_hint_type_distribution.items():
            lines.append(f"| `{ht}` | {count} |")

        lines.extend([
            "",
            "## 7. Phân Tích Giá Trị Khuyết Thiếu (Missing Values Analysis)",
            "| Thuộc tính (Field) | Số lượng khuyết thiếu | Trạng thái kiểm soát |",
            "| :--- | :--- | :--- |",
        ])
        for field, count in report.missing_values.items():
            status = "Tùy chọn (Optional)" if "optional" in field else ("✅ 100% Đầy đủ" if count == 0 else "❌ Thiếu dữ liệu")
            lines.append(f"| `{field}` | {count} | {status} |")

        lines.append("")
        return "\n".join(lines)
