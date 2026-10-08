import { DashboardShell } from "@/components/app-shell/DashboardShell";
import { PageState } from "@/components/app-shell/PageState";
import { requirePageRole } from "@/lib/auth/page-session";

export default async function ParentPage() {
  const session = await requirePageRole("PARENT", "/parent");
  return <DashboardShell session={session} title="Đồng hành học tập" description="Phiên phụ huynh được tách biệt và kiểm tra quyền ở server."><PageState kind="empty" title="Chưa có dữ liệu để hiển thị" description="FE-REAL-01 chưa tích hợp dashboard phụ huynh. EduMS không tạo số liệu thay thế khi endpoint chưa có." /></DashboardShell>;
}
