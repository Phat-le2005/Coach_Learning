import { PageState } from "@/components/app-shell/PageState";

export default function UnauthorizedPage() {
  return <main style={{ width: "min(100% - 32px, 760px)", margin: "0 auto", paddingTop: "12vh" }}><PageState kind="unauthorized" title="Bạn không có quyền mở khu vực này" description="Vai trò trong phiên đăng nhập không phù hợp với dashboard được yêu cầu. Quyền truy cập vẫn được backend kiểm tra cho từng API." /></main>;
}
