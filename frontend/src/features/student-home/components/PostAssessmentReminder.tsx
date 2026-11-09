"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { ArrowRight, Target } from "lucide-react";
import { afterAttempt, parseNextLearning, type NextLearning } from "@/features/math-workspace/utils/next-learning";
import s from "./PostAssessmentReminder.module.css";

/** Returning from a review keeps its context; opening the home normally adds no request. */
export function PostAssessmentReminder() {
  const [data, setData] = useState<NextLearning | null>(null);
  const [attemptId, setAttemptId] = useState<string | null>(null);
  const [error, setError] = useState(false);
  useEffect(() => {
    const id = afterAttempt(window.location.search);
    if (!id) return;
    setAttemptId(id);
    const controller = new AbortController();
    fetch(`/api/v3/math-solutions/attempts/${id}/next-learning`, {cache:"no-store",signal:controller.signal})
      .then(async response => {if (!response.ok) throw Error(); return parseNextLearning(await response.json(),id);})
      .then(value => {if (!controller.signal.aborted) setData(value);})
      .catch(() => {if (!controller.signal.aborted) setError(true);});
    return () => controller.abort();
  }, []);
  if (!attemptId) return null;
  return <section className={s.card} aria-label="Tiếp nối bài vừa làm">
    <div className={s.icon}><Target size={22} /></div>
    <div className={s.copy}><span>TỪ BÀI VỪA LÀM</span><h3>{data?.target?.name ?? "Tiếp nối chặng học của bạn"}</h3>
      <p>{data?.target?.reason ?? (error ? "Mở lại kết quả để xem bước học tiếp theo. Kết quả bài làm vẫn được giữ." : data?.explanation ?? "Đang đọc đề xuất từ kết quả đã lưu…")}</p>
      {data?.target?.next_review_at && <small>Lịch ôn của mục tiêu này đã được hiển thị trong phần kết quả.</small>}
    </div>
    <Link href={`/student/attempts/${attemptId}`} prefetch={false}>Xem kết quả & bài luyện <ArrowRight size={15} /></Link>
  </section>;
}
