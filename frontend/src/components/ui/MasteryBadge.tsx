import { CircleEllipsis, Leaf, Sprout } from "lucide-react";

import styles from "./ui.module.css";

export type MasteryBadgeState = "mastered" | "developing" | "weak" | "review" | "not_measured";

export interface MasteryBadgeProps {
  state: MasteryBadgeState;
  label: string;
}

export function MasteryBadge({ state, label }: MasteryBadgeProps) {
  const stateClass =
    state === "weak" ? styles.masteryWeak : state === "review" ? styles.masteryReview : state === "not_measured" ? styles.masteryUnknown : "";
  const Icon = state === "mastered" ? Leaf : state === "not_measured" ? CircleEllipsis : Sprout;

  return (
    <span className={[styles.masteryBadge, stateClass].filter(Boolean).join(" ")}>
      <span className={styles.masteryIcon} aria-hidden="true">
        <Icon size={15} strokeWidth={2} />
      </span>
      {label}
    </span>
  );
}
