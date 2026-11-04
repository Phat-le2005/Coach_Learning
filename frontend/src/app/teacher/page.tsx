import type { Metadata } from "next";
import { requirePageRole } from "@/lib/auth/page-session";
import { TeacherDashboardClient, type TabKey } from "@/features/teacher/TeacherDashboardClient";

export const metadata: Metadata = {
  title: "Không gian Giảng dạy · EduMS",
  description: "Cổng quản trị lớp học, kho tài liệu lý thuyết thực hành và giám sát bài làm học sinh.",
};

interface TeacherPageProps {
  searchParams: Promise<{ tab?: string }>;
}

export default async function TeacherPage({ searchParams }: TeacherPageProps) {
  const session = await requirePageRole("TEACHER", "/teacher");
  const params = await searchParams;
  const validTabs: TabKey[] = ["classes", "materials", "theory", "submissions", "analytics"];
  const initialTab: TabKey = validTabs.includes(params?.tab as TabKey) ? (params.tab as TabKey) : "classes";

  return (
    <TeacherDashboardClient
      teacherName={session.fullName || session.email}
      teacherEmail={session.email}
      initialTab={initialTab}
    />
  );
}
