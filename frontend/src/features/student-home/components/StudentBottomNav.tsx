import Link from "next/link";
import { HomeIcon } from "./HomeIcon";
import nav from "./StudentNav.module.css";
export interface StudentBottomNavProps { currentRoute?: string; subjectId?: string; pendingAssignmentsCount?: number; refreshed?: boolean; }
export function StudentBottomNav({ currentRoute = "/student", subjectId, pendingAssignmentsCount }: StudentBottomNavProps) {
  const subject = subjectId ? `?subject_id=${encodeURIComponent(subjectId)}` : "";
  const items = [
    { label: "Trang chủ", href: `/student${subject}`, icon: "house" as const, active: currentRoute === "/student" },
    { label: "Bài tập", href: "/student/attempts", icon: "pen-nib" as const, active: /\/student\/(attempts|assignments)/.test(currentRoute) },
    { label: "Tri thức", href: `/student/knowledge${subject}`, icon: "graph" as const, active: currentRoute.startsWith("/student/knowledge") },
    { label: "Lý thuyết", href: "/student/theory", icon: "book-open" as const, active: currentRoute.startsWith("/student/theory") },
  ];
  return <nav className={nav.mobile} aria-label="Điều hướng học sinh trên di động">{items.map(item => <Link key={item.label} href={item.href} aria-current={item.active ? "page" : undefined}><HomeIcon name={item.icon} /><span>{item.label}</span>{item.label === "Bài tập" && !!pendingAssignmentsCount && pendingAssignmentsCount > 0 && <span className={nav.badge}>{pendingAssignmentsCount}</span>}</Link>)}</nav>;
}
