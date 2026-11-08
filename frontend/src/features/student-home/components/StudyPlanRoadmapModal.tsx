"use client";

import { useCallback, useEffect, useId, useMemo, useRef, useState } from "react";
import Link from "next/link";
import type { StudyPlanRead, StudyTaskRead } from "@/lib/api/contracts";
import { homeDate, homeTaskHref, homeTaskTypeLabel } from "../home-presentation";
import { HomeIcon } from "./HomeIcon";
import styles from "./StudyPlanRoadmapModal.module.css";

interface StudyPlanRoadmapModalProps {
  isOpen: boolean; onClose: () => void; subjectId?: string; onRecalculateDone?: () => void;
}
const taskReasons: Record<string, string> = {
  PREREQUISITE_REPAIR: "Củng cố kiến thức tiên quyết", LOW_MASTERY_PREREQUISITE: "Củng cố kiến thức tiên quyết",
  REVIEW_DUE: "Đến lịch ôn tập", SCHEDULED_REVIEW: "Đến lịch ôn tập",
  WEAK_PROBLEM_TYPE: "Dạng bài cần luyện thêm", CURRENT_TEACHING_PLAN: "Trọng tâm học tập của lớp",
  DIAGNOSTIC_FOLLOWUP: "Luyện thêm sau chẩn đoán", EXAM_PREPARATION: "Ôn tập theo mục tiêu",
};

