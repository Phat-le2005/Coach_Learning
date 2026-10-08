import { AlertTriangle, Inbox, LoaderCircle, ShieldX } from "lucide-react";
import type { ReactNode } from "react";

import { GradientButton } from "@/components/ui/GradientButton";
import { OrganicCard } from "@/components/ui/OrganicCard";

import styles from "./app-shell.module.css";

type StateKind = "loading" | "empty" | "unauthorized" | "error";
const icons: Record<StateKind, typeof Inbox> = { loading: LoaderCircle, empty: Inbox, unauthorized: ShieldX, error: AlertTriangle };
export interface PageStateProps { kind: StateKind; title: string; description: string; action?: ReactNode }

export function PageState({ kind, title, description, action }: PageStateProps) {
  const Icon = icons[kind];
  return <OrganicCard className={styles.state} variant="glass"><span className={styles.stateIcon}><Icon className={kind === "loading" ? styles.spin : undefined} size={27} /></span><h2>{title}</h2><p>{description}</p>{action ?? (kind === "unauthorized" ? <GradientButton href="/">Về trang của tôi</GradientButton> : null)}</OrganicCard>;
}
