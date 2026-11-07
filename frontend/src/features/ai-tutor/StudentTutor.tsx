"use client";

import { Bot, Lightbulb, LoaderCircle, Send, Sparkles, X } from "lucide-react";
import Link from "next/link";
import { useEffect, useId, useRef, useState, type FormEvent } from "react";

import { MathRenderer } from "@/components/ui/MathRenderer";
import { parseStudentTutorReply, TUTOR_MESSAGE_MAX_LENGTH } from "@/lib/api/student-tutor";
import { BrowserAuthError, getCsrfToken, refreshBrowserSession } from "@/lib/auth/browser";

import styles from "./StudentTutor.module.css";

const SUGGESTIONS = [
  { label: "Xét tính đơn điệu", question: "Em cần xét tính đơn điệu của y=x^3-3x+1. Hãy gợi ý bước đầu, chưa đưa toàn bộ lời giải." },
  { label: "Quy tắc đạo hàm", question: "Em hay nhầm quy tắc đạo hàm của hàm hợp. Hãy giải thích bằng một ví dụ đơn giản và cho em một câu để tự thử." },
  { label: "Cách học hiệu quả", question: "Em có 30 phút để ôn đạo hàm hôm nay. Hãy gợi ý cách chia thời gian và hỏi em một câu để xác định phần cần ôn." },
];

export function StudentTutor() {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const questionRef = useRef<HTMLTextAreaElement>(null);
  const answerRef = useRef<HTMLElement>(null);
  const controllerRef = useRef<AbortController | null>(null);
  const titleId = useId();
  const questionId = useId();
  const helpId = useId();
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState<{ question: string; reply: string } | null>(null);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [needsLogin, setNeedsLogin] = useState(false);

  useEffect(() => () => controllerRef.current?.abort(), []);
  useEffect(() => {
    if (answer && dialogRef.current?.open) answerRef.current?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [answer]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const message = question.trim();
    if (!message || controllerRef.current || message.length > TUTOR_MESSAGE_MAX_LENGTH) return;
    const controller = new AbortController();
    controllerRef.current = controller;
    setPending(true);
    setError(null);
    setNeedsLogin(false);
    setAnswer(null);
    try {
      const send = async () => {
        const csrfToken = await getCsrfToken();
        return fetch("/api/student/tutor", {
          method: "POST",
          credentials: "same-origin",
          headers: { "Content-Type": "application/json", "X-CSRF-Token": csrfToken },
          body: JSON.stringify({ message, stream: false }),
          signal: controller.signal,
        });
      };
      let response = await send();
      if (response.status === 401) {
        await refreshBrowserSession();
        response = await send();
      }
      const data = await response.json().catch(() => null);
      if (!response.ok) {
        setNeedsLogin(response.status === 401);
        throw new Error(data?.error?.message || "Gia sư chưa thể phản hồi. Em hãy thử lại.");
      }
      const reply = parseStudentTutorReply(data);
      if (!reply) throw new Error("Chưa nhận được câu trả lời. Em hãy thử gửi lại.");
      setAnswer({ question: message, reply });
    } catch (failure) {
      if (!controller.signal.aborted) {
        if (failure instanceof BrowserAuthError && failure.status === 401) setNeedsLogin(true);
        setError(failure instanceof Error ? failure.message : "Có lỗi kết nối. Em hãy thử lại.");
      }
    } finally {
      if (controllerRef.current === controller) controllerRef.current = null;
      if (!controller.signal.aborted) setPending(false);
    }
  }

  return (
    <>
      <button type="button" className={styles.trigger} onClick={() => {
        dialogRef.current?.showModal(); questionRef.current?.focus();
      }}
        aria-haspopup="dialog" aria-label="Mở Gia sư AI" title="Hỏi Gia sư AI">
        <Sparkles size={16} aria-hidden="true" />
        <span>Gia sư AI</span>
      </button>
      <dialog ref={dialogRef} className={styles.dialog} aria-labelledby={titleId}
        onClick={event => { if (event.target === event.currentTarget) dialogRef.current?.close(); }}>
        <header className={styles.header}>
          <div className={styles.avatar}><Bot size={24} aria-hidden="true" /></div>
          <div className={styles.heading}>
            <p>Cùng em tìm hướng giải</p>
            <h2 id={titleId}>Gia sư AI</h2>
          </div>
          <button type="button" className={styles.close} onClick={() => dialogRef.current?.close()} aria-label="Đóng Gia sư AI">
            <X size={20} aria-hidden="true" />
          </button>
        </header>
        <div className={styles.body}>
          <p className={styles.intro}>Gửi đề bài và bước em đang vướng. Gia sư sẽ gợi mở để em tự tìm ra cách giải.</p>
          <div className={styles.suggestions} aria-label="Câu hỏi gợi ý">
            {SUGGESTIONS.map(item => (
              <button type="button" key={item.label} disabled={pending} onClick={() => {
                setQuestion(item.question); setError(null); questionRef.current?.focus();
              }}><Lightbulb size={14} aria-hidden="true" />{item.label}</button>
            ))}
          </div>
          <form onSubmit={handleSubmit} className={styles.form}>
            <label htmlFor={questionId}>Câu hỏi của em</label>
            <textarea ref={questionRef} id={questionId} value={question} onChange={event => setQuestion(event.target.value)}
              placeholder="Ví dụ: Em đã tính đạo hàm nhưng chưa biết lập bảng xét dấu…"
              maxLength={TUTOR_MESSAGE_MAX_LENGTH} rows={4} required autoFocus aria-describedby={helpId} />
            <div className={styles.formFooter}>
              <span id={helpId}>{question.length.toLocaleString("vi-VN")} / 2.000 ký tự</span>
              <button type="submit" className={styles.send} disabled={pending || !question.trim()}>
                {pending ? <LoaderCircle className={styles.spinner} size={17} aria-hidden="true" /> : <Send size={16} aria-hidden="true" />}
                {pending ? "Đang hỏi gia sư…" : "Gửi câu hỏi"}
              </button>
            </div>
          </form>
          {pending && <p className={styles.pending} role="status">Gia sư đang đọc câu hỏi và chuẩn bị gợi ý cho em…</p>}
          {error && <div className={styles.error} role="alert"><p>{error}</p>{needsLogin && <Link href="/login?returnTo=%2Fstudent">Đăng nhập lại</Link>}</div>}
          {answer && <section ref={answerRef} className={styles.answer} aria-label="Phản hồi của Gia sư AI" aria-live="polite">
            <p className={styles.asked}>{answer.question}</p>
            <h3><Sparkles size={16} aria-hidden="true" /> Gợi ý dành cho em</h3>
            <MathRenderer content={answer.reply} />
          </section>}
          <p className={styles.note}>Mỗi câu hỏi là một lượt hướng dẫn riêng. Nhận xét của gia sư không thay thế điểm chấm chính thức.</p>
        </div>
      </dialog>
    </>
  );
}
