import type { Metadata } from "next";
import { requirePageRole } from "@/lib/auth/page-session";
import { AdminDashboardClient, type AdminTabKey } from "@/features/admin/AdminDashboardClient";

export const metadata: Metadata = {
  title: "Quản trị Hệ thống · EduMS",
  description: "Trung tâm quản trị chương trình học, ngân hàng câu hỏi, giám sát vận hành AI và danh mục tuyển sinh.",
};

interface AdminPageProps {
  searchParams?: Promise<{ tab?: string }>;
}

export default async function AdminPage({ searchParams }: AdminPageProps) {
  const session = await requirePageRole("ADMIN", "/admin");
  const params = searchParams ? await searchParams : undefined;
  const validTabs: AdminTabKey[] = ["curriculum", "question-supply", "ai-governance", "admission"];
  const initialTab: AdminTabKey = validTabs.includes(params?.tab as AdminTabKey)
    ? (params?.tab as AdminTabKey)
    : "curriculum";

  return (
    <AdminDashboardClient
      adminName={session.fullName || session.email}
      adminEmail={session.email}
      initialTab={initialTab}
    />
  );
}
