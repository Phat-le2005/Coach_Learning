"use client";

import {
  ArrowRight,
  BookOpen,
  CheckCircle2,
  Clock,
  Compass,
  Sparkles,
  Target,
  X,
  Zap,
} from "lucide-react";
import Link from "next/link";
import { useEffect, useRef } from "react";

import { getMasteryStateDescription, getMasteryStateLabel } from "../copy";
import {
  getPostrequisitesForProblemType,
  getPrerequisitesForProblemType,
} from "../prerequisite-graph";
import type { KnowledgeProblemTypeNode } from "../types";
import styles from "../KnowledgeWorld3D.module.css";

export interface KnowledgeDetailPanelProps {
  node: KnowledgeProblemTypeNode | null;
  onClose: () => void;
  onSelectRelatedCode?: (code: string) => void;
  onExploreRelations?: (code: string) => void;
}

// Key mathematical theory formula snippets for Grade 12 Math topics
const THEORY_SNIPPETS: Record<string, { summary: string; formula?: string }> = {
  MONOTONICITY_FROM_DERIVATIVE_SIGN: {
    summary: "Hàm số f(x) đồng biến trên K khi f'(x) ≥ 0, nghịch biến khi f'(x) ≤ 0 (dấu bằng tại hữu hạn điểm).",
    formula: "f'(x) \\ge 0, \\forall x \\in K \\implies f(x) \\text{ đồng biến}",
  },
  FIND_FUNCTION_EXTREMA: {
    summary: "Điểm cực trị x₀ là điểm làm f'(x₀) = 0 hoặc không xác định và f'(x) đổi dấu khi qua x₀.",
    formula: "f'(x_0) = 0 \\quad \\text{và } f'(x) \\text{ đổi dấu}",
  },
  GLOBAL_EXTREMA_INTERVAL: {
    summary: "Tìm GTLN, GTNN trên đoạn [a, b]: Tính f(a), f(b) và f(xᵢ) tại các điểm tới hạn xᵢ ∈ (a, b).",
    formula: "\\max_{[a, b]} f(x) = \\max \\{ f(a), f(b), f(x_i) \\}",
  },
  DEFINITE_INTEGRAL_DEFINITION_APPLICATION: {
    summary: "Định lý Newton-Leibniz: Tích phân của f(x) từ a đến b bằng F(b) - F(a) với F'(x) = f(x).",
    formula: "\\int_{a}^{b} f(x)\\,dx = F(b) - F(a)",
  },
  AREA_BY_INTEGRAL: {
    summary: "Diện tích hình phẳng giới hạn bởi đồ thị y = f(x), y = g(x) và x = a, x = b.",
    formula: "S = \\int_{a}^{b} |f(x) - g(x)|\\,dx",
  },
  SPACE_COORDINATES_POINT: {
    summary: "Tọa độ điểm M(x, y, z) trong không gian Oxyz tương ứng với vectơ OM = x·i + y·j + z·k.",
    formula: "\\vec{OM} = x\\vec{i} + y\\vec{j} + z\\vec{k}",
  },
  VECTOR_DOT_PRODUCT_3D: {
    summary: "Tích vô hướng của hai vectơ: a · b = |a|·|b|·cos(a, b) = a₁b₁ + a₂b₂ + a₃b₃.",
    formula: "\\vec{a} \\cdot \\vec{b} = a_1 b_1 + a_2 b_2 + a_3 b_3",
  },
  PLANE_EQUATION_WRITING: {
    summary: "Phương trình tổng quát mặt phẳng qua M₀(x₀, y₀, z₀) với VTPT n(A, B, C): A(x-x₀) + B(y-y₀) + C(z-z₀) = 0.",
    formula: "A(x - x_0) + B(y - y_0) + C(z - z_0) = 0",
  },
  POINT_TO_PLANE_DISTANCE: {
    summary: "Khoảng cách từ điểm M(x₀, y₀, z₀) đến mặt phẳng (P): Ax + By + Cz + D = 0.",
    formula: "d(M, (P)) = \\frac{|Ax_0 + By_0 + Cz_0 + D|}{\\sqrt{A^2 + B^2 + C^2}}",
  },
  TOTAL_PROBABILITY_FORMULA: {
    summary: "Công thức xác suất toàn phần: P(A) = P(B₁)P(A|B₁) + ... + P(Bₙ)P(A|Bₙ) với {Bᵢ} là nhóm biến cố đầy đủ.",
    formula: "P(A) = \\sum_{i=1}^{n} P(B_i) \\cdot P(A \\mid B_i)",
  },
  BAYES_FORMULA_APPLICATION: {
    summary: "Công thức Bayes tính xác suất hậu nghiệm của nguyên nhân Bₖ khi biến cố A đã xảy ra.",
    formula: "P(B_k \\mid A) = \\frac{P(B_k) P(A \\mid B_k)}{\\sum_{i} P(B_i) P(A \\mid B_i)}",
  },
};

