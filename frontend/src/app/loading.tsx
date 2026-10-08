import { PageState } from "@/components/app-shell/PageState";

export default function Loading() {
  return <main style={{ width: "min(100% - 32px, 760px)", margin: "0 auto", paddingTop: "12vh" }}><PageState kind="loading" title="Đang mở không gian của bạn" description="EduMS đang kiểm tra phiên và tải dữ liệu thật." /></main>;
}
