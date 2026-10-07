import type { ReactNode } from "react";

import styles from "../StudentHome.module.css";

export interface SectionHeadingProps {
  eyebrow?: string;
  title: string;
  description?: string;
  action?: ReactNode;
}

export function SectionHeading({ eyebrow, title, description, action }: SectionHeadingProps) {
  return (
    <div className={styles.sectionHeading}>
      <div>
        {eyebrow ? <p className={styles.sectionEyebrow}>{eyebrow}</p> : null}
        <h2>{title}</h2>
        {description ? <p>{description}</p> : null}
      </div>
      {action ? <div className={styles.sectionAction}>{action}</div> : null}
    </div>
  );
}
