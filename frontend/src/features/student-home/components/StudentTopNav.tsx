"use client";

import { useEffect, useState } from "react";
import { Flame, Sparkles, Wind } from "lucide-react";
import Link from "next/link";

import { AccountMenu } from "@/components/auth/AccountMenu";

import styles from "../StudentHome.module.css";
import ui from "../HomeRefresh.module.css";
import { useHomeAppearance } from "./HomeAppearance";
import { HomeIcon } from "./HomeIcon";
import { BrandMark } from "./BrandMark";
import nav from "./StudentNav.module.css";
import { useGardenMotion } from "./nature/GardenMotionContext";

export interface StudentTopNavProps {
  displayName: string;
  email?: string;
  activeDays?: number;
  currentRoute?: string;
  subjectId?: string;
  showAmbientToggle?: boolean;
  pendingAssignmentsCount?: number;
  refreshed?: boolean;
}

export function StudentTopNav({
  displayName,
  email,
  activeDays,
  currentRoute = "/student",
  subjectId,
  showAmbientToggle = false,
  pendingAssignmentsCount,
  refreshed = false,
}: StudentTopNavProps) {
  const { ambientEnabled, toggleAmbient } = useGardenMotion();
  const { theme, toggleTheme } = useHomeAppearance();
  const [badgeCount, setBadgeCount] = useState<number | undefined>(pendingAssignmentsCount);

  useEffect(() => {
    if (pendingAssignmentsCount !== undefined) {
      setBadgeCount(pendingAssignmentsCount);
      return;
    }
    let ignore = false;
    fetch("/api/student/assignments")
      .then((res) => (res.ok ? res.json() : []))
      .then((list) => {
        if (!ignore && Array.isArray(list)) {
          const count = list.filter(
            (a: any) => a.status === "NOT_STARTED" || a.status === "IN_PROGRESS"
          ).length;
          setBadgeCount(count);
        }
      })
      .catch(() => {});
    return () => {
      ignore = true;
    };
  }, [pendingAssignmentsCount]);

  const isKnowledge = currentRoute.startsWith("/student/knowledge");
  const isAttempts =
    currentRoute.startsWith("/student/attempts") || currentRoute.startsWith("/student/assignments");
  const isTheory = currentRoute.startsWith("/student/theory");
  const isHome =
    currentRoute === "/student" ||
    (!isKnowledge && !isAttempts && !isTheory && currentRoute.startsWith("/student"));

  const knowledgeHref = subjectId
    ? `/student/knowledge?subject_id=${encodeURIComponent(subjectId)}`
    : "/student/knowledge";

  const homeHref = subjectId
    ? `/student?subject_id=${encodeURIComponent(subjectId)}`
    : "/student";

  const attemptsHref =
    (badgeCount ?? 0) > 0 ? "/student/attempts?tab=classroom" : "/student/attempts";

  const navItems = [
    { label: "Khu vườn học tập", href: homeHref, current: isHome, isAttempts: false },
    {
      label: "Bài tập & Luyện tập",
      href: attemptsHref,
      current: isAttempts,
      isAttempts: true,
      badge: badgeCount,
    },
    { label: "Vũ trụ tri thức", href: knowledgeHref, current: isKnowledge, isAttempts: false },
    { label: "Kho lý thuyết", href: "/student/theory", current: isTheory, isAttempts: false },
  ];

  const effectsActive = ambientEnabled;

  return (
    <header className={nav.wrap}>
      <nav className={nav.nav} aria-label="Điều hướng học sinh">
        <Link className={nav.brand} href={homeHref}>
          <BrandMark />
        </Link>

        <div className={nav.links}>
          {navItems.map((item) => (
            <Link
              className={nav.link}
              href={item.href}
              aria-current={item.current ? "page" : undefined}
              key={item.label}
            >
              <span>{item.label}</span>
              {item.isAttempts && item.badge !== undefined && item.badge > 0 && (
                <span className={nav.badge}>{item.badge}</span>
              )}
            </Link>
          ))}
        </div>

        <div className={nav.actions}>
          {showAmbientToggle ? (
            <button
              type="button"
              onClick={toggleAmbient}
              className={nav.icon}
              aria-pressed={effectsActive}
              aria-label={effectsActive ? "Tắt hiệu ứng lá rơi" : "Bật hiệu ứng lá rơi"}
              title={
                effectsActive
                  ? "Đang bật chuyển động thiên nhiên (Nhấn để chuyển sang chế độ tĩnh)"
                  : "Đang tắt chuyển động thiên nhiên (Nhấn để bật lại)"
              }
            >
              <HomeIcon name="wind" />
            </button>
          ) : null}

          <button type="button" className={nav.icon} aria-pressed={theme === "dark"} aria-label={theme === "dark" ? "Chuyển sang giao diện sáng" : "Chuyển sang giao diện tối"} title={theme === "dark" ? "Giao diện sáng" : "Giao diện tối"} onClick={toggleTheme}><HomeIcon name={theme === "dark" ? "sun" : "moon"} /></button>
          {!refreshed && activeDays !== undefined && activeDays > 0 ? (
            <span
              className={styles.momentumPill}
              aria-label={`${activeDays} ngày học liên tục`}
            >
              <Flame size={16} strokeWidth={2} aria-hidden="true" />
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
