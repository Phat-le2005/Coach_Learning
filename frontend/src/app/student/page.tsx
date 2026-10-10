import type { Metadata } from "next";

import { PageState } from "@/components/app-shell/PageState";
import { SessionRecovery } from "@/components/auth/SessionRecovery";
import { SessionHeartbeat } from "@/components/auth/SessionHeartbeat";
import { GradientButton } from "@/components/ui/GradientButton";
import { StudentHome } from "@/features/student-home/StudentHome";
import { toStudentHomeViewModel } from "@/features/student-home/adapter";
import {
  resolveStudentSubjectAccess,
  selectAccessibleSubject,
} from "@/features/self-study/discovery";
import { getPublishedSelfStudySubjectCodes } from "@/features/self-study/server-policy";
import { ApiNetworkError, ApiResponseError, createBackendApiClient } from "@/lib/api/client";
import { requirePageRole } from "@/lib/auth/page-session";
import { readAccessToken } from "@/lib/auth/server";

export const metadata: Metadata = {
  title: "Không gian học tập",
  description: "Tổng quan học tập cá nhân hóa của học sinh EduMS.",
};

function state(kind: "empty" | "unauthorized" | "error", title: string, description: string) {
  return (
    <main style={{ width: "min(100% - 32px, 780px)", margin: "0 auto", paddingTop: "12vh" }}>
      <PageState
        kind={kind}
        title={title}
        description={description}
        action={kind === "error" ? <GradientButton href="/student">Thử lại</GradientButton> : undefined}
      />
    </main>
  );
}

export default async function StudentPage(props: {
  searchParams?: Promise<{ subject_id?: string }>;
}) {
  const session = await requirePageRole("STUDENT", "/student");
  const accessToken = await readAccessToken();
  if (!accessToken) return <SessionRecovery />;

  const searchParams = props.searchParams ? await props.searchParams : undefined;
  const requestedSubjectId = searchParams?.subject_id?.trim() || undefined;

  try {
    const client = createBackendApiClient();
    let learningState = await client.studentLearningState(accessToken);
    let masteryData = null;
    try {
      masteryData = await client.studentMastery(accessToken);
      if (masteryData && masteryData.student_id !== learningState.student_id) {
        masteryData = null;
      }
    } catch {
      // Graceful degradation: Mastery API failure must not break Student Home
      masteryData = null;
    }

    const subjectAccess = resolveStudentSubjectAccess(
      learningState.available_subjects,
      masteryData,
      getPublishedSelfStudySubjectCodes()
    );
    const selectedSubject = selectAccessibleSubject(
      subjectAccess,
      requestedSubjectId,
      learningState.focus_subject_id
    );

    if (requestedSubjectId && !selectedSubject) {
      return state(
        "error",
        "Môn học ngoài phạm vi",
        "Môn học được chọn không thuộc hoạt động của bạn và chưa được phát hành cho chế độ tự học."
      );
    }

    const selectedHasActivity = selectedSubject
      ? learningState.available_subjects.some((subject) => subject.id === selectedSubject.id)
      : false;
    if (
      selectedSubject &&
      selectedHasActivity &&
      learningState.focus_subject_id !== selectedSubject.id
    ) {
      const focusedState = await client.studentLearningState(accessToken, selectedSubject.id);
      if (focusedState.student_id !== learningState.student_id) {
        throw new Error("Student identity changed while resolving the selected subject.");
      }
      learningState = focusedState;
    }

    return (
      <>
        <SessionHeartbeat />
        <StudentHome
          data={toStudentHomeViewModel(
            learningState,
            session.fullName,
            session.email,
            masteryData,
            {
              availableSubjects: subjectAccess.subjects,
              selectedSubjectId: selectedSubject?.id,
              discoveryOnlySubjectIds: subjectAccess.discoveryOnlySubjectIds,
            }
          )}
        />
      </>
    );
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
          "Dịch vụ backend đang bận hoặc phụ thuộc dữ liệu chưa sẵn sàng. EduMS không hiển thị dữ liệu thay thế."
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
}
