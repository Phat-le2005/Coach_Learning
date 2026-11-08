"use client";

import { useEffect, useRef } from "react";
import Link from "next/link";
import { ArrowLeft, ChevronLeft, ChevronRight, Check } from "lucide-react";
import type { ClassroomNavData } from "@/lib/classroom-assignments/launch";
import type { SolutionAttemptRead } from "../types";
import styles from "../MathWorkspace.module.css";

interface Props {
  nav: ClassroomNavData;
  attemptId: string;
  attempt: SolutionAttemptRead | null;
  switching: boolean;
  examMode: boolean;
  examSubmitted: boolean;
  onNavigate: (index: number) => void;
  onSubmitExam: () => void;
  onBack?: () => void;
  backDisabled?: boolean;
}

/** Presentation only: MathWorkspace still owns saving, revision and navigation guards. */
export function ClassroomNavigation({ nav, attemptId, attempt, switching, examMode, examSubmitted, onNavigate, onSubmitExam, onBack, backDisabled }: Props) {
  const questions = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const row = questions.current;
    const current = row?.querySelector<HTMLElement>('[aria-current="step"]');
    if (row && current) row.scrollLeft = Math.max(0, current.offsetLeft - (row.clientWidth - current.offsetWidth) / 2);
  }, [nav.currentIndex]);

  return <nav className={styles.classroomBar} aria-label="Điều hướng bài tập lớp">
    <div className={styles.classroomLeft}>
      <Link href="/student/attempts?tab=classroom" className={styles.classroomBackLink} aria-disabled={backDisabled || undefined} onClick={event => {
        if (backDisabled) { event.preventDefault(); return; }
        if (onBack && !event.metaKey && !event.ctrlKey && !event.shiftKey && !event.altKey) { event.preventDefault(); onBack(); }
      }}><ArrowLeft size={16} aria-hidden="true" /><span>Bài tập lớp</span></Link>
      <div className={styles.classroomContext}>
        <span className={`${styles.classroomModeBadge} ${nav.deliveryMode === "EXAM" ? styles.classroomModeBadgeExam : styles.classroomModeBadgePractice}`}>{nav.deliveryMode === "EXAM" ? "Kiểm tra" : "Luyện tập"}</span>
        <span className={styles.classroomTitle} title={nav.title}>{nav.title}</span>
      </div>
    </div>
    <div className={styles.classroomQuestionNav}>
      <span className={styles.classroomQuestionCount}>Câu {nav.currentIndex + 1}<span>/{nav.totalQuestions}</span></span>
      <div ref={questions} className={styles.classroomCenter} aria-label="Danh sách câu hỏi">
        {nav.questions.map(q => {
          const isCurrent = q.index === nav.currentIndex;
          const isLiveAttempt = q.attemptId === attemptId;
          const status = isLiveAttempt && attempt ? attempt.status : q.status;
          const submitted = status === "SUBMITTED" || status === "EVALUATED";
          const hasSteps = (isLiveAttempt && attempt ? attempt.steps?.length ?? 0 : q.stepCount ?? 0) > 0;
          const hasAnswer = Boolean(q.hasAnswer || q.studentAnswer?.trim());
          const state = submitted ? "submitted" : hasSteps || hasAnswer ? "started" : "unmarked";
          const description = submitted ? "Đã nộp câu" : hasSteps ? "Đã lưu bước giải" : hasAnswer ? "Đã có câu trả lời" : "Chưa ghi nhận bước giải";
          return <button key={q.index} type="button" className={`${styles.qNavPill} ${isCurrent ? styles.qNavPillActive : state !== "unmarked" ? styles.qNavPillCompleted : ""}`}
            aria-current={isCurrent ? "step" : undefined} aria-label={`Câu ${q.index + 1}${isCurrent ? ", đang xem" : ""} · ${description}`} data-question-state={state}
            title={`Câu ${q.index + 1} · ${description}`} disabled={switching} onClick={() => onNavigate(q.index)}>
            {q.index + 1}{submitted ? <Check className={styles.questionStateMark} size={10} aria-hidden="true" /> : state === "started" ? <span className={styles.questionStartedMark} aria-hidden="true" /> : null}
          </button>;
        })}
      </div>
    </div>
    <div className={styles.classroomRight}>
      <button type="button" className={styles.navStepBtn} aria-label="Câu trước" title="Câu trước" disabled={nav.currentIndex === 0 || switching} onClick={() => onNavigate(nav.currentIndex - 1)}><ChevronLeft size={16} aria-hidden="true" /><span className={styles.questionDirectionLabel}>Câu trước</span></button>
      <button type="button" className={styles.navStepBtn} aria-label="Câu sau" title="Câu sau" disabled={nav.currentIndex >= nav.totalQuestions - 1 || switching} onClick={() => onNavigate(nav.currentIndex + 1)}><span className={styles.questionDirectionLabel}>{switching ? "Đang chuyển…" : "Câu sau"}</span><ChevronRight size={16} aria-hidden="true" /></button>
    </div>
    {examMode ? <div className={styles.classroomExamAction}>{examSubmitted ? <span className={styles.examSubmittedLabel}><Check size={14} aria-hidden="true" />Đã nộp toàn bài</span> : <button type="button" className={styles.navStepBtnPrimary} onClick={onSubmitExam}>Nộp bài kiểm tra</button>}</div> : null}
    <span className={styles.navigationAnnouncement} role="status">{switching ? "Đang lưu và chuyển câu…" : ""}</span>
  </nav>;
}
