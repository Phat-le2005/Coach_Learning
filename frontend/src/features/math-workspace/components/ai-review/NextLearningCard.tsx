"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { ArrowRight, BookOpen, Check, ChevronRight, Compass, LoaderCircle, RefreshCw, Target, Clock3, AlertCircle, Sparkles } from "lucide-react";
import type { AIReviewRead } from "@/lib/api/contracts";
import { getCsrfToken } from "@/lib/auth/browser";
import { MathRenderer } from "@/components/ui/MathRenderer";
import { learningLinks, parseNextLearning, reviewDate, type NextLearning } from "../../utils/next-learning";
import s from "./NextLearning.module.css";

export function NextLearningCard({ review, onJumpToStep, onNextProblem, nextProblemLabel, isNextLoading }: {
  review: AIReviewRead; onJumpToStep: (index: number) => void;
  onNextProblem?: () => void; nextProblemLabel?: string; isNextLoading?: boolean;
}) {
  const router = useRouter();
  const [data, setData] = useState<NextLearning | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [launching, setLaunching] = useState(false);
  const [revision, setRevision] = useState(0);
  const [coach, setCoach] = useState<{ text: string; source: string } | null>(null);
  const [explaining, setExplaining] = useState(false);
  useEffect(() => {
    const controller = new AbortController();
    setData(null); setLoading(true); setError(""); setCoach(null);
    fetch(`/api/v3/math-solutions/attempts/${review.attempt_id}/next-learning`, { cache: "no-store", signal: controller.signal })
      .then(async response => {
        if (!response.ok) throw new Error(response.status === 401 ? "Phiên đăng nhập đã hết hạn. Hãy đăng nhập lại để xem đề xuất." : "Chưa tải được đề xuất. Kết quả chấm của bạn vẫn được giữ.");
        return parseNextLearning(await response.json(), review.attempt_id);
      }).then(value => { if (!controller.signal.aborted) setData(value); })
      .catch(reason => { if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : "Chưa tải được đề xuất."); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [review.attempt_id, review.is_final, review.final_score, revision]);

  async function launch() {
    if (!data?.question || !data.decision_id || launching) return;
    setLaunching(true); setError("");
    try {
      const token = await getCsrfToken();
      const response = await fetch(`/api/v3/math-solutions/attempts/${review.attempt_id}/next-learning`, {
        method: "POST", headers: { "Content-Type": "application/json", "X-CSRF-Token": token },
        body: JSON.stringify({ decision_id: data.decision_id, question_id: data.question.id }),
      });
      if (response.status === 409) { setRevision(n => n + 1); throw new Error("Đề xuất đã thay đổi. Hệ thống đang tải lại bài phù hợp."); }
      if (!response.ok) throw new Error("Chưa mở được bài luyện. Bạn có thể thử lại; bài vừa chấm vẫn được giữ.");
      const result = await response.json();
      if (!/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(result.attempt_id ?? "")) throw new Error("Chưa nhận được bài luyện hợp lệ.");
      router.push(`/student/attempts/${result.attempt_id}`);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Chưa mở được bài luyện."); }
    finally { setLaunching(false); }
  }

  async function explain() {
    if (explaining) return;
    setExplaining(true); setError("");
    try {
      const token = await getCsrfToken();
      const response = await fetch(`/api/v3/math-solutions/attempts/${review.attempt_id}/next-learning/explain`, {
        method: "POST", headers: { "X-CSRF-Token": token },
      });
      if (!response.ok) throw new Error("Chưa tải được phần giải thích. Bạn vẫn có thể làm bài luyện đã chọn.");
      const value = await response.json();
      if (typeof value.text !== "string" || !value.text.trim() || !["AI_COACH", "LEARNING_CORE"].includes(value.source)) throw new Error("Phần giải thích chưa hợp lệ.");
      setCoach(value);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Chưa tải được giải thích."); }
    finally { setExplaining(false); }
  }

  const reinforce = data?.status === "REINFORCE";
  const pending = data?.status.startsWith("WAITING");
  const links = data ? learningLinks(data) : { theory: "/student/theory", knowledge: "/student/knowledge", plan: "/student#learning-pulse" };
  return <section className={`${s.card} ${reinforce ? s.reinforce : ""}`} aria-label="Bạn nên học gì tiếp?" data-testid="next-learning-card" aria-busy={loading}>
    <header className={s.heading}>
      <span className={s.compass}><Compass size={23} aria-hidden="true" /></span>
      <div><span className={s.eyebrow}>CHẶNG HỌC TIẾP THEO</span><h3>Bạn nên học gì tiếp?</h3></div>
      {!loading && data && <span className={s.badge}>{pending ? "Cần đối chiếu" : reinforce ? "Củng cố" : "Tiếp tục luyện"}</span>}
    </header>
    {loading ? <div className={s.loading} role="status"><LoaderCircle size={18} className={s.spin} /> Đang chọn bước học phù hợp với bạn…<div className={s.skeleton} /><div className={s.skeleton} /></div> : data && <>
      <div className={s.journey} aria-label="Tiến trình học"><span><Check size={13} /> Đối chiếu bài</span><ChevronRight size={13} /><span className={s.current}><Target size={13} /> {pending ? "Xem lại" : "Chọn mục tiêu"}</span><ChevronRight size={13} /><span><BookOpen size={13} /> Luyện & ôn</span></div>
      <h4 className={s.headline}>{data.headline}</h4><p className={s.description}>{data.explanation}</p>
      {data.score !== null && <div className={s.scoreLine}><strong>{Math.round(data.score * 100)}<small>/100</small></strong><div><b>Điểm bài đã lưu</b><span>{data.evidence_recorded ? "Đã ghi nhận bằng chứng học tập" : "Chưa xác nhận đồng bộ hồ sơ năng lực"}</span></div></div>}
      {data.criterion_gaps.length > 0 && <div className={s.gaps}><p>Tiêu chí cần hoàn thiện</p>{data.criterion_gaps.map((gap, i) => <div key={i}><span className={s.gapDot} /><span>{gap.title}</span><b>{Math.round(gap.achieved * 100)}/{Math.round(gap.maximum * 100)}</b>{gap.step_index !== null && review.step_grades.some(g => g.step_index === gap.step_index) && <button type="button" onClick={() => onJumpToStep(gap.step_index!)}>Bước {gap.step_index} <ArrowRight size={12} /></button>}</div>)}</div>}
      {data.target && <div className={s.target}>
        <div className={s.targetIcon}><Target size={21} /></div><div className={s.targetBody}><span className={s.overline}>{data.target.kind === "CONCEPT" ? "KIẾN THỨC ƯU TIÊN" : "DẠNG BÀI ƯU TIÊN"}</span><h4>{data.target.name}</h4><p>{data.target.reason}</p>
          {data.target.mastery_score !== null ? <div className={s.mastery}><div><span>Hồ sơ năng lực hiện tại</span><b>{Math.round(data.target.mastery_score * 100)}%</b></div><progress value={data.target.mastery_score} max={1} aria-label={`Mức năng lực ${data.target.name}`} /><small>Từ {data.target.evidence_count} lượt bằng chứng · khác với điểm bài vừa làm</small></div> : <p className={s.noEvidence}>Chưa đủ dữ liệu năng lực cho nội dung này.</p>}
          {data.target.next_review_at && <span className={s.reviewDate}><Clock3 size={13} /> Lịch ôn đã có: {reviewDate(data.target.next_review_at)}</span>}
        </div>
      </div>}
      {data.target && !pending && <div className={s.coach}>
        {coach ? <><span><Sparkles size={14} />{coach.source === "AI_COACH" ? "AI gợi ý cách ôn" : "Gợi ý từ kế hoạch học"}</span><p>{coach.text}</p></> : <button type="button" onClick={() => void explain()} disabled={explaining}>
          {explaining ? <LoaderCircle size={14} className={s.spin} /> : <Sparkles size={14} />}{explaining ? "Đang giải thích…" : "Gợi ý cách ôn cùng AI"}</button>}
      </div>}
      {data.question && <div className={s.question}><span className={s.overline}>01 BÀI LUYỆN ĐƯỢC CHỌN CHO BẠN</span><div className={s.questionText}><MathRenderer content={data.question.content} /></div><button className={s.primary} type="button" onClick={() => void launch()} disabled={launching}>{launching ? <LoaderCircle size={17} className={s.spin} /> : <ArrowRight size={17} />} {launching ? "Đang mở bài…" : reinforce ? "Làm bài củng cố" : "Làm bài được đề xuất"}</button></div>}
      {data.supply_message && <p className={s.supply}><AlertCircle size={16} />{data.supply_message}</p>}
      <div className={s.links}><Link href={links.theory} prefetch={false}><BookOpen size={15} />{data.target ? "Tìm lý thuyết liên quan" : "Mở kho lý thuyết"}</Link><Link href={links.plan} prefetch={false}>Xem kế hoạch học <ArrowRight size={14} /></Link></div>
    </>}
    {error && <div className={s.error} role="alert"><AlertCircle size={16} /><span>{error}</span><button type="button" onClick={() => setRevision(n => n + 1)}><RefreshCw size={14} />Tải lại</button></div>}
    {!loading && <footer className={s.footer}><Link href={links.knowledge} prefetch={false}>Bản đồ kiến thức <ArrowRight size={13} /></Link>{onNextProblem && <button type="button" onClick={onNextProblem} disabled={isNextLoading}>{isNextLoading ? "Đang mở…" : nextProblemLabel?.startsWith("Luyện tập") ? "Tự chọn bài khác" : nextProblemLabel || "Tự chọn bài khác"}<ArrowRight size={13} /></button>}</footer>}
  </section>;
}
