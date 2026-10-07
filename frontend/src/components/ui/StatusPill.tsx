import styles from "./ui.module.css";

export interface StatusPillProps {
  children: string;
  tone?: "positive" | "warning" | "violet";
}

export function StatusPill({ children, tone = "positive" }: StatusPillProps) {
  const toneClass = tone === "warning" ? styles.pillWarning : tone === "violet" ? styles.pillViolet : "";
  return (
    <span className={[styles.pill, toneClass].filter(Boolean).join(" ")}>
      <span className={styles.pillDot} aria-hidden="true" />
      {children}
    </span>
  );
}
