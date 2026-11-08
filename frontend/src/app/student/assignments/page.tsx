import type { Metadata } from "next";
import { redirect } from "next/navigation";

import { AppFooter } from "@/components/app-shell/AppFooter";
import { SessionHeartbeat } from "@/components/auth/SessionHeartbeat";
import { StudentShell } from "@/features/student-home/components/StudentShell";
import { requirePageRole } from "@/lib/auth/page-session";
import { readAccessToken } from "@/lib/auth/server";
import { getBackendBaseUrl } from "@/lib/api/client";
import { AssignmentsListClient } from "./AssignmentsListClient";

export const metadata: Metadata = {
  title: "Bài tập từ lớp · EduMS",
  description: "Bảng bài tập, đề luyện tập và bài kiểm tra do Giáo viên giao cho bạn.",
};

export default async function StudentAssignmentsPage() {
  const session = await requirePageRole("STUDENT", "/student/assignments");
  const accessToken = await readAccessToken();

  if (!accessToken) {
    redirect("/login");
  }

  let assignments: any[] = [];
  try {
    const backendUrl = getBackendBaseUrl();
    const res = await fetch(`${backendUrl}/students/me/assignments?limit=100`, {
      headers: {
        Authorization: `Bearer ${accessToken}`,
        Accept: "application/json",
      },
      cache: "no-store",
    });
    if (res.ok) {
      assignments = await res.json();
    }
  } catch {
    assignments = [];
  }

  return (
    <StudentShell displayName={session.fullName} email={session.email} route="/student/assignments" footer={<AppFooter variant="student" compact />}>
      <SessionHeartbeat />
      <AssignmentsListClient
        initialAssignments={assignments}
        studentName={session.fullName || session.email.split("@")[0]}
      />
    </StudentShell>
  );
}
