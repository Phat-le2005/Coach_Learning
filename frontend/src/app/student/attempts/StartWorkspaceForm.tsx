"use client";

import { useActionState } from "react";
import { useFormStatus } from "react-dom";

import { startWorkspaceAction, type StartWorkspaceState } from "./actions";
import styles from "./attempts.module.css";

const initialState: StartWorkspaceState = { error: null };

function SubmitButton() {
  const { pending } = useFormStatus();
  return <button className={styles.startButton} type="submit" disabled={pending}>{pending ? "Đang tìm bài..." : "Bắt đầu làm bài"}</button>;
}

export function StartWorkspaceForm({ subjects }: { subjects: { id: string; name: string }[] }) {
  const [state, action] = useActionState(startWorkspaceAction, initialState);
  if (subjects.length === 0) return <p>Chưa có môn học nào được phát hành cho tài khoản này.</p>;

  return (
    <form action={action} className={styles.startForm}>
      <label htmlFor="workspace-subject">Môn học</label>
      <select id="workspace-subject" name="subject_id" required>
        {subjects.map((subject) => <option key={subject.id} value={subject.id}>{subject.name}</option>)}
      </select>
      <SubmitButton />
      {state.error && <p className={styles.formError} role="alert">{state.error}</p>}
    </form>
  );
}
