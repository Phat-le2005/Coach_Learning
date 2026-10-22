"use client";

import React, { useState } from "react";
import {
  PenTool,
  CheckCircle2,
  AlertCircle,
  Clock,
  Sparkles,
  Layers,
  MessageSquare,
  Send,
  Eye,
  FileCheck,
} from "lucide-react";
import { MathRenderer } from "@/components/ui/MathRenderer";
import type { StudentAttemptInspection } from "../types";
import styles from "../TeacherDashboard.module.css";

interface StudentWorkspaceTabProps {
  attempts: StudentAttemptInspection[];
  selectedStudentId?: string;
}

export function StudentWorkspaceTab({
  attempts,
  selectedStudentId,
}: StudentWorkspaceTabProps) {
  const initialIndex = selectedStudentId
    ? Math.max(0, attempts.findIndex((a) => a.studentId === selectedStudentId))
    : 0;

  const [activeAttemptIndex, setActiveAttemptIndex] = useState(initialIndex);
  const [teacherNoteInput, setTeacherNoteInput] = useState("");
  const [savedNotes, setSavedNotes] = useState<Record<string, string>>({});

  const currentAttempt = attempts[activeAttemptIndex] || attempts[0];

  const handleSaveNote = () => {
    if (!teacherNoteInput.trim() || !currentAttempt) return;
    setSavedNotes((prev) => ({
      ...prev,
      [currentAttempt.attemptId]: teacherNoteInput.trim(),
    }));
    setTeacherNoteInput("");
  };

  const currentNote = currentAttempt
    ? savedNotes[currentAttempt.attemptId] || currentAttempt.teacherNote
    : "";

  return (
    <div>
      {/* View Header */}
      <div className={styles.viewHeader}>
        <div className={styles.viewTitleGroup}>
          <h2 className={styles.viewTitle}>Trang giám sát bài làm học sinh</h2>
          <span className={styles.viewSubtitle}>
            Kiểm tra nét vẽ bảng viết tay (Canvas Ink), các bước giải trích xuất AI OCR và nhận xét sư phạm
          </span>
        </div>

        <div className={styles.viewActions}>
          <span style={{ fontSize: "0.82rem", color: "var(--text-secondary)" }}>
            Đang hiển thị lượt giải của: <strong style={{ color: "var(--verdant-800)" }}>{currentAttempt?.studentName}</strong>
          </span>
        </div>
      </div>

      <div className={styles.inspectorGrid}>
        {/* Left: Attempt Selector List */}
        <div className={styles.attemptList}>
          <div style={{ fontSize: "0.78rem", fontWeight: 700, color: "var(--text-tertiary)", textTransform: "uppercase", marginBottom: "0.25rem" }}>
            Danh sách bài nộp gần đây ({attempts.length})
          </div>

          {attempts.map((att, idx) => {
            const isActive = idx === activeAttemptIndex;
            return (
              <div
                key={att.attemptId}
                className={`${styles.attemptItem} ${isActive ? styles.attemptItemActive : ""}`}
                onClick={() => setActiveAttemptIndex(idx)}
              >
                <div className={styles.attemptTop}>
                  <span className={styles.attemptStudentName}>{att.studentName}</span>
                  <span
                    className={`${styles.statusPill} ${
                      att.status === "EVALUATED"
                        ? styles.statusPillActive
                        : att.status === "SUBMITTED"
                        ? styles.statusIconSky
                        : styles.statusPillInactive
                    }`}
                  >
                    {att.status === "IN_PROGRESS"
                      ? "Đang làm"
                      : att.status === "SUBMITTED"
                      ? "Đã nộp"
                      : "Đã chấm"}
                  </span>
                </div>

                <div className={styles.attemptProblemTitle}>{att.problemTitle}</div>

                <div className={styles.attemptMetaRow}>
                  <span>{att.strokesCount} nét viết tay</span>
                  <span>{att.lastActive}</span>
                </div>
              </div>
            );
          })}
        </div>

        {/* Right: Detailed Inspection Pane */}
        {currentAttempt ? (
          <div className={styles.workspaceDetail}>
            {/* Header info */}
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: "1rem", borderBottom: "1px solid var(--border-soft)", paddingBottom: "0.75rem" }}>
              <div>
                <h3 style={{ margin: "0 0 0.25rem", fontSize: "1.15rem", fontWeight: 700 }}>
                  {currentAttempt.studentName} — {currentAttempt.problemTitle}
                </h3>
                <span style={{ fontSize: "0.8rem", color: "var(--text-secondary)" }}>
                  Phiên bản bài làm: v{currentAttempt.revision} • Cập nhật lần cuối: {currentAttempt.lastActive}
                </span>
              </div>

              {currentAttempt.score !== undefined && (
                <div style={{ textAlign: "right" }}>
                  <span style={{ fontSize: "0.72rem", color: "var(--text-tertiary)", display: "block" }}>Điểm đánh giá</span>
                  <span style={{ fontSize: "1.4rem", fontWeight: 800, color: "var(--verdant-800)" }}>
                    {currentAttempt.score} <span style={{ fontSize: "0.85rem", fontWeight: 600 }}>/ 10</span>
                  </span>
                </div>
              )}
            </div>

            {/* Problem Statement Box */}
            <div className={styles.problemBox}>
              <div className={styles.problemBoxTitle}>Đề bài giao học sinh</div>
              <div className={styles.problemBoxContent}>
                <MathRenderer content={currentAttempt.problemContent} />
              </div>
            </div>

            {/* Handwritten Canvas Visualizer */}
            <div className={styles.canvasPreviewCard}>
              <div className={styles.canvasPreviewHeader}>
                <span style={{ display: "flex", alignItems: "center", gap: "0.35rem" }}>
                  <PenTool size={14} style={{ color: "var(--verdant-700)" }} />
                  Bảng viết tay học sinh (Toán Ink • {currentAttempt.strokesCount} nét vector)
                </span>
                <span style={{ color: "var(--text-tertiary)", fontSize: "0.74rem" }}>
                  Trang 1 / 1 (Khổ chuẩn A4)
                </span>
              </div>

              <div className={styles.canvasVisualArea}>
                {/* Visual Representation of Handwriting */}
                <div className={styles.handwrittenSample}>
                  {currentAttempt.drawnFormulaPreview}
                </div>
              </div>

              <div style={{ fontSize: "0.74rem", color: "var(--text-secondary)", textAlign: "center", borderTop: "1px solid rgba(0,0,0,0.06)", paddingTop: "0.5rem" }}>
                Nét vẽ được học sinh vẽ trực tiếp trên canvas và đồng bộ từng phần tử điểm vector lên PostgreSQL.
              </div>
            </div>

            {/* Steps Breakdown Section */}
            <div className={styles.stepsSectionTitle}>
              <Layers size={18} style={{ color: "var(--verdant-800)" }} />
              Các bước giải toán được AI OCR trích xuất & chẩn đoán ({currentAttempt.steps.length} bước)
            </div>

            <div>
              {currentAttempt.steps.map((st) => (
                <div
                  key={st.stepIndex}
                  className={`${styles.stepCard} ${
                    st.status === "ERROR"
                      ? styles.stepCardError
                      : st.status === "PENDING"
                      ? styles.stepCardPending
                      : ""
                  }`}
                >
                  <div className={styles.stepTop}>
                    <span className={styles.stepKindName}>
                      Bước {st.stepIndex}: {st.stepKind}
                    </span>
                    <span
                      style={{
                        fontSize: "0.72rem",
                        fontWeight: 700,
                        padding: "0.15rem 0.5rem",
                        borderRadius: "999px",
                        backgroundColor:
                          st.status === "VERIFIED"
                            ? "var(--mint-100)"
                            : st.status === "ERROR"
                            ? "#fee2e2"
                            : "#fef3c7",
                        color:
                          st.status === "VERIFIED"
                            ? "var(--verdant-800)"
                            : st.status === "ERROR"
                            ? "#991b1b"
                            : "#92400e",
                      }}
                    >
                      {st.status === "VERIFIED"
                        ? "Hợp lệ"
                        : st.status === "ERROR"
                        ? "Sai sót"
                        : "Chờ duyệt"}
                    </span>
                  </div>

                  <div className={styles.stepLatexRender}>
                    <MathRenderer content={`$$${st.latex}$$`} />
                  </div>

                  <div className={styles.stepExplanation}>{st.explanation}</div>

                  {st.aiFeedback && (
                    <div className={styles.stepAiFeedback}>
                      <Sparkles size={14} style={{ color: "var(--verdant-700)", flexShrink: 0 }} />
                      <span>{st.aiFeedback}</span>
                    </div>
                  )}
                </div>
              ))}
            </div>

            {/* Teacher Notes & Pedagogical Feedback */}
            <div className={styles.teacherNoteArea}>
              <div className={styles.noteTitle}>
                <MessageSquare size={16} />
                Nhận xét & Dặn dò sư phạm của giáo viên
              </div>

              {currentNote ? (
                <p className={styles.noteContent}>{currentNote}</p>
              ) : (
                <p className={styles.noteContent} style={{ fontStyle: "italic", color: "var(--text-tertiary)" }}>
                  Chưa có lời nhận xét nào cho bài làm này.
                </p>
              )}

              {/* Add Note Form */}
              <div style={{ display: "flex", gap: "0.5rem", marginTop: "0.75rem" }}>
                <input
                  type="text"
                  className={styles.formInput}
                  placeholder="Gửi thêm lời nhắc hoặc hướng dẫn sửa bước giải cho học sinh..."
                  value={teacherNoteInput}
                  onChange={(e) => setTeacherNoteInput(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") handleSaveNote();
                  }}
                />
                <button
                  type="button"
                  className={styles.btnPrimary}
                  style={{ whiteSpace: "nowrap", padding: "0.5rem 0.85rem" }}
                  onClick={handleSaveNote}
                >
                  <Send size={14} />
                  Gửi nhận xét
                </button>
              </div>
            </div>
          </div>
        ) : null}
      </div>
    </div>
  );
}
