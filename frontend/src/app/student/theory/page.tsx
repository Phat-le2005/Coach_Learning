import type { Metadata } from "next";

import { AppFooter } from "@/components/app-shell/AppFooter";
import { SessionHeartbeat } from "@/components/auth/SessionHeartbeat";
import { StudentBottomNav } from "@/features/student-home/components/StudentBottomNav";
import { StudentTopNav } from "@/features/student-home/components/StudentTopNav";
import { StudentTheoryClient } from "@/features/theory-maps/StudentTheoryClient";
import styles from "@/features/theory-maps/TheoryMaps.module.css";
import { requirePageRole } from "@/lib/auth/page-session";

export const metadata: Metadata = {
  title: "Kho lý thuyết lớp học · EduMS",
  description: "Sơ đồ tư duy lý thuyết, sổ tay công thức và tài liệu gốc của lớp học.",
};

export default async function StudentTheoryPage() {
  const session = await requirePageRole("STUDENT", "/student/theory");
  return (
    <div className={styles.studentPageShell}>
      <SessionHeartbeat />
      <StudentTopNav
        displayName={session.fullName}
        email={session.email}
        currentRoute="/student/theory"
      />
      <StudentTheoryClient />
      <AppFooter variant="student" compact />
      <StudentBottomNav currentRoute="/student/theory" />
    </div>
  );
}
