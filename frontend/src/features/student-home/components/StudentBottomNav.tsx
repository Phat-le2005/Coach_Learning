import { BookOpen, Edit3, FileText, House, Orbit } from "lucide-react";
import Link from "next/link";

import styles from "../StudentHome.module.css";

export interface StudentBottomNavProps {
  currentRoute?: string;
  subjectId?: string;
  pendingAssignmentsCount?: number;
}

export function StudentBottomNav({
  currentRoute = "/student",
  subjectId,
  pendingAssignmentsCount,
}: StudentBottomNavProps) {
  const isKnowledge = currentRoute.startsWith("/student/knowledge");
  const isAssignments = currentRoute.startsWith("/student/assignments");
  const isTheory = currentRoute.startsWith("/student/theory");
  const isAttempts = currentRoute.startsWith("/student/attempts");
  const isHome = currentRoute === "/student" || (!isKnowledge && !isAssignments && !isTheory && !isAttempts && currentRoute.startsWith("/student"));

  const knowledgeHref = subjectId
    ? `/student/knowledge?subject_id=${encodeURIComponent(subjectId)}`
    : "/student/knowledge";

  const homeHref = subjectId ? `/student?subject_id=${encodeURIComponent(subjectId)}` : "/student";

  const items = [
    { label: "Tổng quan", href: homeHref, icon: House, current: isHome },
    { label: "Bài tập", href: "/student/assignments", icon: BookOpen, current: isAssignments },
    { label: "Vũ trụ", href: knowledgeHref, icon: Orbit, current: isKnowledge },
    { label: "Lý thuyết", href: "/student/theory", icon: FileText, current: isTheory },
    { label: "Luyện tập", href: "/student/attempts", icon: Edit3, current: isAttempts },
    { label: "Nhiệm vụ", href: isHome ? "#learning-pulse" : `${homeHref}#learning-pulse`, icon: BookOpen, current: false },
  ];

  return (
    <nav className={styles.bottomNav} aria-label="Điều hướng học sinh trên di động">
      {items.map(({ label, href, icon: Icon, current }) => (
        <Link
          className={current ? styles.bottomNavActive : styles.bottomNavItem}
          href={href}
          aria-current={current ? "page" : undefined}
          key={label}
        >
          <Icon size={19} strokeWidth={1.9} aria-hidden="true" />
          <span>{label}</span>
          {label === "Bài tập" && pendingAssignmentsCount !== undefined && pendingAssignmentsCount > 0 && (
            <span className={styles.bottomNavNotificationBadge}>{pendingAssignmentsCount}</span>
          )}
        </Link>
      ))}
    </nav>
  );
}
