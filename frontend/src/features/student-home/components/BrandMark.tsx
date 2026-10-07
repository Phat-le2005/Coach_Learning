import styles from "./BrandMark.module.css";

export interface BrandMarkProps {
  compact?: boolean;
}

export function BrandMark({ compact = false }: BrandMarkProps) {
  return (
    <span aria-label="EduMS" className={styles.root}>
      <svg aria-hidden="true" viewBox="0 0 44 44" width="42" height="42">
        <defs>
          <linearGradient id="brand-leaf-gradient" x1="5" y1="37" x2="39" y2="5">
            <stop offset="0" stopColor="var(--verdant-700)" />
            <stop offset="1" stopColor="var(--aqua-500)" />
          </linearGradient>
        </defs>
        <path
          d="M9.5 28.5C8.2 17.1 15.7 8.8 31.8 7.2c1.5 14.3-5.8 23-18.8 23.1"
          fill="url(#brand-leaf-gradient)"
        />
        <path d="M11.2 34.8c3.9-8.1 9.9-14 18.3-19.1" fill="none" stroke="var(--surface-elevated)" strokeWidth="2.4" strokeLinecap="round" />
        <circle cx="31.9" cy="8.1" r="2.6" fill="var(--amber-500)" />
        <path d="M34.9 13.8l1.1 2.4 2.4 1.1-2.4 1.1-1.1 2.4-1.1-2.4-2.4-1.1 2.4-1.1z" fill="var(--surface-elevated)" />
      </svg>
      {!compact ? (
        <span className={styles.copy}>
          <strong>EduMS</strong>
          <small>Learning Garden</small>
        </span>
      ) : null}
    </span>
  );
}
