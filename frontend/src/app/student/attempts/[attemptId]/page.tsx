import type { Metadata } from "next";
import { PageState } from "@/components/app-shell/PageState";
import { SessionHeartbeat } from "@/components/auth/SessionHeartbeat";
import { SessionRecovery } from "@/components/auth/SessionRecovery";
import { GradientButton } from "@/components/ui/GradientButton";
import { MathWorkspace } from "@/features/math-workspace/MathWorkspace";
import { createBackendApiClient, ApiResponseError } from "@/lib/api/client";
import type {
  InkDocumentRead,
  InkPageRead,
  ProblemRead,
  SolutionAttemptRead,
} from "@/lib/api/contracts";
import { requirePageRole } from "@/lib/auth/page-session";
import { readAccessToken } from "@/lib/auth/server";

export const metadata: Metadata = {
  title: "Không gian làm bài Toán · EduMS",
  description: "Không gian giải bài toán viết tay tương tác, lưu trữ đa trang và nhận diện lời giải.",
};

interface AttemptPageProps {
  params: Promise<{ attemptId: string }>;
}

export default async function StudentAttemptPage(props: AttemptPageProps) {
  const { attemptId } = await props.params;
  const targetPath = `/student/attempts/${attemptId}`;
  await requirePageRole("STUDENT", targetPath);

  const accessToken = await readAccessToken();
  if (!accessToken) return <SessionRecovery />;

  const apiClient = createBackendApiClient();

  let initialAttempt: SolutionAttemptRead | null = null;
  let initialProblem: ProblemRead | null = null;
  let initialDocument: InkDocumentRead | null = null;
  let initialPage: InkPageRead | null = null;
  let notFoundError = false;
  let forbiddenError = false;

  try {
    const [attemptRes, problemRes, docRes] = await Promise.allSettled([
      apiClient.getMathAttempt(accessToken, attemptId),
      apiClient.getMathAttemptProblem(accessToken, attemptId),
      apiClient.getMathInkDocument(accessToken, attemptId),
    ]);

    if (attemptRes.status === "fulfilled") {
      initialAttempt = attemptRes.value;
    } else {
      const err = attemptRes.reason;
      if (err instanceof ApiResponseError && err.status === 404) notFoundError = true;
      if (err instanceof ApiResponseError && err.status === 403) forbiddenError = true;
    }

    if (problemRes.status === "fulfilled") {
      initialProblem = problemRes.value;
    }

    if (docRes.status === "fulfilled") {
      initialDocument = docRes.value;
      if (initialDocument.pages && initialDocument.pages.length > 0) {
        try {
          initialPage = await apiClient.getMathInkPage(accessToken, attemptId, 0);
        } catch {
          // Page 0 not loaded, start fresh
        }
      }
    }
  } catch {
    // Tolerant SSR fallback; client will retry via active session
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
      <MathWorkspace
        attemptId={attemptId}
        accessToken={accessToken}
        initialAttempt={initialAttempt}
        initialProblem={initialProblem}
        initialDocument={initialDocument}
        initialPage={initialPage}
      />
    </>
  );
}
