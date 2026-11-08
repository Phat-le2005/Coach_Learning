"use client";
import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import type { StudentHomeViewModel } from "../types";
import ui from "../HomeRefresh.module.css";
import { HomeIcon } from "./HomeIcon";
import { HomeToday } from "./HomeToday";
import { StudyPlanRoadmapModal } from "./StudyPlanRoadmapModal";

export function LearningPulse({ data, planRequest = 0, onDetails, onPlanOpenChange }: {
  data: StudentHomeViewModel; planRequest?: number; onDetails: () => void; onPlanOpenChange?: (open: boolean) => void;
}) {
  const router = useRouter();
  const [showGoal, setShowGoal] = useState(false);
  const [showRoadmap, setShowRoadmap] = useState(false);
  const [targetScore, setTargetScore] = useState(8);
  const [dailyMinutes, setDailyMinutes] = useState(30);
  const [goalDate, setGoalDate] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [recalculating, setRecalculating] = useState(false);
  const [feedback, setFeedback] = useState<string | null>(null);
  const [canUseExistingGoal, setCanUseExistingGoal] = useState(false);
  const dialog = useRef<HTMLDialogElement>(null);
  const handledRequest = useRef(0);
  useEffect(() => { onPlanOpenChange?.(showGoal || showRoadmap); }, [showGoal, showRoadmap, onPlanOpenChange]);
  function openPlan() {
    if (data.todayPlan && data.todayPlan.totalCount > 0) setShowRoadmap(true);
    else { setFeedback(null); setCanUseExistingGoal(false); setShowGoal(true); }
  }
  useEffect(() => {
    if (planRequest > handledRequest.current) { handledRequest.current = planRequest; openPlan(); }
  }, [planRequest, data.todayPlan]);
  useEffect(() => {
    const element = dialog.current;
    if (showGoal && element && !element.open) element.showModal();
    if (!showGoal && element?.open) element.close();
  }, [showGoal]);
  async function createGoal() {
    if (submitting || recalculating) return;
    setSubmitting(true); setFeedback(null);
    try {
      const response = await fetch("/api/student/study-plan", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ action: "create_goal", subject_id: data.subject.id, target_score: targetScore, available_daily_minutes: dailyMinutes, exam_date: goalDate }) });
      if (!response.ok) {
        const body = await response.json().catch(() => ({}));
        const error = body.error ?? body;
        setCanUseExistingGoal(error.code === "ACTIVE_GOAL_EXISTS" || error.code === "PLAN_CREATION_FAILED");
        throw new Error(error.message || "Không thể tạo kế hoạch. Bạn có thể thử lại.");
      }
      setShowGoal(false); router.refresh();
    } catch (error) { setFeedback(error instanceof Error ? error.message : "Không thể tạo kế hoạch. Bạn có thể thử lại."); }
    finally { setSubmitting(false); }
  }
  async function recalculate(closeGoal = false) {
    if (recalculating) return;
    setRecalculating(true); setFeedback(null);
    try {
      const response = await fetch("/api/student/study-plan", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ action: "recalculate", horizon_days: 7 }) });
      if (!response.ok) throw new Error("Chưa cập nhật được kế hoạch. Bạn có thể thử lại.");
      if (closeGoal) setShowGoal(false);
      router.refresh();
    } catch (error) { setFeedback(error instanceof Error ? error.message : "Chưa cập nhật được kế hoạch."); }
    finally { setRecalculating(false); }
  }
  return <>
    <HomeToday data={data} onOpenPlan={openPlan} onDetails={onDetails} onRecalculate={() => void recalculate()} recalculating={recalculating} feedback={!showGoal ? feedback : null} />
    <dialog ref={dialog} className={ui.goalDialog} aria-labelledby="goal-modal-title" onCancel={event => { event.preventDefault(); if (!submitting && !recalculating) setShowGoal(false); }} onClick={event => { if (event.target === dialog.current && !submitting && !recalculating) setShowGoal(false); }}>
      <form onSubmit={event => { event.preventDefault(); void createGoal(); }}>
        <div className={ui.dialogHeading}><h2 id="goal-modal-title">Kế hoạch học của bạn</h2><button type="button" className={ui.closeButton} aria-label="Đóng kế hoạch học" disabled={submitting || recalculating} onClick={() => setShowGoal(false)}><HomeIcon name="x" /></button></div>
        <p>Chọn mục tiêu, quỹ thời gian và mốc hoàn thành cho môn {data.subject.name}.</p>
        <fieldset><legend>Mục tiêu điểm số</legend><div className={ui.goalOptions}>{[{ score: 7, label: "7.0+", hint: "Vững cơ bản" }, { score: 8, label: "8.0+", hint: "Củng cố và nâng cao" }, { score: 9, label: "9.0+", hint: "Vận dụng cao" }].map(item => <button type="button" key={item.score} aria-pressed={targetScore === item.score} onClick={() => setTargetScore(item.score)}><strong>{item.label}</strong><span>{item.hint}</span></button>)}</div></fieldset>
        <fieldset><legend>Thời gian tự học mỗi ngày</legend><div className={ui.timeOptions}>{[15, 30, 45, 60].map(minutes => <button type="button" key={minutes} aria-pressed={dailyMinutes === minutes} onClick={() => setDailyMinutes(minutes)}>{minutes} phút</button>)}</div></fieldset>
        <label className={ui.goalDate}>Mốc hoàn thành<input type="date" required value={goalDate} onChange={event => setGoalDate(event.target.value)} /><small>Kế hoạch sẽ được sắp theo mốc bạn chọn.</small></label>
        {feedback && <p className={ui.feedback} role="alert">{feedback}</p>}
        {canUseExistingGoal && <button type="button" className={ui.goalSubmit} disabled={submitting || recalculating} onClick={() => void recalculate(true)}>{recalculating ? "Đang cập nhật…" : "Dùng mục tiêu hiện có"}</button>}
        {!canUseExistingGoal && <button type="submit" className={ui.goalSubmit} disabled={submitting || recalculating}>{submitting ? "Đang tạo kế hoạch…" : "Tạo kế hoạch học"}</button>}
      </form>
    </dialog>
    <StudyPlanRoadmapModal isOpen={showRoadmap} onClose={() => setShowRoadmap(false)} subjectId={data.subject.id} onRecalculateDone={() => router.refresh()} />
  </>;
}
