"use client";

import { useActionState } from "react";
import { useFormStatus } from "react-dom";

import { startStepReviewDemoAction, type StartWorkspaceState } from "./actions";
import styles from "./attempts.module.css";

const initialState: StartWorkspaceState = { error: null };

function DemoButton() {
  const { pending } = useFormStatus();
  return <button type="submit" className={styles.startButton} disabled={pending}>
    {pending ? "Đang mở bài mẫu..." : "Thử chấm từng bước"}
  </button>;
}

export function StepReviewDemoForm() {
  const [state, action] = useActionState(startStepReviewDemoAction, initialState);
  return <form action={action} className={styles.startForm}>
    <p>Bài tự luận Toán 12: khảo sát hàm bậc ba. Xác nhận từng bước, nộp bài, rồi chọn “Nhận xét bằng Gemini”. Kết quả chỉ là góp ý, chưa phải điểm chính thức.</p>
    <DemoButton />
    {state.error ? <p className={styles.formError} role="alert">{state.error}</p> : null}
  </form>;
}
