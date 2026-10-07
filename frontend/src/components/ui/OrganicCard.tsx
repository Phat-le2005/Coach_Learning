import type { HTMLAttributes, ReactNode } from "react";

import styles from "./ui.module.css";

export interface OrganicCardProps extends HTMLAttributes<HTMLDivElement> {
  children: ReactNode;
  variant?: "glass" | "solid" | "accent";
  interactive?: boolean;
}

export function OrganicCard({
  children,
  variant = "glass",
  interactive = false,
  className,
  ...props
}: OrganicCardProps) {
  const classes = [
    styles.card,
    styles[variant],
    interactive ? styles.interactive : "",
    className ?? "",
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <div className={classes} {...props}>
      {children}
    </div>
  );
}
