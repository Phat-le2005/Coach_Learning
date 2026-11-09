"use client";

import { useEffect, useRef, type ReactNode } from "react";
import styles from "../TeacherDashboard.module.css";

/** Native top-layer dialogs stay inside the viewport even in the transformed 3D room. */
export function MaterialDialog({ children, titleId, descriptionId, busy = false, compact = false, onClose }: {
  children: ReactNode; titleId: string; descriptionId?: string; busy?: boolean; compact?: boolean; onClose: () => void;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const closeRef = useRef(onClose);
  closeRef.current = onClose;
  useEffect(() => {
    const dialog = ref.current;
    const previous = document.activeElement;
    const overflow = document.body.style.overflow;
    dialog?.showModal();
    document.body.style.overflow = "hidden";
    return () => {
      dialog?.close();
      document.body.style.overflow = overflow;
      if (previous instanceof HTMLElement && previous.isConnected) previous.focus();
    };
  }, []);
  return <dialog ref={ref} className={`${styles.materialDialog} ${compact ? styles.materialDialogCompact : ""}`}
    aria-labelledby={titleId} aria-describedby={descriptionId} onCancel={event => {
      event.preventDefault();
      if (!busy) closeRef.current();
    }}>{children}</dialog>;
}
