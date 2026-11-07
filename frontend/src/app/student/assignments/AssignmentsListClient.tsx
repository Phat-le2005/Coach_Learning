"use client";

import { useState } from "react";
import Link from "next/link";
import {
  BookOpen,
  Calendar,
  CheckCircle2,
  Clock,
  FileCheck,
  FileText,
  GraduationCap,
  Layers,
  Sparkles,
} from "lucide-react";

import styles from "./assignments.module.css";

export interface StudentAssignmentItem {
  id: string;
  assignment_id: string;
  title: string;
  description?: string | null;
  assignment_type: string;
  delivery_mode: "PRACTICE" | "EXAM";
  status: "NOT_STARTED" | "IN_PROGRESS" | "SUBMITTED" | "GRADED";
  question_count: number;
  due_at?: string | null;
  score?: number | null;
  questions?: any[];
}

export interface AssignmentsListClientProps {
  initialAssignments: StudentAssignmentItem[];
  studentName?: string;
}

export function AssignmentsListClient({
  initialAssignments,
  studentName = "Học sinh",
}: AssignmentsListClientProps) {
  const [activeFilter, setActiveFilter] = useState<string>("ALL");

  const filtered = initialAssignments.filter((a) => {
    if (activeFilter === "ALL") return true;
    if (activeFilter === "PENDING") return a.status === "NOT_STARTED" || a.status === "IN_PROGRESS";
    if (activeFilter === "SUBMITTED") return a.status === "SUBMITTED";
    if (activeFilter === "GRADED") return a.status === "GRADED";
    return true;
  });

  const getStatusBadge = (status: string) => {
    switch (status) {
      case "NOT_STARTED":
        return <span className={`${styles.statusPill} ${styles.statusNotStarted}`}>Chưa bắt đầu</span>;
      case "IN_PROGRESS":
        return <span className={`${styles.statusPill} ${styles.statusInProgress}`}>Đang làm</span>;
      case "SUBMITTED":
        return <span className={`${styles.statusPill} ${styles.statusSubmitted}`}>Đã nộp · Chờ duyệt</span>;
      case "GRADED":
        return <span className={`${styles.statusPill} ${styles.statusGraded}`}>Đã chấm điểm</span>;
      default:
        return <span className={styles.statusPill}>{status}</span>;
    }
  };

  const formatScore = (score: number | null | undefined) => {
    if (score === null || score === undefined) return null;
    const val = score <= 1.0 ? score * 10 : score;
    return val % 1 === 0 ? val.toFixed(0) : val.toFixed(1);
  };

  return (
    <div className={styles.canvas}>
      <main className={styles.mainContainer}>
        {/* Header Banner */}
        <div className={styles.headerBanner}>
          <div>
            <h1 className={styles.headerTitle}>
              <GraduationCap size={28} color="#059669" />
              Bảng bài tập từ lớp
            </h1>
            <p className={styles.headerSubtitle}>
              Chào {studentName}! Đây là danh sách các bài luyện tập và đề thi do Giáo viên giao cho lớp của bạn.
            </p>
          </div>
          <Link href="/student" className={styles.btnActionSecondary}>
            🌱 Về Khu vườn học tập
          </Link>
        </div>

        {/* Filter Tabs */}
        <div className={styles.filterTabs}>
          <button
            type="button"
            className={`${styles.filterTabBtn} ${activeFilter === "ALL" ? styles.filterTabBtnActive : ""}`}
            onClick={() => setActiveFilter("ALL")}
          >
            Tất cả ({initialAssignments.length})
          </button>
          <button
            type="button"
            className={`${styles.filterTabBtn} ${activeFilter === "PENDING" ? styles.filterTabBtnActive : ""}`}
            onClick={() => setActiveFilter("PENDING")}
          >
            Cần làm ngay ({initialAssignments.filter((a) => a.status === "NOT_STARTED" || a.status === "IN_PROGRESS").length})
          </button>
          <button
            type="button"
            className={`${styles.filterTabBtn} ${activeFilter === "SUBMITTED" ? styles.filterTabBtnActive : ""}`}
            onClick={() => setActiveFilter("SUBMITTED")}
          >
            Chờ duyệt ({initialAssignments.filter((a) => a.status === "SUBMITTED").length})
          </button>
          <button
            type="button"
            className={`${styles.filterTabBtn} ${activeFilter === "GRADED" ? styles.filterTabBtnActive : ""}`}
            onClick={() => setActiveFilter("GRADED")}
          >
            Đã có điểm ({initialAssignments.filter((a) => a.status === "GRADED").length})
          </button>
        </div>

        {/* Assignments Cards Grid */}
        {filtered.length === 0 ? (
          <div className={styles.emptyState}>
            <div className={styles.emptyIcon}>📚</div>
            <h3>Không có bài tập nào trong mục này</h3>
            <p>Tuyệt vời! Bạn đã hoàn thành các nhiệm vụ được giao hoặc chưa có bài tập mới.</p>
            <Link href="/student" className={styles.btnAction} style={{ marginTop: "1rem" }}>
              Tiếp tục luyện tập cá nhân
            </Link>
          </div>
        ) : (
          <div className={styles.cardsGrid}>
            {filtered.map((item) => {
              const formattedScore = formatScore(item.score);
              const isExam = item.delivery_mode === "EXAM";
              const isDone = item.status === "GRADED" || item.status === "SUBMITTED";

              return (
                <div key={item.id} className={styles.assignmentCard}>
                  <div className={styles.cardTopRow}>
                    {isExam ? (
                      <span className={styles.modeBadgeExam}>
                        <FileCheck size={14} />
                        Kiểm tra tập trung
                      </span>
                    ) : (
                      <span className={styles.modeBadgePractice}>
                        <Sparkles size={14} />
                        Luyện tập từng câu
                      </span>
                    )}
                    {getStatusBadge(item.status)}
                  </div>

                  <h3 className={styles.cardTitle}>{item.title}</h3>
                  {item.description && (
                    <p className={styles.cardDescription}>{item.description}</p>
                  )}

                  <div className={styles.cardMetaRow}>
                    <div className={styles.metaItem}>
                      <Layers size={14} />
                      <span>{item.question_count} câu hỏi</span>
                    </div>
                    {item.due_at && (
                      <div className={styles.metaItem}>
                        <Calendar size={14} />
                        <span>Hạn: {new Date(item.due_at).toLocaleDateString("vi-VN")}</span>
                      </div>
                    )}
                  </div>

                  <div className={styles.cardFooter}>
                    {formattedScore !== null ? (
                      <div className={styles.scoreBadgeBig}>
                        {formattedScore}
                        <span className={styles.scoreScale}>/10đ</span>
                      </div>
                    ) : (
                      <div style={{ fontSize: "0.8125rem", color: "#94A3B8" }}>
                        {item.status === "SUBMITTED" ? "Chờ giáo viên duyệt" : "Chưa chấm điểm"}
                      </div>
                    )}

                    <Link
                      href={`/student/assignments/${item.id}`}
                      className={isDone ? styles.btnActionSecondary : styles.btnAction}
                    >
                      {item.status === "GRADED" ? (
                        <>
                          <CheckCircle2 size={15} />
                          Xem kết quả
                        </>
                      ) : item.status === "SUBMITTED" ? (
                        <>
                          <FileText size={15} />
                          Xem bài nộp
                        </>
                      ) : (
                        <>
                          <BookOpen size={15} />
                          Vào làm bài
                        </>
                      )}
                    </Link>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </main>
    </div>
  );
}
