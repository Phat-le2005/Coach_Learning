import type { Metadata } from "next";
import { requirePageRole } from "@/lib/auth/page-session";
import { StudentTheoryClient } from "@/features/theory-maps/StudentTheoryClient";
import { StudentShell } from "@/features/student-home/components/StudentShell";

export const metadata: Metadata = { title: "Kho lý thuyết lớp học · EduMS" };
export default async function StudentTheoryPage() {
  const session = await requirePageRole("STUDENT", "/student/theory");
  return <StudentShell displayName={session.fullName} email={session.email} route="/student/theory"><StudentTheoryClient /></StudentShell>;
}
