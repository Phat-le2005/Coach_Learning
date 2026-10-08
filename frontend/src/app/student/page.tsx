import type { Metadata } from "next";

import { PageState } from "@/components/app-shell/PageState";
import { SessionRecovery } from "@/components/auth/SessionRecovery";
import { SessionHeartbeat } from "@/components/auth/SessionHeartbeat";
import { GradientButton } from "@/components/ui/GradientButton";
import { StudentHome } from "@/features/student-home/StudentHome";
import { toStudentHomeViewModel } from "@/features/student-home/adapter";
import { ApiNetworkError, ApiResponseError, createBackendApiClient } from "@/lib/api/client";
import { requirePageRole } from "@/lib/auth/page-session";
import { readAccessToken } from "@/lib/auth/server";

export const metadata: Metadata = {
  title: "Không gian học tập",
  description: "Tổng quan học tập cá nhân hóa của học sinh EduMS.",
};

function state(kind: "empty" | "unauthorized" | "error", title: string, description: string) {
  return <main style={{ width: "min(100% - 32px, 780px)", margin: "0 auto", paddingTop: "12vh" }}><PageState kind={kind} title={title} description={description} action={kind === "error" ? <GradientButton href="/student">Thử lại</GradientButton> : undefined} /></main>;
}

export default async function StudentPage() {
  const session = await requirePageRole("STUDENT", "/student");
  const accessToken = await readAccessToken();
  if (!accessToken) return <SessionRecovery />;
  try {
    const learningState = await createBackendApiClient().studentLearningState(accessToken);
    return <><SessionHeartbeat /><StudentHome data={toStudentHomeViewModel(learningState, session.fullName, session.email)} /></>;
  } catch (error) {
    if (error instanceof ApiResponseError) {
      if (error.status === 401) return <SessionRecovery />;
      if (error.status === 403) return state("unauthorized", "Không thể đọc Learning State", "Backend từ chối quyền truy cập dữ liệu học sinh của tài khoản này.");
      if (error.status === 404) return state("empty", "Chưa có hồ sơ học tập", "Backend chưa có Student Learning State cho tài khoản hiện tại.");
      if (error.status === 503) return state("error", "Learning State tạm thời chưa sẵn sàng", "Dịch vụ backend đang bận hoặc phụ thuộc dữ liệu chưa sẵn sàng. EduMS không hiển thị dữ liệu thay thế.");
    }
    if (error instanceof ApiNetworkError) return state("error", "Không kết nối được EduMS API", "Hãy kiểm tra backend và kết nối mạng. Không có dữ liệu giả nào được dùng thay thế.");
    return state("error", "Dữ liệu không đúng contract", "Frontend đã từ chối phản hồi không hợp lệ để tránh hiển thị sai dữ liệu học tập.");
  }
}
