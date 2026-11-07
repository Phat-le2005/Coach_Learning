import type { Metadata } from "next";
import { redirect } from "next/navigation";

export const metadata: Metadata = {
  title: "Bài tập từ lớp · EduMS",
  description: "Bảng bài tập, đề luyện tập và bài kiểm tra do Giáo viên giao cho bạn.",
};

export default function StudentAssignmentsPage() {
  redirect("/student/attempts?tab=classroom");
}
