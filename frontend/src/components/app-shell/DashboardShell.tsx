import { BookOpenCheck, LayoutDashboard, Leaf, UsersRound } from "lucide-react";
import Link from "next/link";
import type { ReactNode } from "react";

import type { Role } from "@/lib/api/contracts";
import type { SessionPayload } from "@/lib/auth/session-codec";
import { AccountMenu } from "@/components/auth/AccountMenu";
import { SessionHeartbeat } from "@/components/auth/SessionHeartbeat";

import styles from "./app-shell.module.css";

const labels: Record<Role, string> = { STUDENT: "Học sinh", TEACHER: "Giáo viên", PARENT: "Phụ huynh", ADMIN: "Quản trị" };
const icons: Record<Role, typeof LayoutDashboard> = { STUDENT: Leaf, TEACHER: BookOpenCheck, PARENT: UsersRound, ADMIN: LayoutDashboard };

export interface DashboardShellProps { session: SessionPayload; children: ReactNode; title: string; description: string }

export function DashboardShell({ session, children, title, description }: DashboardShellProps) {
  const RoleIcon = icons[session.role];
  return (
    <div className={styles.canvas}>
      <SessionHeartbeat />
      <header className={styles.header}>
        <Link className={styles.brand} href={`/${session.role.toLowerCase()}`}><span><Leaf size={20} /></span><strong>EduMS</strong></Link>
        <div className={styles.identity}><span>{labels[session.role]}</span><AccountMenu fullName={session.fullName} email={session.email} role={session.role} /></div>
      </header>
      <main className={styles.main}>
        <section className={styles.intro}>
          <span className={styles.roleIcon}><RoleIcon size={24} /></span>
          <div><p>{labels[session.role]} workspace</p><h1>{title}</h1><span>{description}</span></div>
        </section>
        {children}
      </main>
    </div>
  );
}
