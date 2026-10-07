import { Bell, Flame } from "lucide-react";

import { IconButton } from "@/components/ui/IconButton";

import { BrandMark } from "./BrandMark";
import styles from "../StudentHome.module.css";

export interface StudentTopNavProps {
  displayName: string;
  avatarLabel: string;
  activeDays: number;
}

const navItems = [
  { label: "Tổng quan", href: "#student-home", current: true },
  { label: "Học tập", href: "#learning-pulse" },
  { label: "Bản đồ tri thức", href: "#knowledge-garden" },
  { label: "Bài tập", href: "#priority-path" },
  { label: "Thi thử", href: "#coach" },
];

export function StudentTopNav({ displayName, avatarLabel, activeDays }: StudentTopNavProps) {
  return (
    <header className={styles.topNavWrap}>
      <nav className={styles.topNav} aria-label="Điều hướng học sinh">
        <a className={styles.brandLink} href="#student-home">
          <BrandMark />
        </a>

        <div className={styles.desktopNav}>
          {navItems.map((item) => (
            <a
              className={item.current ? styles.desktopNavActive : styles.desktopNavLink}
              href={item.href}
              aria-current={item.current ? "page" : undefined}
              key={item.label}
            >
              {item.label}
            </a>
          ))}
        </div>

        <div className={styles.navActions}>
          {activeDays > 0 ? (
            <span className={styles.momentumPill} aria-label={`${activeDays} ngày học liên tục`}>
              <Flame size={17} strokeWidth={2} aria-hidden="true" />
              <strong>{activeDays}</strong>
              <span>ngày</span>
            </span>
          ) : null}
          <IconButton label="Thông báo">
            <Bell size={19} strokeWidth={1.9} />
          </IconButton>
          <button className={styles.avatarButton} type="button" aria-label={`Tài khoản của ${displayName}`}>
            {avatarLabel}
          </button>
        </div>
      </nav>
    </header>
  );
}
