import type { Metadata } from "next";
import { notFound, redirect } from "next/navigation";

import { SessionHeartbeat } from "@/components/auth/SessionHeartbeat";
import { StudentShell } from "@/features/student-home/components/StudentShell";
import { getBackendBaseUrl } from "@/lib/api/client";
import { requirePageRole } from "@/lib/auth/page-session";
import { readAccessToken } from "@/lib/auth/server";
import { launchClassroomCanvasAttempt } from "@/lib/classroom-assignments/launch";
import { AssignmentWorkspaceClient } from "./AssignmentWorkspaceClient";

export const metadata: Metadata = {
  title: "Không gian làm bài tập · EduMS",
  description: "Không gian giải toán từng bước trên giấy số và làm bài kiểm tra lớp của học sinh.",
};

interface Props {
  params: Promise<{ assignmentId: string }>;
}

export default async function StudentAssignmentWorkspacePage(props: Props) {
  const { assignmentId } = await props.params;
  const session = await requirePageRole("STUDENT", `/student/assignments/${assignmentId}`);
  const accessToken = await readAccessToken();

  if (!accessToken) {
    redirect("/login");
  }

  // Attempt to launch directly onto the interactive Canvas workspace
  const canvasLaunch = await launchClassroomCanvasAttempt(accessToken, assignmentId);
  if (canvasLaunch?.attemptId) {
    redirect(`/student/attempts/${canvasLaunch.attemptId}`);
  }

  // Fallback if canvas launch not possible
  let assignment: any = null;
  try {
    const backendUrl = getBackendBaseUrl();
    const res = await fetch(
      `${backendUrl}/students/me/assignments/${encodeURIComponent(assignmentId)}`,
      {
        headers: {
          Authorization: `Bearer ${accessToken}`,
          Accept: "application/json",
        },
        cache: "no-store",
      }
    );
    if (res.status === 404) {
      notFound();
    }
    if (res.ok) {
      assignment = await res.json();
    }
  } catch {
    notFound();
  }

  if (!assignment) {
    notFound();
  }

  return (
    <StudentShell displayName={session.fullName} email={session.email} route="/student/assignments">
      <SessionHeartbeat />
      <AssignmentWorkspaceClient initialAssignment={assignment} />
    </StudentShell>
  );
}
