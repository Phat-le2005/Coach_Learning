import { DashboardShell } from "@/components/app-shell/DashboardShell";
import { PageState } from "@/components/app-shell/PageState";
import { requirePageRole } from "@/lib/auth/page-session";

export default async function TeacherPage() {
  const session = await requirePageRole("TEACHER", "/teacher");
  return <DashboardShell session={session} title="Không gian giảng dạy" description="Nền tảng xác thực đã sẵn sàng cho dữ liệu giáo viên."><PageState kind="empty" title="Dashboard đang chờ kết nối" description="FE-REAL-01 chỉ thiết lập shell và bảo vệ vai trò. Dữ liệu lớp học sẽ được tích hợp ở giai đoạn riêng." /></DashboardShell>;
}
