import type { Metadata } from "next";

import { PageState } from "@/components/app-shell/PageState";
import { SessionHeartbeat } from "@/components/auth/SessionHeartbeat";
import { SessionRecovery } from "@/components/auth/SessionRecovery";
import { GradientButton } from "@/components/ui/GradientButton";
import { getWorkspaceSubjects } from "@/features/math-workspace/entry-service";
import {
  parseAttemptsPageParam,
  parseAttemptsStatusParam,
  toStudentAttemptsViewModel,
} from "@/features/student-attempts/adapter";
import { StudentAttemptsView } from "@/features/student-attempts/StudentAttemptsView";
import { ApiNetworkError, ApiResponseError, createBackendApiClient } from "@/lib/api/client";
import { requirePageRole } from "@/lib/auth/page-session";
import { readAccessToken } from "@/lib/auth/server";

import styles from "./attempts.module.css";

export const metadata: Metadata = {
  title: "Không gian bài làm · EduMS",
  description: "Nơi lưu giữ từng bước giải trên giấy số và hành trình tiến bộ của học sinh EduMS.",
};

function renderPageState(
  kind: "unauthorized" | "error",
  title: string,
  description: string
) {
  return (
    <main className={styles.errorFallbackShell}>
      <div className={styles.errorFallbackInner}>
        <PageState
          kind={kind}
          title={title}
          description={description}
          action={
            kind === "error" ? (
              <GradientButton href="/student/attempts">Thử lại</GradientButton>
            ) : (
              <GradientButton href="/student">Về Khu vườn học tập</GradientButton>
            )
          }
        />
      </div>
    </main>
  );
}

export interface StudentAttemptsPageProps {
  searchParams?: Promise<{
    page?: string;
    status?: string;
    subject_id?: string;
  }>;
}

export default async function StudentAttemptsPage(props: StudentAttemptsPageProps) {
  const session = await requirePageRole("STUDENT", "/student/attempts");
  const accessToken = await readAccessToken();
  if (!accessToken) return <SessionRecovery />;

  const resolvedSearchParams = props.searchParams ? await props.searchParams : undefined;
  const requestedPage = parseAttemptsPageParam(resolvedSearchParams?.page);
  const activeStatusFilter = parseAttemptsStatusParam(resolvedSearchParams?.status);
  const requestedSubjectId = resolvedSearchParams?.subject_id?.trim() || undefined;

  try {
    const client = createBackendApiClient();
    const PAGE_SIZE = 12;

    const [attemptsResult, inProgressResult, draftResult, subjectsResult] =
      await Promise.allSettled([
        client.listMathAttempts(accessToken, {
          page: requestedPage,
          size: PAGE_SIZE,
          status: activeStatusFilter !== "ALL" ? activeStatusFilter : undefined,
        }),
        client.listMathAttempts(accessToken, {
          page: 1,
          size: 4,
          status: "IN_PROGRESS",
        }),
        client.listMathAttempts(accessToken, {
          page: 1,
          size: 4,
          status: "DRAFT",
        }),
        getWorkspaceSubjects(accessToken),
      ]);

    if (attemptsResult.status === "rejected") {
      throw attemptsResult.reason;
    }

    let attemptsPage = attemptsResult.value;
    // Clamp out-of-range page request to the last valid backend page
    if (attemptsPage.total_pages > 0 && requestedPage > attemptsPage.total_pages) {
      attemptsPage = await client.listMathAttempts(accessToken, {
        page: attemptsPage.total_pages,
        size: PAGE_SIZE,
        status: activeStatusFilter !== "ALL" ? activeStatusFilter : undefined,
      });
    }

    const subjectsLoaded = subjectsResult.status === "fulfilled";
    const subjects = subjectsLoaded ? subjectsResult.value : [];

    const viewModel = toStudentAttemptsViewModel({
      displayName: session.fullName,
      email: session.email,
      subjects,
      subjectsLoaded,
      defaultSubjectId: requestedSubjectId ?? subjects[0]?.id,
      activeStatusFilter,
      attemptsPage,
      inProgressPage:
        inProgressResult.status === "fulfilled" ? inProgressResult.value : null,
      draftPage: draftResult.status === "fulfilled" ? draftResult.value : null,
    });

    return (
      <>
        <SessionHeartbeat />
        <StudentAttemptsView data={viewModel} />
      </>
    );
  } catch (error) {
    if (error instanceof ApiResponseError) {
      if (error.status === 401) return <SessionRecovery />;
      if (error.status === 403) {
        return renderPageState(
          "unauthorized",
          "Không có quyền truy cập bài làm",
          "Tài khoản hiện tại không được cấp quyền đọc danh sách bài làm học sinh."
        );
      }
      if (error.status === 503) {
        return renderPageState(
          "error",
          "Không gian bài làm tạm thời bận",
          "Dịch vụ lưu trữ bài làm đang bảo trì hoặc quá tải. Vui lòng thử lại sau ít phút."
        );
      }
    }
    if (error instanceof ApiNetworkError) {
      return renderPageState(
        "error",
        "Chưa kết nối được dịch vụ bài làm",
        "Không thể kết nối tới EduMS API. Vui lòng kiểm tra backend và kết nối mạng rồi tải lại trang."
      );
    }
    return renderPageState(
      "error",
      "Chưa tải được bài làm",
      "Không thể đọc dữ liệu bài làm đúng contract. Vui lòng kiểm tra backend rồi tải lại trang."
    );
  }
}
