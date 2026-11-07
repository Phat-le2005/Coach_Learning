import type { Metadata } from "next";
import { redirect, notFound } from "next/navigation";

import { requirePageRole } from "@/lib/auth/page-session";
import { readAccessToken } from "@/lib/auth/server";
import { getBackendBaseUrl } from "@/lib/api/client";
import { AssignmentWorkspaceClient } from "./AssignmentWorkspaceClient";

export const metadata: Metadata = {
  title: "Không gian làm bài tập · EduMS",
  description: "Không gian giải toán từng bước và làm bài kiểm tra lớp của học sinh.",
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

  return <AssignmentWorkspaceClient initialAssignment={assignment} />;
}
