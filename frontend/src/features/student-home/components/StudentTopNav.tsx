import { Flame } from "lucide-react";
import Link from "next/link";

import { AccountMenu } from "@/components/auth/AccountMenu";

import { BrandMark } from "./BrandMark";
import styles from "../StudentHome.module.css";

export interface StudentTopNavProps {
  displayName: string;
  email?: string;
  activeDays?: number;
  currentRoute?: string;
  subjectId?: string;
}

export function StudentTopNav({
  displayName,
  email,
  activeDays,
  currentRoute = "/student",
  subjectId,
}: StudentTopNavProps) {
  const isKnowledge = currentRoute.startsWith("/student/knowledge");
  const isAttempts = currentRoute.startsWith("/student/attempts");
  const isHome = currentRoute === "/student" || (!isKnowledge && !isAttempts && currentRoute.startsWith("/student"));

  const knowledgeHref = subjectId
    ? `/student/knowledge?subject_id=${encodeURIComponent(subjectId)}`
    : "/student/knowledge";

  const homeHref = subjectId ? `/student?subject_id=${encodeURIComponent(subjectId)}` : "/student";

  const navItems = [
    { label: "Tổng quan", href: homeHref, current: isHome },
    { label: "Vũ trụ tri thức", href: knowledgeHref, current: isKnowledge },
    { label: "Bài làm & Luyện tập", href: "/student/attempts", current: isAttempts },
  ];

  return (
    <header className={styles.topNavWrap}>
      <nav className={styles.topNav} aria-label="Điều hướng học sinh">
        <Link className={styles.brandLink} href={homeHref}>
          <BrandMark />
        </Link>

        <div className={styles.desktopNav}>
          {navItems.map((item) => (
            <Link
              className={item.current ? styles.desktopNavActive : styles.desktopNavLink}
              href={item.href}
              aria-current={item.current ? "page" : undefined}
              key={item.label}
            >
              {item.label}
            </Link>
          ))}
        </div>

        <div className={styles.navActions}>
          {activeDays !== undefined && activeDays > 0 ? (
            <span className={styles.momentumPill} aria-label={`${activeDays} ngày học liên tục`}>
              <Flame size={17} strokeWidth={2} aria-hidden="true" />
              <strong>{activeDays}</strong>
              <span>ngày</span>
            </span>
          ) : null}
          <AccountMenu fullName={displayName} email={email} role="STUDENT" compact />
        </div>
      </nav>
    </header>
  );
}
