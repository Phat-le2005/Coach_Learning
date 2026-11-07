"use client";

import {
  AlertTriangle,
  ArrowRight,
  BookOpen,
  CheckCircle2,
  Clock,
  Compass,
  Lock,
  ShieldCheck,
  Sparkles,
  Target,
  X,
  Zap,
} from "lucide-react";
import Link from "next/link";
import { useEffect, useRef } from "react";

import { getMasteryStateLabel } from "../copy";
import {
  getPostrequisitesForProblemType,
  getPrerequisitesForProblemType,
} from "../prerequisite-graph";
import type { KnowledgeProblemTypeNode } from "../types";
import styles from "../KnowledgeWorld3D.module.css";

export interface KnowledgeDetailPanelProps {
  node: KnowledgeProblemTypeNode | null;
  subjectId?: string;
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
  MONOTONICITY_FROM_EXPRESSION: {
    summary: "Tìm TXĐ D, tính đạo hàm y' = f'(x), giải f'(x) = 0, lập bảng xét dấu đạo hàm và kết luận khoảng đơn điệu.",
    formula: "y' = f'(x) = 0 \\implies \\text{Lập bảng biến thiên}",
  },
  COMPLETE_FUNCTION_ANALYSIS_CUBIC: {
    summary: "Khảo sát sự biến thiên và vẽ đồ thị hàm số bậc ba y = ax³ + bx² + cx + d (a ≠ 0) qua 5 bước chuẩn.",
    formula: "y = ax^3 + bx^2 + cx + d \\implies y' = 3ax^2 + 2bx + c",
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
  subjectId,
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

  const scopeState = node.scopeState ?? "UNLOCKED";
  const scopeLabel =
    node.teacherScopeLabel ??
    (scopeState === "CURRENT_TEACHING"
      ? "Giáo viên đang dạy & giao bài"
      : scopeState === "FOG_OF_WAR"
      ? "Sương mù tri thức — Giáo viên chưa dạy tới"
      : "Nền tảng đã mở khóa");

  const relatedConcepts = node.relatedConcepts ?? [];
  const recommendedTasks = node.recommendedTasks ?? [];
  const weakConcepts = relatedConcepts.filter((c) => c.isWeakPrerequisite);

  const buildPracticeHref = (conceptId?: string) => {
    const params = new URLSearchParams();
    params.set("problem_type_id", node.id);
    if (conceptId) params.set("concept_id", conceptId);
    if (subjectId) params.set("subject_id", subjectId);
    return `/student/practice?${params.toString()}`;
  };

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
        {/* 1. Teacher Curriculum Scope Banner */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: "8px",
            padding: "8px 12px",
            borderRadius: "10px",
            fontSize: "11.5px",
            fontWeight: 600,
            background:
              scopeState === "CURRENT_TEACHING"
                ? "rgba(250, 204, 21, 0.14)"
                : scopeState === "FOG_OF_WAR"
                ? "rgba(51, 65, 85, 0.45)"
                : "rgba(35, 166, 122, 0.14)",
            border:
              scopeState === "CURRENT_TEACHING"
                ? "1px solid rgba(250, 204, 21, 0.4)"
                : scopeState === "FOG_OF_WAR"
                ? "1px solid rgba(148, 163, 184, 0.28)"
                : "1px solid rgba(139, 229, 194, 0.3)",
            color:
              scopeState === "CURRENT_TEACHING"
                ? "#fde047"
                : scopeState === "FOG_OF_WAR"
                ? "#cbd5e1"
                : "#8be5c2",
          }}
        >
          {scopeState === "CURRENT_TEACHING" ? (
            <Sparkles size={14} color="#fde047" style={{ flexShrink: 0 }} />
          ) : scopeState === "FOG_OF_WAR" ? (
            <Lock size={14} color="#94a3b8" style={{ flexShrink: 0 }} />
          ) : (
            <CheckCircle2 size={14} color="#8be5c2" style={{ flexShrink: 0 }} />
          )}
          <span>{scopeLabel}</span>
        </div>

        {/* 2. Step-Grounded Mastery Backdrop Card */}
        <div
          className={styles.stateCard}
          style={{ flexDirection: "column", alignItems: "stretch", gap: "10px" }}
        >
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
            <div className={styles.stateBadge}>
              <span
                className={styles.stateDot}
                style={{
                  background:
                    node.state === "WEAK"
                      ? "#f87171"
                      : node.state === "MASTERED"
                      ? "#22c55e"
                      : "#23a67a",
                  boxShadow:
                    node.state === "WEAK"
                      ? "0 0 8px #f87171"
                      : "0 0 8px #23a67a",
                }}
              />
              <span>{stateLabel}</span>
            </div>
            <div className={styles.stateScore}>
              {node.masteryScore !== undefined ? `${node.masteryScore}%` : "Chưa tích lũy"}
            </div>
          </div>

