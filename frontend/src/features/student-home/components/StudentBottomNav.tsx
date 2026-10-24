import { BookOpen, Edit3, House, Orbit } from "lucide-react";
import Link from "next/link";

import styles from "../StudentHome.module.css";

export interface StudentBottomNavProps {
  currentRoute?: string;
  subjectId?: string;
}

export function StudentBottomNav({ currentRoute = "/student", subjectId }: StudentBottomNavProps) {
  const isKnowledge = currentRoute.startsWith("/student/knowledge");
  const isAttempts = currentRoute.startsWith("/student/attempts");
  const isHome = currentRoute === "/student" || (!isKnowledge && !isAttempts && currentRoute.startsWith("/student"));

  const knowledgeHref = subjectId
    ? `/student/knowledge?subject_id=${encodeURIComponent(subjectId)}`
    : "/student/knowledge";

  const homeHref = subjectId ? `/student?subject_id=${encodeURIComponent(subjectId)}` : "/student";

  const items = [
    { label: "Tổng quan", href: homeHref, icon: House, current: isHome },
    { label: "Vũ trụ", href: knowledgeHref, icon: Orbit, current: isKnowledge },
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
        </Link>
      ))}
    </nav>
  );
}
