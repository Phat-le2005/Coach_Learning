"use client";

import { useActionState } from "react";
import { useFormStatus } from "react-dom";

import { DERIVATIVE_TEST_EXAMPLES, LEGACY_STEP_REVIEW_EXAMPLES } from "@/features/math-workspace/utils/step-review-examples";
import { startStepReviewDemoAction, type StartWorkspaceState } from "./actions";
import styles from "./attempts.module.css";

const initialState: StartWorkspaceState = { error: null };

function DemoFields() {
  const { pending } = useFormStatus();
  return <>
    <div className={styles.fieldGroup}>
      <label htmlFor="step-review-question" className={styles.fieldLabel}>Bộ 10 bài đạo hàm · Thử chấm từng bước</label>
      <select id="step-review-question" name="question_id" className={styles.subjectSelect}
        defaultValue={DERIVATIVE_TEST_EXAMPLES[0].id} disabled={pending}>
        <optgroup label="Bộ 10 bài đạo hàm">
          {DERIVATIVE_TEST_EXAMPLES.map((example) => <option key={example.id} value={example.id}>{example.label}</option>)}
        </optgroup>
        <optgroup label="Bài thử trước đây">
          {LEGACY_STEP_REVIEW_EXAMPLES.map((example) => <option key={example.id} value={example.id}>{example.label}</option>)}
        </optgroup>
      </select>
      <p>Chọn từng bài để thử viết hoặc tải ảnh, trích xuất OCR, sửa và xác nhận các bước rồi nộp. Bộ thử chỉ có trên máy development; nhận xét AI chưa phải điểm chính thức.</p>
    </div>
    <button type="submit" className={styles.startButton} disabled={pending}>
      {pending ? "Đang mở bài thử..." : "Thử chấm từng bước"}
    </button>
  </>;
}

export function StepReviewDemoForm() {
  const [state, action] = useActionState(startStepReviewDemoAction, initialState);
  return <form action={action} className={styles.startForm}>
    <DemoFields />
    {state.error ? <p className={styles.formError} role="alert">{state.error}</p> : null}
  </form>;
}
