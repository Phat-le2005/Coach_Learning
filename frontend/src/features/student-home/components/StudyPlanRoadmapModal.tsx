"use client";

import React, { useEffect, useState, useMemo } from "react";
import {
  Calendar,
  CheckCircle2,
  Clock,
  Compass,
  Flame,
  Milestone,
  RotateCcw,
  Sparkles,
  Target,
  X,
} from "lucide-react";
import Link from "next/link";
import styles from "./StudyPlanRoadmapModal.module.css";
import type { StudyPlanRead, StudyTaskRead } from "@/lib/api/contracts";

interface StudyPlanRoadmapModalProps {
  isOpen: boolean;
  onClose: () => void;
  subjectId?: string;
  onRecalculateDone?: () => void;
}

export function StudyPlanRoadmapModal({
  isOpen,
  onClose,
  subjectId,
  onRecalculateDone,
}: StudyPlanRoadmapModalProps) {
  const [loading, setLoading] = useState(true);
  const [plan, setPlan] = useState<StudyPlanRead | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [activeDateIndex, setActiveDateIndex] = useState(0);
  const [isRecalculating, setIsRecalculating] = useState(false);

  const fetchPlan = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch("/api/student/study-plan", {
        headers: { Accept: "application/json" },
        cache: "no-store",
      });
      if (!res.ok) {
        throw new Error("Không thể tải thông tin lộ trình.");
      }
      const data = await res.json();
      if (data.hasPlan && data.plan) {
        setPlan(data.plan);
      } else {
        setPlan(null);
      }
    } catch (err: any) {
      setError(err.message || "Không thể kết nối đến máy chủ.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (isOpen) {
      fetchPlan();
    }
  }, [isOpen]);

  const handleRecalculate = async () => {
    setIsRecalculating(true);
    try {
      const res = await fetch("/api/student/study-plan", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: "recalculate", horizon_days: 7 }),
      });
      if (!res.ok) {
        throw new Error("Không thể tính lại lộ trình.");
      }
      await fetchPlan();
      if (onRecalculateDone) {
        onRecalculateDone();
      }
    } catch (err: any) {
      setError(err.message || "Lỗi khi tái tính nhịp học.");
    } finally {
      setIsRecalculating(false);
    }
  };

  // Group tasks by planned_date
  const days = useMemo(() => {
    if (!plan || !plan.tasks || plan.tasks.length === 0) return [];

    const grouped: { [dateStr: string]: StudyTaskRead[] } = {};
    for (const task of plan.tasks) {
      const dateKey = task.planned_date;
      if (!grouped[dateKey]) {
        grouped[dateKey] = [];
      }
      grouped[dateKey].push(task);
    }

    const sortedDates = Object.keys(grouped).sort();
    return sortedDates.map((dateStr, idx) => {
      const tasks = grouped[dateStr];
      const totalMinutes = tasks.reduce((sum, t) => sum + (t.estimated_duration_minutes || 0), 0);
      const completedCount = tasks.filter((t) => t.status === "COMPLETED").length;
      return {
        dateStr,
        isToday: idx === 0,
        dayNumber: idx + 1,
        tasks,
        totalMinutes,
        completedCount,
        totalCount: tasks.length,
      };
    });
  }, [plan]);

  if (!isOpen) return null;

  const currentDay = days[activeDateIndex] || days[0];

  return (
    <div className={styles.backdrop} role="dialog" aria-modal="true" onClick={onClose}>
      <div className={styles.modal} onClick={(e) => e.stopPropagation()}>
        {/* Header */}
        <div className={styles.header}>
          <div className={styles.headerTitleWrap}>
            <div className={styles.headerIcon}>
              <Compass size={24} />
            </div>
            <div>
              <h2>Lộ trình học tập thích ứng 7 ngày</h2>
              <p>Phân bổ nhịp nhàng giữa bài tập bù đắp lỗ hổng và chu kỳ lặp lại ngắt quãng</p>
            </div>
          </div>
          <button
            type="button"
            className={styles.closeButton}
            onClick={onClose}
            aria-label="Đóng"
          >
            <X size={20} />
          </button>
        </div>

        {/* KPI Strip */}
        {plan && (
          <div className={styles.kpiStrip}>
            <div className={styles.kpiCard}>
              <div className={styles.kpiIcon} style={{ background: "rgba(35, 166, 122, 0.15)", color: "#14533f" }}>
                <Target size={18} />
              </div>
              <div className={styles.kpiText}>
                <span className={styles.kpiLabel}>Kỳ thi mục tiêu</span>
                <span className={styles.kpiValue}>TN THPT & ĐH 2026</span>
              </div>
            </div>

            <div className={styles.kpiCard}>
              <div className={styles.kpiIcon} style={{ background: "rgba(245, 158, 11, 0.15)", color: "#b45309" }}>
                <Flame size={18} />
              </div>
              <div className={styles.kpiText}>
                <span className={styles.kpiLabel}>Đếm ngược thi</span>
                <span className={styles.kpiValue}>
                  {plan.days_to_exam ? `${plan.days_to_exam} ngày` : "230 ngày"}
                </span>
              </div>
            </div>

            <div className={styles.kpiCard}>
              <div className={styles.kpiIcon} style={{ background: "rgba(59, 130, 246, 0.15)", color: "#1d4ed8" }}>
                <Clock size={18} />
              </div>
              <div className={styles.kpiText}>
                <span className={styles.kpiLabel}>Thời lượng học</span>
                <span className={styles.kpiValue}>{plan.available_daily_minutes} phút/ngày</span>
              </div>
            </div>

            <div className={styles.kpiCard}>
              <div className={styles.kpiIcon} style={{ background: "rgba(16, 185, 129, 0.15)", color: "#047857" }}>
                <Milestone size={18} />
              </div>
              <div className={styles.kpiText}>
                <span className={styles.kpiLabel}>Tiến độ 7 ngày</span>
                <span className={styles.kpiValue}>
                  {plan.completed_tasks}/{plan.total_tasks} bài ({plan.total_tasks > 0 ? Math.round((plan.completed_tasks / plan.total_tasks) * 100) : 0}%)
                </span>
              </div>
            </div>
          </div>
        )}

        {/* Day Tabs */}
        {days.length > 0 && (
          <div className={styles.dayTabsWrap}>
            {days.map((day, idx) => {
              const isSelected = idx === activeDateIndex;
              const dateObj = new Date(day.dateStr);
              const formattedDate = !isNaN(dateObj.getTime())
                ? `${dateObj.getDate()}/${dateObj.getMonth() + 1}`
                : day.dateStr;

              return (
                <button
                  key={day.dateStr}
                  type="button"
                  className={`${styles.dayTab} ${isSelected ? styles.dayTabActive : ""}`}
                  onClick={() => setActiveDateIndex(idx)}
                >
                  <span className={styles.dayTabTitle}>
                    {day.isToday ? "Hôm nay" : `Ngày ${day.dayNumber}`}
                  </span>
                  <span className={styles.dayTabSub}>{formattedDate}</span>
                  {day.isToday ? (
                    <span className={styles.dayBadgeToday}>Hiện tại</span>
                  ) : (
                    <span className={styles.dayTabSub}>
                      {day.completedCount}/{day.totalCount} bài
                    </span>
                  )}
                </button>
              );
            })}
          </div>
        )}

        {/* Body content */}
        <div className={styles.body}>
          {loading ? (
            <div style={{ textAlign: "center", padding: "40px" }}>
              <div style={{ color: "#23a67a", fontWeight: 700 }}>🌱 Đang mở lộ trình học tập...</div>
            </div>
          ) : error ? (
            <div style={{ textAlign: "center", padding: "30px", color: "#b91c1c" }}>
              <p>{error}</p>
              <button
                type="button"
                onClick={fetchPlan}
                className={styles.recalcButton}
                style={{ marginTop: "12px" }}
              >
                Thử lại
              </button>
            </div>
          ) : !plan || days.length === 0 ? (
            <div className={styles.emptyDayState}>
              <Sparkles size={36} color="#23a67a" style={{ margin: "0 auto 12px" }} />
              <h3>Chưa có dữ liệu lộ trình học tập</h3>
              <p>Hãy gieo mục tiêu học tập để hệ thống tự động sinh lộ trình 7 ngày thích ứng.</p>
            </div>
          ) : (
            <div>
              <div className={styles.daySectionHeading}>
                <span className={styles.daySectionTitle}>
                  {currentDay?.isToday
                    ? `🎯 Nhiệm vụ học tập Hôm nay (${currentDay?.dateStr})`
                    : `📅 Kế hoạch Ngày ${currentDay?.dayNumber} (${currentDay?.dateStr})`}
                </span>
                <span className={styles.daySectionMinutes}>
                  ⏱️ Tổng: {currentDay?.totalMinutes || 0} phút ước tính
                </span>
              </div>

              <div className={styles.taskList}>
                {currentDay?.tasks.map((task) => {
                  const isDone = task.status === "COMPLETED";

                  let typeLabel = "✍️ Luyện dạng toán";
                  let typeClass = styles.typePractice;
                  if (task.task_type === "REPAIR" || task.task_type === "REMEDIAL_PRACTICE") {
                    typeLabel = "🛠️ Vá lỗ hổng";
                    typeClass = styles.typeRemedial;
                  } else if (task.task_type === "REVIEW" || task.task_type === "SPACED_REVIEW") {
                    typeLabel = "🔄 Ôn ngắt quãng";
                    typeClass = styles.typeReview;
                  } else if (task.task_type === "LEARN" || task.task_type === "CONCEPT_ACQUISITION") {
                    typeLabel = "📖 Bài trọng tâm";
                    typeClass = styles.typeConcept;
                  } else if (task.task_type === "MINI_TEST") {
                    typeLabel = "🏆 Kiểm tra ngắn";
                    typeClass = styles.typeRemedial;
                  } else if (task.task_type === "EXAM") {
                    typeLabel = "📝 Luyện đề";
                    typeClass = styles.typeReview;
                  }

                  let reasonNote = "";
                  if (task.reason_code === "PREREQUISITE_REPAIR" || task.reason_code === "LOW_MASTERY_PREREQUISITE") {
                    reasonNote = "Phát hiện lỗ hổng ở bước tiên quyết, cần củng cố ngay";
                  } else if (task.reason_code === "REVIEW_DUE" || task.reason_code === "SCHEDULED_REVIEW") {
                    reasonNote = "Chu kỳ củng cố trí nhớ dài hạn (Spaced Repetition)";
                  } else if (task.reason_code === "WEAK_PROBLEM_TYPE") {
                    reasonNote = "Dạng bài chưa đạt ngưỡng vững 50%, cần tăng độ thuần thục";
                  } else if (task.reason_code === "CURRENT_TEACHING_PLAN") {
                    reasonNote = "Nội dung trọng tâm theo phân phối chương trình của lớp";
                  } else if (task.reason_code === "DIAGNOSTIC_FOLLOWUP") {
                    reasonNote = "Luyện tập bổ trợ sau chẩn đoán lỗi sai ở bài làm gần nhất";
                  } else if (task.reason_code === "EXAM_PREPARATION") {
                    reasonNote = "Ôn tập tổng hợp chuẩn bị cho kỳ thi THPT & Đại học 2026";
                  }

                  const title =
                    task.problem_type_name ||
                    task.concept_name ||
                    task.topic_name ||
                    "Bài tập rèn luyện năng lực";

                  const practiceUrl = task.problem_type_id
                    ? `/student/practice?problem_type_id=${task.problem_type_id}${subjectId ? `&subject_id=${subjectId}` : ""}`
                    : `/student/practice${subjectId ? `?subject_id=${subjectId}` : ""}`;

                  return (
                    <div
                      key={task.id}
                      className={`${styles.taskCard} ${isDone ? styles.taskCardCompleted : ""}`}
                    >
                      <div className={styles.taskLeft}>
                        <div
                          className={styles.taskCheckIcon}
                          style={{
                            background: isDone ? "rgba(35, 166, 122, 0.2)" : "rgba(9, 45, 37, 0.08)",
                            color: isDone ? "#14533f" : "#6b7280",
                          }}
                        >
                          {isDone ? <CheckCircle2 size={18} /> : <Clock size={16} />}
                        </div>
                        <div className={styles.taskInfo}>
                          <div className={styles.taskPillsRow}>
                            <span className={`${styles.taskTypeBadge} ${typeClass}`}>
                              {typeLabel}
                            </span>
                            <span className={styles.durationBadge}>
                              {task.estimated_duration_minutes} phút
                            </span>
                            {task.priority === 1 && (
                              <span
                                style={{
                                  fontSize: "0.68rem",
                                  fontWeight: 700,
                                  color: "#b45309",
                                  background: "#fef3c7",
                                  padding: "2px 6px",
                                  borderRadius: "4px",
                                }}
                              >
                                Ưu tiên cao
                              </span>
                            )}
                          </div>
                          <h4 className={styles.taskTitle}>{title}</h4>
                          {(task.chapter_name || task.topic_name) && (
                            <span className={styles.taskBreadcrumb}>
                              {task.chapter_name ? `${task.chapter_name} › ` : ""}
                              {task.topic_name || ""}
                            </span>
                          )}
                          {reasonNote && (
                            <span className={styles.taskReasonNote}>💡 {reasonNote}</span>
                          )}
                        </div>
                      </div>

                      <div className={styles.taskActionWrap}>
                        {isDone ? (
                          <span className={styles.completedBadge}>
                            <CheckCircle2 size={14} />
                            Đã xong
                          </span>
                        ) : (
                          <Link
                            href={practiceUrl}
                            className={styles.practiceButton}
                            onClick={onClose}
                          >
                            ✍️ Luyện ngay
                          </Link>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className={styles.footer}>
          <button
            type="button"
            className={styles.recalcButton}
            onClick={handleRecalculate}
            disabled={isRecalculating}
            title="Tái cân bằng nhịp học và phân bổ lại bài tập theo kết quả làm bài gần nhất"
          >
            <RotateCcw size={14} />
            {isRecalculating ? "Đang tính lại lộ trình..." : "Tái tính nhịp học 7 ngày"}
          </button>
          <button type="button" className={styles.closeFooterButton} onClick={onClose}>
            Đóng
          </button>
        </div>
      </div>
    </div>
  );
}
