import type { Metadata } from "next";
import { requirePageRole } from "@/lib/auth/page-session";
import { TeacherDashboardClient } from "@/features/teacher/TeacherDashboardClient";

export const metadata: Metadata = {
  title: "Không gian Giảng dạy · EduMS",
  description: "Cổng quản trị lớp học, kho tài liệu lý thuyết thực hành và giám sát bài làm học sinh.",
};

export default async function TeacherPage() {
  const session = await requirePageRole("TEACHER", "/teacher");
  return <TeacherDashboardClient teacherName={session.fullName || "Giáo viên Toán"} />;
}
