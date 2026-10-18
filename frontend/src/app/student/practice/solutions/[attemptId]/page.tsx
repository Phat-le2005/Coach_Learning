import type { Metadata } from "next";
import { PageState } from "@/components/app-shell/PageState";
import { SessionHeartbeat } from "@/components/auth/SessionHeartbeat";
import { SessionRecovery } from "@/components/auth/SessionRecovery";
import { GradientButton } from "@/components/ui/GradientButton";
import { MathSolutionSolver } from "@/features/math-solver/MathSolutionSolver";
import type { SolutionSolverAttempt } from "@/features/math-solver/types";
import { createBackendApiClient, ApiResponseError, getBackendBaseUrl } from "@/lib/api/client";
import type { ProblemRead } from "@/lib/api/contracts";
import { requirePageRole } from "@/lib/auth/page-session";
import { readAccessToken } from "@/lib/auth/server";

export const metadata: Metadata = {
  title: "Giải toán theo bước · EduMS",
  description: "Không gian giải toán theo bước tương tác, biên tập bảng xét dấu và kiểm thử lịch sử lời giải.",
};

interface SolutionPageProps {
  params: Promise<{ attemptId: string }>;
}

export default async function StudentSolutionPage(props: SolutionPageProps) {
  const { attemptId } = await props.params;
  const targetPath = `/student/practice/solutions/${attemptId}`;
  await requirePageRole("STUDENT", targetPath);

  const accessToken = await readAccessToken();
  if (!accessToken) return <SessionRecovery />;

  const apiClient = createBackendApiClient();
  let initialAttempt: SolutionSolverAttempt | null = null;
  let initialProblem: ProblemRead | null = null;
  let notFoundError = false;
  let forbiddenError = false;

  try {
    const backendBase = getBackendBaseUrl();
    const headers = {
      Authorization: `Bearer ${accessToken}`,
      Accept: "application/json",
    };

    const [attemptRes, problemRes] = await Promise.allSettled([
      fetch(`${backendBase}/api/v2/math-solutions/attempts/${attemptId}`, {
        headers,
        cache: "no-store",
      }),
      apiClient.getMathAttemptProblem(accessToken, attemptId),
    ]);

    if (attemptRes.status === "fulfilled") {
      const resp = attemptRes.value;
      if (resp.status === 404) notFoundError = true;
      else if (resp.status === 403) forbiddenError = true;
      else if (resp.ok) {
        initialAttempt = (await resp.json()) as SolutionSolverAttempt;
      }
    }

    if (problemRes.status === "fulfilled") {
      initialProblem = problemRes.value;
    } else {
      const err = problemRes.reason;
      if (err instanceof ApiResponseError && err.status === 404) notFoundError = true;
      if (err instanceof ApiResponseError && err.status === 403) forbiddenError = true;
    }
  } catch {
    // Tolerant SSR fallback; client will load via active session
  }

  if (notFoundError) {
    return (
      <main style={{ width: "min(100% - 32px, 780px)", margin: "0 auto", paddingTop: "12vh" }}>
        <PageState
          kind="error"
          title="Không tìm thấy lượt làm bài"
          description="Lượt giải bài toán này không tồn tại hoặc bạn không có quyền truy cập."
          action={<GradientButton href="/student">Về trang chủ</GradientButton>}
        />
      </main>
    );
  }

  if (forbiddenError) {
    return (
      <main style={{ width: "min(100% - 32px, 780px)", margin: "0 auto", paddingTop: "12vh" }}>
        <PageState
          kind="unauthorized"
          title="Không có quyền truy cập"
          description="Lượt giải bài toán này thuộc về học sinh khác."
          action={<GradientButton href="/student">Về trang chủ</GradientButton>}
        />
      </main>
    );
  }

  return (
    <>
      <SessionHeartbeat />
      <MathSolutionSolver
        attemptId={attemptId}
        accessToken={accessToken}
        initialAttempt={initialAttempt}
        initialProblem={initialProblem}
      />
    </>
  );
}
