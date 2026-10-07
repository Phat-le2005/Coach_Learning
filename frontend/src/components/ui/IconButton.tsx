import type { ButtonHTMLAttributes, ReactNode } from "react";

import styles from "./ui.module.css";

export interface IconButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  label: string;
  children: ReactNode;
}

export function IconButton({ label, children, className, ...props }: IconButtonProps) {
  return (
    <button
      aria-label={label}
      className={[styles.iconButton, className ?? ""].filter(Boolean).join(" ")}
      type="button"
      {...props}
    >
      {children}
    </button>
  );
}
