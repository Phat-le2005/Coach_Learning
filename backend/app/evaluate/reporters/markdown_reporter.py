from __future__ import annotations

from pathlib import Path
from app.evaluate.schemas import FullEvaluationReport, MetricStatus


class MarkdownReporter:
    """Generates human-readable GitHub Flavored Markdown evaluation report."""

    @classmethod
    def render_markdown(cls, report: FullEvaluationReport) -> str:
        status_badge = "✅ ALL GROUPS PASSED" if report.overall_passed else "❌ SOME GROUPS FAILED"

        lines = [
            "# Báo Cáo Đánh Giá Toàn Diện Hệ Thống (Comprehensive Evaluation Report)",
            "",
            f"- **Mã đợt đánh giá (Evaluation ID)**: `{report.evaluation_id}`",
            f"- **Thời gian thực hiện (Timestamp)**: `{report.timestamp}`",
            f"- **Phiên bản Framework**: `{report.framework_version}`",
            f"- **Tổng số mẫu kiểm định (Total Samples)**: `{report.total_samples_evaluated}`",
            f"- **Kết quả chung**: **`{status_badge}`**",
            "",
            "---",
            "",
            "## 1. Bảng Tổng Hợp Kết Quả Các Nhóm Đánh Giá",
            "",
            "| Nhóm Đánh Giá (Group) | Số mẫu (Samples) | Điểm Tổng (Score) | Trạng Thái | Ghi Chú |",
            "| :--- | :--- | :--- | :--- | :--- |",
        ]

        for group_name, g_res in report.groups.items():
            st = "✅ PASS" if g_res.passed else "❌ FAIL"
            lines.append(
                f"| **`{group_name}`** | {g_res.sample_count} | {round(g_res.overall_score * 100, 1)}% | {st} | {g_res.notes} |"
            )

        lines.extend([
            "",
            "---",
            "",
            "## 2. Chi Tiết Chỉ Số Đo Lường Từng Nhóm",
        ])

        for group_name, g_res in report.groups.items():
            lines.extend([
                "",
                f"### Nhóm: `{group_name}`",
                f"- **Điểm tổng hợp**: `{round(g_res.overall_score * 100, 2)}%` — Trạng thái: `{'PASSED' if g_res.passed else 'FAILED'}`",
                f"- **Số lượng mẫu kiểm tra**: `{g_res.sample_count}`",
                "",
                "| Chỉ Số (Metric) | Điểm Đạt Được | Ngưỡng Yêu Cầu | Đơn Vị | Đánh Giá | Mô Tả Ý Nghĩa |",
                "| :--- | :--- | :--- | :--- | :--- | :--- |",
            ])

            for m in g_res.metrics:
                m_st = "✅ PASS" if m.status == MetricStatus.PASS else "❌ FAIL"
                thresh_str = f"{m.threshold}" if m.threshold is not None else "N/A"
                lines.append(
                    f"| `{m.name}` | **{m.score}** | {thresh_str} | {m.unit or '-'} | {m_st} | {m.description} |"
                )

            # Optional Confusion Matrix
            if g_res.confusion_matrix:
                lines.extend([
                    "",
                    "#### Ma Trận Nhầm Lẫn (Confusion Matrix):",
                    "",
                ])
                cm = g_res.confusion_matrix
                labels = sorted(cm.keys())
                header = "| Thực tế \\ Dự đoán | " + " | ".join(f"`{lbl}`" for lbl in labels) + " |"
                separator = "| :--- | " + " | ".join(":---:" for _ in labels) + " |"
                lines.append(header)
                lines.append(separator)
                for true_lbl in labels:
                    row = [f"**`{true_lbl}`**"]
                    for pred_lbl in labels:
                        cnt = cm[true_lbl].get(pred_lbl, 0)
                        row.append(str(cnt))
                    lines.append("| " + " | ".join(row) + " |")

            # Optional Concept / ProblemType Breakdown
            if g_res.breakdown:
                if "by_concept" in g_res.breakdown:
                    lines.extend([
                        "",
                        "#### Phân Tích Độ Chính Xác Theo Khái Niệm (Concept Breakdown):",
                        "",
                        "| Khái Niệm (Concept) | Số Mẫu | Độ Chính Xác |",
                        "| :--- | :--- | :--- |",
                    ])
                    for c_code, stats in g_res.breakdown["by_concept"].items():
                        acc_pct = round(stats.get("accuracy", 0.0) * 100, 1)
                        lines.append(f"| `{c_code}` | {stats.get('count', 0)} | {acc_pct}% |")

                if "by_problem_type" in g_res.breakdown:
                    lines.extend([
                        "",
                        "#### Phân Tích Độ Chính Xác Theo Dạng Bài (ProblemType Breakdown):",
                        "",
                        "| Dạng Bài (ProblemType) | Số Mẫu | Độ Chính Xác |",
                        "| :--- | :--- | :--- |",
                    ])
                    for pt_code, stats in g_res.breakdown["by_problem_type"].items():
                        acc_pct = round(stats.get("accuracy", 0.0) * 100, 1)
                        lines.append(f"| `{pt_code}` | {stats.get('count', 0)} | {acc_pct}% |")

        lines.extend([
            "",
            "---",
            "",
            "## 3. Cam Kết An Toàn & Bảo Mật Dữ Liệu",
            "- Toàn bộ quy trình kiểm định được thực hiện trên tập dữ liệu mô phỏng độc lập (`data/evaluation/`).",
            "- **Tuyệt đối 0% PII sản xuất**: Không chứa bất kỳ thông tin thực tế nào của học sinh, phụ huynh hay giáo viên.",
            "- Báo cáo kết quả được lưu trữ tại máy cục bộ cho mục đích kiểm soát chất lượng kỹ thuật.",
            "",
        ])

        return "\n".join(lines)

    @classmethod
    def write_report(cls, report: FullEvaluationReport, output_path: Path | str) -> Path:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        content = cls.render_markdown(report)
        with path.open("w", encoding="utf-8") as f:
            f.write(content)
        return path
