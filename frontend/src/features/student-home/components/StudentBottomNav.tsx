import { BookOpen, Bot, ClipboardCheck, House, Waypoints } from "lucide-react";

import styles from "../StudentHome.module.css";

const items = [
  { label: "Home", href: "#student-home", icon: House, current: true },
  { label: "Học", href: "#learning-pulse", icon: BookOpen },
  { label: "Bản đồ", href: "#knowledge-garden", icon: Waypoints },
  { label: "Bài tập", href: "#priority-path", icon: ClipboardCheck },
  { label: "Coach", href: "#coach", icon: Bot },
];

export function StudentBottomNav() {
  return (
    <nav className={styles.bottomNav} aria-label="Điều hướng học sinh trên di động">
      {items.map(({ label, href, icon: Icon, current }) => (
        <a
          className={current ? styles.bottomNavActive : styles.bottomNavItem}
          href={href}
          aria-current={current ? "page" : undefined}
          key={label}
        >
          <Icon size={19} strokeWidth={1.9} aria-hidden="true" />
          <span>{label}</span>
        </a>
      ))}
    </nav>
  );
}
