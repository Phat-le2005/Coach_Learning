"use client";

import { AlertCircle, ArrowRight, BookOpen, Loader2 } from "lucide-react";
import { useActionState } from "react";
import { useFormStatus } from "react-dom";

import { startWorkspaceAction, type StartWorkspaceState } from "./actions";
import styles from "./attempts.module.css";

const initialState: StartWorkspaceState = { error: null };

function SubmitButton() {
  const { pending } = useFormStatus();
  return (
    <button
      className={styles.startButton}
      type="submit"
      disabled={pending}
      aria-busy={pending}
    >
      {pending ? (
        <>
          <Loader2 size={18} className={styles.buttonSpinner} aria-hidden="true" />
          <span>Đang chuẩn bị trang giấy...</span>
        </>
      ) : (
        <>
          <span>Bắt đầu làm bài</span>
          <ArrowRight size={18} aria-hidden="true" />
        </>
      )}
    </button>
  );
}

export interface StartWorkspaceFormProps {
  subjects: { id: string; name: string }[];
  defaultSubjectId?: string;
}

export function StartWorkspaceForm({ subjects, defaultSubjectId }: StartWorkspaceFormProps) {
  const [state, action] = useActionState(startWorkspaceAction, initialState);

  if (subjects.length === 0) {
    return (
      <div className={styles.emptySubjectsNotice} role="status">
        <BookOpen size={18} aria-hidden="true" />
        <span>Chưa có môn học nào được phát hành cho tài khoản này.</span>
      </div>
    );
  }

  const initialSelectedId =
    defaultSubjectId && subjects.some((s) => s.id === defaultSubjectId)
      ? defaultSubjectId
      : subjects[0]?.id;

  return (
    <form action={action} className={styles.startForm}>
      <div className={styles.fieldGroup}>
        <label htmlFor="workspace-subject" className={styles.fieldLabel}>
          Chọn môn học
        </label>
        <div className={styles.selectWrap}>
          <select
            id="workspace-subject"
            name="subject_id"
            defaultValue={initialSelectedId}
            className={styles.subjectSelect}
            required
          >
            {subjects.map((subject) => (
              <option key={subject.id} value={subject.id}>
                {subject.name}
              </option>
            ))}
          </select>
        </div>
      </div>

      <SubmitButton />

      {state.error ? (
        <div className={styles.formError} role="alert" aria-live="polite">
          <AlertCircle size={17} aria-hidden="true" />
          <span>{state.error}</span>
        </div>
      ) : null}
    </form>
  );
}
