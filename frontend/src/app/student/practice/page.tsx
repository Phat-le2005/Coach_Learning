import type { Metadata } from "next";
import { redirect } from "next/navigation";

import { PageState } from "@/components/app-shell/PageState";
import { SessionRecovery } from "@/components/auth/SessionRecovery";
import { GradientButton } from "@/components/ui/GradientButton";
import { getWorkspaceSubjects } from "@/features/math-workspace/entry-service";
import { ApiResponseError, createBackendApiClient } from "@/lib/api/client";
import { requirePageRole } from "@/lib/auth/page-session";
import { readAccessToken } from "@/lib/auth/server";

export const metadata: Metadata = {
  title: "Khởi tạo bài tập luyện tập · EduMS",
  description: "Khởi tạo không gian giải toán từng bước từ ngân hàng câu hỏi hệ thống theo lộ trình thích ứng.",
};

const UUID_REGEX = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export default async function StudentPracticeLaunchPage(props: {
  searchParams?: Promise<{
    problem_type_id?: string;
    concept_id?: string;
    subject_id?: string;
  }>;
}) {
  await requirePageRole("STUDENT", "/student/practice");
  const accessToken = await readAccessToken();
  if (!accessToken) return <SessionRecovery />;

  const params = props.searchParams ? await props.searchParams : undefined;
  const rawPtId = params?.problem_type_id?.trim();
  const rawConceptId = params?.concept_id?.trim();
  const rawSubjectId = params?.subject_id?.trim();

  const problemTypeId = rawPtId && UUID_REGEX.test(rawPtId) ? rawPtId : undefined;
  const conceptId = rawConceptId && UUID_REGEX.test(rawConceptId) ? rawConceptId : undefined;

  let targetAttemptId: string | null = null;
  let errorTitle = "Không thể khởi tạo bài tập luyện tập";
  let errorDescription =
    "Hệ thống chưa thể chọn bài tập phù hợp ngay lúc này. Vui lòng thử lại hoặc quay về Vũ trụ Tri thức.";

  try {
    const subjects = await getWorkspaceSubjects(accessToken);
    const subject =
      (rawSubjectId ? subjects.find((s) => s.id === rawSubjectId) : undefined) ?? subjects[0];

    if (!subject) {
      return (
        <main style={{ width: "min(100% - 32px, 780px)", margin: "0 auto", paddingTop: "12vh" }}>
          <PageState
            kind="empty"
            title="Chưa có môn học khả dụng"
            description="Tài khoản của bạn hiện chưa có môn học nào được kích hoạt để bắt đầu luyện tập."
            action={<GradientButton href="/student/knowledge">Về Vũ trụ Tri thức</GradientButton>}
          />
        </main>
      );
    }

    const client = createBackendApiClient();

    // 1. Try targeted practice session scoped to the selected 3D node (problem_type_id / concept_id)
    let session = await client.createPracticeSession(accessToken, subject.id, {
      problemTypeIds: problemTypeId ? [problemTypeId] : [],
      conceptIds: conceptId ? [conceptId] : [],
      sessionType: "PRACTICE",
    });

    let problem;
    try {
      problem = await client.getMathPracticeNextProblem(accessToken, session.id);
    } catch (innerErr) {
      // Graceful fallback: if this specific node only has question groups or no standalone item yet,
      // fall back to subject-level approved canonical problem so the student is never blocked.
      if (problemTypeId || conceptId) {
        session = await client.createPracticeSession(accessToken, subject.id);
        problem = await client.getMathPracticeNextProblem(accessToken, session.id);
      } else {
        throw innerErr;
      }
    }

    const attempt = await client.createMathAttempt(accessToken, session.id, problem.id);
    targetAttemptId = attempt.id;
  } catch (error) {
    if (error instanceof ApiResponseError) {
      if (error.status === 401) return <SessionRecovery />;
      if (error.code === "NO_QUESTIONS_AVAILABLE" || error.code === "NO_AVAILABLE_QUESTION") {
        errorTitle = "Chưa có câu hỏi tự luận cho dạng bài này";
        errorDescription =
          "Ngân hàng câu hỏi của dạng bài này đang được cập nhật thêm đề tự luận mới.";
      }
    }
  }

  if (targetAttemptId) {
    redirect(`/student/attempts/${targetAttemptId}`);
  }

  return (
    <main style={{ width: "min(100% - 32px, 780px)", margin: "0 auto", paddingTop: "12vh" }}>
      <PageState
        kind="error"
        title={errorTitle}
        description={errorDescription}
        action={<GradientButton href="/student/knowledge">Quay lại Vũ trụ Tri thức 3D</GradientButton>}
      />
    </main>
  );
}
