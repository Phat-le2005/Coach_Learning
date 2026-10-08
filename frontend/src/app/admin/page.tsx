import { DashboardShell } from "@/components/app-shell/DashboardShell";
import { PageState } from "@/components/app-shell/PageState";
import { requirePageRole } from "@/lib/auth/page-session";

export default async function AdminPage() {
  const session = await requirePageRole("ADMIN", "/admin");
  return <DashboardShell session={session} title="Quản trị EduMS" description="Quyền ADMIN chỉ được xác lập từ phiên đã ký và backend."><PageState kind="empty" title="Admin shell đã sẵn sàng" description="Không có credential đặc quyền hoặc dữ liệu quản trị được nhúng trong frontend." /></DashboardShell>;
}