export function StudyPlanRoadmapModal({ isOpen, onClose, subjectId, onRecalculateDone }: StudyPlanRoadmapModalProps) {
  const [loading, setLoading] = useState(true);
  const [plan, setPlan] = useState<StudyPlanRead | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [activeDateIndex, setActiveDateIndex] = useState(0);
  const [isRecalculating, setIsRecalculating] = useState(false);
  const dialog = useRef<HTMLDialogElement>(null);
  const request = useRef<AbortController | null>(null);
  const titleId = useId();

  const fetchPlan = useCallback(async () => {
    request.current?.abort();
    const controller = new AbortController();
    request.current = controller;
    setLoading(true); setError(null);
    try {
      const res = await fetch("/api/student/study-plan", { headers: { Accept: "application/json" }, cache: "no-store", signal: controller.signal });
      if (!res.ok) throw new Error("Không thể tải lộ trình. Bạn có thể thử lại.");
      const data = await res.json();
      if (!controller.signal.aborted) { setPlan(data.hasPlan && data.plan ? data.plan : null); setActiveDateIndex(0); }
    } catch (reason) {
      if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : "Không thể kết nối máy chủ.");
    } finally { if (!controller.signal.aborted) setLoading(false); }
  }, []);

  useEffect(() => {
    const element = dialog.current;
    if (!isOpen) { element?.close(); request.current?.abort(); return; }
    const previousFocus = document.activeElement as HTMLElement | null;
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    element?.showModal();
    void fetchPlan();
    return () => {
      request.current?.abort(); element?.close();
      document.body.style.overflow = overflow;
      previousFocus?.focus();
    };
  }, [isOpen, fetchPlan]);

  async function recalculate() {
    if (isRecalculating) return;
    setIsRecalculating(true); setError(null);
    try {
      const res = await fetch("/api/student/study-plan", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ action: "recalculate", horizon_days: 7 }) });
      if (!res.ok) throw new Error("Chưa cập nhật được kế hoạch. Bạn có thể thử lại.");
      await fetchPlan(); onRecalculateDone?.();
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Không thể cập nhật kế hoạch."); }
    finally { setIsRecalculating(false); }
  }

  const days = useMemo(() => {
    const groups = new Map<string, StudyTaskRead[]>();
    for (const task of plan?.tasks ?? []) {
      if (task.status === "SKIPPED") continue;
      groups.set(task.planned_date, [...(groups.get(task.planned_date) ?? []), task]);
    }
    return [...groups.entries()].sort(([a], [b]) => a.localeCompare(b)).map(([date, tasks]) => ({
      date, tasks: [...tasks].sort((a, b) => a.order_index - b.order_index),
      minutes: tasks.reduce((sum, task) => sum + task.estimated_duration_minutes, 0),
      done: tasks.filter(task => task.status === "COMPLETED").length,
    }));
  }, [plan]);
  const day = days[activeDateIndex] ?? days[0];
  const countdown = plan?.days_to_exam;
  const countdownText = typeof countdown !== "number" || !Number.isFinite(countdown)
    ? "Chưa có mốc mục tiêu" : countdown > 0 ? `Còn ${countdown} ngày` : countdown === 0 ? "Đến mốc mục tiêu hôm nay" : "Đã qua mốc mục tiêu";

  return <dialog ref={dialog} className={styles.modal} aria-labelledby={titleId}
    onKeyDown={event => {
      if (event.key !== "Tab") return;
      const controls = [...event.currentTarget.querySelectorAll<HTMLElement>('button:not(:disabled),a[href],input:not(:disabled),[tabindex="0"]')].filter(el => el.getClientRects().length > 0);
      const first = controls[0], last = controls[controls.length - 1];
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
    }}
    onCancel={event => { event.preventDefault(); if (!isRecalculating) onClose(); }}
    onClick={event => { if (event.target === dialog.current && !isRecalculating) onClose(); }}>
    <header className={styles.header}><div><h2 id={titleId}>Kế hoạch học 7 ngày</h2><p>Xem nhiệm vụ và thời gian học theo từng ngày.</p></div>
      <button type="button" className={styles.iconButton} aria-label="Đóng lộ trình" disabled={isRecalculating} onClick={onClose}><HomeIcon name="x" /></button></header>
    <div className={styles.body}>
      {loading ? <p role="status">Đang tải kế hoạch học…</p> : error ? <div role="alert"><p>{error}</p><button type="button" className={styles.secondary} onClick={() => void fetchPlan()}>Thử lại</button></div> : !plan ? <p>Chưa có kế hoạch học. Bạn có thể đặt mục tiêu để bắt đầu.</p> : <>
        <dl className={styles.summary}>
          <div><dt>Mốc mục tiêu</dt><dd>{homeDate(plan.target_date) ?? "Chưa đặt ngày"}<small>{countdownText}</small></dd></div>
          <div><dt>Thời gian mỗi ngày</dt><dd>{plan.available_daily_minutes} phút</dd></div>
          <div><dt>Tiến độ kế hoạch</dt><dd>{plan.completed_tasks}/{plan.total_tasks} nhiệm vụ</dd></div>
        </dl>
        {days.length > 0 ? <>
          <div className={styles.days} role="group" aria-label="Chọn ngày trong kế hoạch">{days.map((item, index) => <button type="button" key={item.date} aria-pressed={index === activeDateIndex} onClick={() => setActiveDateIndex(index)}>{homeDate(item.date) ?? item.date}<small>{item.done}/{item.tasks.length} hoàn tất</small></button>)}</div>
          <div className={styles.dayHeading}><h3>Nhiệm vụ ngày {homeDate(day.date)}</h3><span>{day.minutes} phút dự kiến</span></div>
          <ul className={styles.tasks}>{day.tasks.map(task => <li key={task.id}>
            <HomeIcon name={task.status === "COMPLETED" ? "check-circle" : "clock"} />
            <div className={styles.taskCopy}><h4>{task.problem_type_name || task.concept_name || task.topic_name || "Nhiệm vụ học tập"}</h4><p>{homeTaskTypeLabel(task.task_type)} · {task.estimated_duration_minutes} phút{task.priority >= 110 || task.priority === 1 ? " · Ưu tiên cao" : ""}</p>{(task.chapter_name || task.topic_name) && <p>{[task.chapter_name, task.topic_name].filter(Boolean).join(" · ")}</p>}{task.reason_code && <p>{taskReasons[task.reason_code] ?? "Ưu tiên học tập"}</p>}</div>
            {task.status === "COMPLETED" ? <span className={styles.completed}>Đã hoàn thành</span> : <>
              {(task.task_type === "LEARN" || task.task_type === "CONCEPT_ACQUISITION") && <Link className={styles.taskLink} href="/student/theory" onClick={onClose}>Lý thuyết<HomeIcon name="book-open" size={16} /></Link>}
              <Link className={styles.taskLink} prefetch={false} href={homeTaskHref({ id: task.id, title: "", taskType: task.task_type, status: task.status, isCompleted: false, estimatedMinutes: task.estimated_duration_minutes, problemTypeId: task.problem_type_id, conceptId: task.concept_id }, task.subject_id ?? subjectId ?? "")} onClick={onClose}>Mở nhiệm vụ<HomeIcon name="arrow-up-right" size={16} /></Link>
            </>}
          </li>)}</ul>
        </> : <p>Chưa có nhiệm vụ trong kế hoạch này.</p>}
      </>}
    </div>
    <footer className={styles.footer}><button type="button" className={styles.secondary} disabled={isRecalculating || loading} onClick={() => void recalculate()}>{isRecalculating ? "Đang cập nhật…" : "Cập nhật kế hoạch 7 ngày"}</button><button type="button" className={styles.primary} disabled={isRecalculating} onClick={onClose}>Đóng</button></footer>
  </dialog>;
}
