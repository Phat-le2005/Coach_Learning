import { BookOpen, ClipboardCheck, House, Sparkles, Waypoints } from "lucide-react";
import Link from "next/link";

import styles from "../StudentHome.module.css";

export interface StudentBottomNavProps {
  currentRoute?: string;
  subjectId?: string;
}

export function StudentBottomNav({ currentRoute = "/student", subjectId }: StudentBottomNavProps) {
  const isKnowledge = currentRoute.startsWith("/student/knowledge");
  const isHome = currentRoute === "/student" || (!isKnowledge && currentRoute.startsWith("/student"));

  const knowledgeHref = subjectId
    ? `/student/knowledge?subject_id=${encodeURIComponent(subjectId)}`
    : "/student/knowledge";

  const homeHref = subjectId ? `/student?subject_id=${encodeURIComponent(subjectId)}` : "/student";

  const items = [
    { label: "Home", href: homeHref, icon: House, current: isHome },
    { label: "Bản đồ", href: knowledgeHref, icon: Waypoints, current: isKnowledge },
    { label: "Nhiệm vụ", href: isHome ? "#learning-pulse" : `${homeHref}#learning-pulse`, icon: BookOpen, current: false },
    { label: "Ưu tiên", href: isHome ? "#priority-path" : `${homeHref}#priority-path`, icon: ClipboardCheck, current: false },
    { label: "Coach", href: isHome ? "#coach" : `${homeHref}#coach`, icon: Sparkles, current: false },
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