          {/* Visual Mastery Progress Bar */}
          <div
            style={{
              width: "100%",
              height: "6px",
              borderRadius: "999px",
              background: "rgba(255, 255, 255, 0.08)",
              overflow: "hidden",
            }}
          >
            <div
              style={{
                width: `${Math.min(100, Math.max(0, node.masteryScore ?? 0))}%`,
                height: "100%",
                borderRadius: "999px",
                background:
                  node.state === "WEAK"
                    ? "linear-gradient(90deg, #ef4444, #f59e0b)"
                    : "linear-gradient(90deg, #10b981, #34d399)",
                transition: "width 0.35s ease",
              }}
            />
          </div>

          {/* Stats Strip */}
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "1fr 1fr",
              gap: "8px",
              fontSize: "11.5px",
              color: "rgba(247, 247, 238, 0.78)",
            }}
          >
            <div
              style={{
                background: "rgba(5, 25, 20, 0.45)",
                padding: "7px 10px",
                borderRadius: "8px",
                display: "flex",
                alignItems: "center",
                gap: "6px",
              }}
            >
              <Target size={13} color="#8be5c2" />
              <span>
                {node.attemptCount} lượt giải ({node.correctCount ?? 0} chuẩn)
              </span>
            </div>
            <div
              style={{
                background: "rgba(5, 25, 20, 0.45)",
                padding: "7px 10px",
                borderRadius: "8px",
                display: "flex",
                alignItems: "center",
                gap: "6px",
              }}
            >
              <ShieldCheck size={13} color="#67bfd4" />
              <span>
                Độ tin cậy AI: {node.confidence !== undefined ? `${node.confidence}%` : "Mới"}
              </span>
            </div>
          </div>

          <div
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              fontSize: "11px",
              color: "rgba(247, 247, 238, 0.58)",
            }}
          >
            <span style={{ display: "flex", alignItems: "center", gap: "5px" }}>
              <Clock size={12} color="#67bfd4" />
              Cập nhật từ bài làm: {formattedDate}
            </span>
          </div>
        </div>

        {/* 3. AI Diagnostic & Prerequisite Concept Root-Cause */}
        {(node.diagnosticSummary || relatedConcepts.length > 0) && (
          <div className={styles.sectionBlock}>
            <div
              className={styles.sectionHeading}
              style={{ color: weakConcepts.length > 0 ? "#fca5a5" : "#67e8f9" }}
            >
              {weakConcepts.length > 0 ? (
                <AlertTriangle size={14} color="#f87171" />
              ) : (
                <Sparkles size={14} color="#67e8f9" />
              )}
              <span>Chẩn đoán AI & Khái niệm gốc</span>
            </div>

            {node.diagnosticSummary && (
              <div
                style={{
                  background:
                    weakConcepts.length > 0
                      ? "rgba(239, 68, 68, 0.12)"
                      : "rgba(6, 182, 212, 0.1)",
                  border:
                    weakConcepts.length > 0
                      ? "1px solid rgba(248, 113, 113, 0.35)"
                      : "1px solid rgba(103, 232, 249, 0.25)",
                  borderRadius: "10px",
                  padding: "10px 12px",
                  fontSize: "12px",
                  lineHeight: 1.5,
                  color: "#f7f7ee",
                }}
              >
                {node.diagnosticSummary}
              </div>
            )}

            {relatedConcepts.length > 0 && (
              <div className={styles.prereqList}>
                {relatedConcepts.map((concept) => (
                  <div
                    key={concept.id}
                    className={styles.prereqItem}
                    style={{
                      justifyContent: "space-between",
                      borderColor: concept.isWeakPrerequisite
                        ? "rgba(248, 113, 113, 0.4)"
                        : "rgba(139, 229, 194, 0.14)",
                      background: concept.isWeakPrerequisite
                        ? "rgba(127, 29, 29, 0.25)"
                        : "rgba(5, 25, 20, 0.5)",
                    }}
                  >
                    <div style={{ display: "flex", flexDirection: "column", gap: "2px" }}>
                      <span style={{ fontWeight: 600, fontSize: "12px", color: "#f7f7ee" }}>
                        {concept.name}
                      </span>
                      <span
                        style={{
                          fontSize: "10.5px",
                          color: concept.isWeakPrerequisite ? "#fca5a5" : "#8be5c2",
                        }}
                      >
                        {concept.masteryScore !== undefined
                          ? `Thành thạo khái niệm: ${concept.masteryScore}%`
                          : "Chưa đo lường"}
                        {concept.isWeakPrerequisite ? " • Lỗ hổng gốc" : ""}
                      </span>
                    </div>

                    {concept.isWeakPrerequisite && (
                      <Link
                        href={buildPracticeHref(concept.id)}
                        style={{
                          fontSize: "11px",
                          fontWeight: 700,
                          color: "#fef08a",
                          background: "rgba(234, 179, 8, 0.2)",
                          border: "1px solid rgba(250, 204, 21, 0.4)",
                          padding: "4px 8px",
                          borderRadius: "6px",
                          textDecoration: "none",
                          whiteSpace: "nowrap",
                        }}
                      >
                        Bù lỗ hổng →
                      </Link>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* 4. Adaptive Practice Pathway using System Exercises */}
        {recommendedTasks.length > 0 && (
          <div className={styles.sectionBlock}>
            <div className={styles.sectionHeading} style={{ color: "#8be5c2" }}>
              <Zap size={14} color="#8be5c2" />
              <span>Lộ trình luyện bài tập hệ thống ({recommendedTasks.length} bước)</span>
            </div>
            <div className={styles.prereqList}>
              {recommendedTasks.map((task, idx) => (
                <Link
                  key={task.id}
                  href={buildPracticeHref(task.conceptId)}
                  style={{
                    textDecoration: "none",
                    background:
                      task.taskType === "REPAIR"
                        ? "rgba(234, 179, 8, 0.12)"
                        : "rgba(35, 166, 122, 0.14)",
                    border:
                      task.taskType === "REPAIR"
                        ? "1px solid rgba(250, 204, 21, 0.35)"
                        : "1px solid rgba(139, 229, 194, 0.28)",
                    borderRadius: "10px",
                    padding: "10px 12px",
                    display: "flex",
                    flexDirection: "column",
                    gap: "4px",
                    transition: "all 0.2s ease",
                  }}
                >
                  <div
                    style={{
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "space-between",
                      gap: "8px",
                    }}
                  >
                    <span
                      style={{
                        fontSize: "10.5px",
                        fontWeight: 700,
                        textTransform: "uppercase",
                        letterSpacing: "0.04em",
                        color: task.taskType === "REPAIR" ? "#fde047" : "#8be5c2",
                      }}
                    >
                      Bước {idx + 1} •{" "}
                      {task.taskType === "REPAIR"
                        ? "Bù khái niệm gốc"
                        : task.taskType === "REVIEW"
                        ? "Ôn tập củng cố"
                        : "Luyện bài hệ thống"}
                    </span>
                    <ArrowRight size={13} color="#8be5c2" />
                  </div>
                  <div style={{ fontSize: "12.5px", fontWeight: 700, color: "#f7f7ee" }}>
                    {task.title}
                  </div>
                  <div style={{ fontSize: "11px", color: "rgba(247, 247, 238, 0.72)", lineHeight: 1.4 }}>
                    {task.subtitle || task.rationale}
                  </div>
                </Link>
              ))}
            </div>
          </div>
        )}

        {/* 5. Theory & Key Formula */}
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
          <div style={{ marginTop: "10px" }}>
            <Link
              href={`/student/theory?topic=${encodeURIComponent(node.topicName || node.name)}`}
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: "6px",
                fontSize: "11.5px",
                fontWeight: 600,
                color: "#8be5c2",
                textDecoration: "none",
                background: "rgba(35, 166, 122, 0.12)",
                border: "1px solid rgba(139, 229, 194, 0.25)",
                padding: "6px 10px",
                borderRadius: "8px",
              }}
            >
              <BookOpen size={13} aria-hidden="true" />
              <span>Xem Sơ đồ tư duy & Trích xuất PDF →</span>
            </Link>
          </div>
        </div>

        {/* 6. Prerequisites in 3D Graph */}
        {prereqs.length > 0 && (
          <div className={styles.sectionBlock}>
            <div className={styles.sectionHeading}>
              <Sparkles size={14} />
              <span>Nhánh rễ tiên quyết 3D ({prereqs.length})</span>
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

        {/* 7. Unlocks / Postrequisites in 3D Graph */}
        {postreqs.length > 0 && (
          <div className={styles.sectionBlock}>
            <div className={styles.sectionHeading} style={{ color: "#8be5c2" }}>
              <Zap size={14} />
              <span>Mở khóa nhánh tiếp theo ({postreqs.length})</span>
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
        <Link href={buildPracticeHref()} className={styles.practiceBtn}>
          <Zap size={16} />
          <span>
            {scopeState === "FOG_OF_WAR"
              ? "Khám phá trước bằng bài tập hệ thống"
              : node.state === "WEAK"
              ? "Luyện bài hệ thống khắc phục lỗi sai"
              : "Giải bài tập hệ thống dạng này"}
          </span>
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
