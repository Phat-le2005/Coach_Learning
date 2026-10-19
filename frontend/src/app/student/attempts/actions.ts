"use server";

import { redirect } from "next/navigation";

import { getWorkspaceSubjects } from "@/features/math-workspace/entry-service";
import { ApiResponseError, createBackendApiClient } from "@/lib/api/client";
import { requirePageRole } from "@/lib/auth/page-session";
import { readAccessToken } from "@/lib/auth/server";

export interface StartWorkspaceState {
  error: string | null;
}

export async function startWorkspaceAction(
  _previous: StartWorkspaceState,
  formData: FormData,
): Promise<StartWorkspaceState> {
  await requirePageRole("STUDENT", "/student/attempts");
  const accessToken = await readAccessToken();
  if (!accessToken) return { error: "Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại." };

  const requestedSubjectId = formData.get("subject_id");
  if (typeof requestedSubjectId !== "string") return { error: "Vui lòng chọn môn học." };

  let attemptId: string;
  try {
    const subjects = await getWorkspaceSubjects(accessToken);
    const subject = subjects.find((item) => item.id === requestedSubjectId);
    if (!subject) return { error: "Môn học này chưa được phát hành cho tài khoản của bạn." };

    const client = createBackendApiClient();
    const session = await client.createPracticeSession(accessToken, subject.id);
    const problem = await client.getMathPracticeNextProblem(accessToken, session.id);
    const attempt = await client.createMathAttempt(accessToken, session.id, problem.id);
    attemptId = attempt.id;
  } catch (error) {
    if (error instanceof ApiResponseError) {
      if (error.code === "NO_QUESTIONS_AVAILABLE" || error.code === "NO_AVAILABLE_QUESTION") {
        return { error: "Môn này chưa có câu hỏi đã duyệt phù hợp để mở trang làm bài." };
      }
      if (error.code === "QUESTION_GROUP_NOT_SUPPORTED") {
        return { error: "Hiện chỉ có nhóm câu hỏi; trang viết bài cá nhân chưa hỗ trợ dạng này." };
      }
      if (error.status === 401) return { error: "Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại." };
      return { error: "Chưa thể bắt đầu bài làm. Vui lòng thử lại sau." };
    }
    return { error: "Không thể kết nối dịch vụ làm bài. Vui lòng thử lại." };
  }
  redirect(`/student/attempts/${attemptId}`);
}
