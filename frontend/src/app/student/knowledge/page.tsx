import type { Metadata } from "next";

import { PageState } from "@/components/app-shell/PageState";
import { SessionHeartbeat } from "@/components/auth/SessionHeartbeat";
import { SessionRecovery } from "@/components/auth/SessionRecovery";
import { GradientButton } from "@/components/ui/GradientButton";
import { KnowledgeForest } from "@/features/knowledge-forest/KnowledgeForest";
import { toKnowledgeForestViewModel } from "@/features/knowledge-forest/adapter";
import type { KnowledgeForestViewModel } from "@/features/knowledge-forest/types";
import { ForestAtmosphere } from "@/features/student-home/components/ForestAtmosphere";
import { StudentBottomNav } from "@/features/student-home/components/StudentBottomNav";
import { StudentTopNav } from "@/features/student-home/components/StudentTopNav";
import { ApiNetworkError, ApiResponseError, createBackendApiClient } from "@/lib/api/client";
import type { StudentLearningStateRead, StudentMasteryRead } from "@/lib/api/contracts";
import { requirePageRole } from "@/lib/auth/page-session";
import { readAccessToken } from "@/lib/auth/server";

export const metadata: Metadata = {
  title: "Khu Rừng Tri Thức · EduMS",
  description: "Bản đồ tri thức và đo lường năng lực học tập của học sinh trong EduMS.",
};

function state(kind: "empty" | "unauthorized" | "error", title: string, description: string) {
  return (
    <main style={{ width: "min(100% - 32px, 780px)", margin: "0 auto", paddingTop: "12vh" }}>
      <PageState
        kind={kind}
        title={title}
        description={description}
        action={kind === "error" ? <GradientButton href="/student/knowledge">Thử lại</GradientButton> : undefined}
      />
    </main>
  );
}

export default async function StudentKnowledgePage(props: {
  searchParams?: Promise<{ subject_id?: string; node?: string }>;
}) {
  const session = await requirePageRole("STUDENT", "/student/knowledge");
  const accessToken = await readAccessToken();
  if (!accessToken) return <SessionRecovery />;

  const searchParams = props.searchParams ? await props.searchParams : undefined;
  const requestedSubjectId = searchParams?.subject_id?.trim() || undefined;
  const requestedNodeId = searchParams?.node?.trim() || undefined;

  const client = createBackendApiClient();
  let learningState: StudentLearningStateRead;
  let mastery: StudentMasteryRead;

  // 1. Fetch Student Learning State
  try {
    learningState = await client.studentLearningState(accessToken, requestedSubjectId);
  } catch (error) {
    if (error instanceof ApiResponseError) {
      if (error.status === 401) return <SessionRecovery />;
      if (error.status === 403) {
        return state(
          "unauthorized",
          "Không thể đọc Learning State",
          "Backend từ chối quyền truy cập dữ liệu học sinh của tài khoản này."
        );
      }
      if (error.status === 404) {
        if (error.code === "SUBJECT_NOT_FOUND") {
          return state(
            "error",
            "Không tìm thấy môn học",
            "Môn học được yêu cầu không tồn tại hoặc đã bị gỡ khỏi hệ thống."
          );
        }
        return state(
          "empty",
          "Chưa có hồ sơ học tập",
          "Backend chưa có Student Learning State cho tài khoản hiện tại."
        );
      }
      if (error.status === 409) {
        return state(
          "error",
          "Môn học ngoài phạm vi",
          "Môn học được chọn không thuộc danh sách môn học của bạn."
        );
      }
      if (error.status === 503) {
        return state(
          "error",
          "Learning State tạm thời chưa sẵn sàng",
          "Dịch vụ backend đang bận hoặc phụ thuộc dữ liệu chưa sẵn sàng."
        );
      }
    }
    if (error instanceof ApiNetworkError) {
      return state(
        "error",
        "Không kết nối được EduMS API",
        "Hãy kiểm tra backend và kết nối mạng. Không có dữ liệu giả nào được dùng thay thế."
      );
    }
    return state(
      "error",
      "Dữ liệu không đúng contract",
      "Frontend đã từ chối phản hồi không hợp lệ để tránh hiển thị sai dữ liệu học tập."
    );
  }

  // 2. Validate requestedSubjectId strictly belongs to student's available scope
  if (
    requestedSubjectId &&
    !learningState.available_subjects.some((s) => s.id === requestedSubjectId)
  ) {
    return state(
      "error",
      "Môn học ngoài phạm vi",
      "Môn học được yêu cầu không nằm trong danh sách môn học bạn được phân quyền truy cập."
    );
  }

  // 3. Fetch Student Mastery with explicit, distinct outcome handling (P0)
  try {
    mastery = await client.studentMastery(accessToken);
  } catch (error) {
    if (error instanceof ApiResponseError) {
      if (error.status === 401) return <SessionRecovery />;
      if (error.status === 403) {
        return state(
          "unauthorized",
          "Không có quyền đọc dữ liệu tri thức",
          "Tài khoản của bạn không được cấp quyền truy cập bảng đo lường tri thức."
        );
      }
      if (error.status === 404) {
        return state(
          "error",
          "Không tìm thấy dữ liệu tri thức",
          `Không tìm thấy dữ liệu đo lường tri thức cho học sinh (${error.code || "MASTERY_NOT_FOUND"}).`
        );
      }
      if (error.status === 503) {
        return state(
          "error",
          "Dịch vụ tri thức tạm thời chưa sẵn sàng",
          "Máy chủ đo lường tri thức đang bận hoặc đang bảo trì. Vui lòng thử lại sau ít phút."
        );
      }
    }
    if (error instanceof ApiNetworkError) {
      return state(
        "error",
        "Lỗi kết nối máy chủ tri thức",
        "Không thể kết nối đến dịch vụ đo lường tri thức. Vui lòng kiểm tra kết nối mạng và thử lại."
      );
    }
    return state(
      "error",
      "Dữ liệu tri thức không đúng contract",
      "Phản hồi dữ liệu tri thức không tuân thủ OpenAPI contract. Hệ thống từ chối hiển thị để bảo đảm tính chính xác."
    );
  }

  // 4. Validate Student ID Data Isolation
  if (mastery.student_id !== learningState.student_id) {
    return state(
      "error",
      "Lỗi đồng bộ hồ sơ học sinh",
      "Định danh học sinh giữa Learning State và Mastery không khớp nhau. Hệ thống đã ngăn chặn để bảo vệ dữ liệu cá nhân."
    );
  }

  // 5. Construct ViewModel safely
  let viewModel: KnowledgeForestViewModel;
  try {
    viewModel = toKnowledgeForestViewModel(
      mastery,
      learningState.available_subjects,
      requestedSubjectId || learningState.focus_subject_id || undefined,
      learningState.student_id
    );
  } catch (error) {
    return state(
      "error",
      "Dữ liệu tri thức không hợp lệ",
      error instanceof Error ? error.message : "Không thể khởi tạo bản đồ tri thức từ dữ liệu nhận được."
    );
  }

  return (
    <>
      <SessionHeartbeat />
      <ForestAtmosphere />
      <StudentTopNav
        displayName={session.fullName}
        email={session.email}
        currentRoute="/student/knowledge"
        subjectId={viewModel.subject.id}
      />
      <KnowledgeForest
        key={viewModel.subject.id}
        data={viewModel}
        initialSelectedId={requestedNodeId}
      />
      <StudentBottomNav currentRoute="/student/knowledge" subjectId={viewModel.subject.id} />
    </>
  );
}