export function KnowledgeDetailPanel({
  node,
  onClose,
  onSelectRelatedCode,
  onExploreRelations,
}: KnowledgeDetailPanelProps) {
  const panelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        onClose();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [onClose]);

  if (!node) {
    return (
      <aside className={`${styles.detailPanel} ${styles.detailPanelHidden}`} aria-hidden="true" />
    );
  }

  const stateLabel = getMasteryStateLabel(node.state);
  const stateDesc = getMasteryStateDescription(node.state);
  const prereqs = getPrerequisitesForProblemType(node.code);
  const postreqs = getPostrequisitesForProblemType(node.code);
  const theory = THEORY_SNIPPETS[node.code] ?? {
    summary: "Nắm vững lý thuyết trọng tâm, các bước biến đổi và nhận dạng dấu hiệu giải toán cho dạng bài này.",
  };

  const formattedDate = node.lastPracticedAt
    ? new Date(node.lastPracticedAt).toLocaleDateString("vi-VN", {
        month: "short",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      })
    : "Chưa luyện tập";

  return (
    <aside
      ref={panelRef}
      className={styles.detailPanel}
      role="region"
      aria-label={`Chi tiết dạng bài ${node.name}`}
    >
      {/* Panel Header */}
      <div className={styles.detailHeader}>
        <div>
          <div className={styles.detailBreadcrumb}>
            {node.chapterName} • {node.topicName}
          </div>
          <h2 className={styles.detailTitle}>{node.name}</h2>
        </div>
        <button
          className={styles.detailCloseBtn}
          onClick={onClose}
          aria-label="Đóng bảng chi tiết"
        >
          <X size={16} aria-hidden="true" />
        </button>
      </div>

      {/* Panel Body */}
      <div className={styles.detailBody}>
        {/* State Card */}
        <div className={styles.stateCard}>
          <div className={styles.stateBadge}>
            <span className={styles.stateDot} />
            <span>{stateLabel}</span>
          </div>
          <div className={styles.stateScore}>
            {node.masteryScore !== undefined ? `${node.masteryScore}%` : "Chưa tích lũy"}
          </div>
        </div>

        {/* Stats Strip */}
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "1fr 1fr",
            gap: "8px",
            fontSize: "12px",
            color: "rgba(247, 247, 238, 0.7)",
          }}
        >
          <div
            style={{
              background: "rgba(5, 25, 20, 0.4)",
              padding: "8px 10px",
              borderRadius: "8px",
              display: "flex",
              alignItems: "center",
              gap: "6px",
            }}
          >
            <Target size={14} color="#8be5c2" />
            <span>{node.attemptCount} lượt làm</span>
          </div>
          <div
            style={{
              background: "rgba(5, 25, 20, 0.4)",
              padding: "8px 10px",
              borderRadius: "8px",
              display: "flex",
              alignItems: "center",
              gap: "6px",
            }}
          >
            <Clock size={14} color="#67bfd4" />
            <span>{formattedDate}</span>
          </div>
        </div>

        {/* Theory & Key Formula */}
        <div className={styles.sectionBlock}>
          <div className={styles.sectionHeading}>
            <BookOpen size={14} />
            <span>Trọng tâm kiến thức</span>
          </div>
          <p style={{ fontSize: "12px", lineHeight: "1.5", color: "rgba(247, 247, 238, 0.85)", margin: 0 }}>
            {theory.summary}
          </p>
          {theory.formula && (
            <div className={styles.formulaBox}>
              <code>{theory.formula}</code>
            </div>
          )}
        </div>

        {/* Prerequisites */}
        {prereqs.length > 0 && (
          <div className={styles.sectionBlock}>
            <div className={styles.sectionHeading}>
              <Sparkles size={14} />
              <span>Kiến thức cần học trước ({prereqs.length})</span>
            </div>
            <div className={styles.prereqList}>
              {prereqs.map((code) => (
                <div
                  key={code}
                  className={styles.prereqItem}
                  onClick={() => onSelectRelatedCode?.(code)}
                  style={{ cursor: onSelectRelatedCode ? "pointer" : "default" }}
                >
                  <span style={{ color: "#e8bf6a" }}>◆</span>
                  <span>{code.replace(/_/g, " ")}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Unlocks / Postrequisites */}
        {postreqs.length > 0 && (
          <div className={styles.sectionBlock}>
            <div className={styles.sectionHeading} style={{ color: "#8be5c2" }}>
              <Zap size={14} />
              <span>Mở khóa tiếp theo ({postreqs.length})</span>
            </div>
            <div className={styles.prereqList}>
              {postreqs.map((code) => (
                <div
                  key={code}
                  className={styles.prereqItem}
                  onClick={() => onSelectRelatedCode?.(code)}
                  style={{ cursor: onSelectRelatedCode ? "pointer" : "default" }}
                >
                  <span style={{ color: "#8be5c2" }}>→</span>
                  <span>{code.replace(/_/g, " ")}</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Action Footer */}
      <div className={styles.detailFooter}>
        <Link
          href={`/student/practice?problem_type_id=${encodeURIComponent(node.id)}`}
          className={styles.practiceBtn}
        >
          <Zap size={16} />
          <span>Luyện tập dạng bài này</span>
        </Link>
        {onExploreRelations && (
          <button
            className={styles.exploreRelationsBtn}
            onClick={() => onExploreRelations(node.code)}
          >
            <Compass size={14} />
            <span>Khám phá chuỗi liên kết 3D</span>
          </button>
        )}
      </div>
    </aside>
  );
}
