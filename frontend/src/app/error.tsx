"use client";

import { PageState } from "@/components/app-shell/PageState";
import { GradientButton } from "@/components/ui/GradientButton";

export default function ErrorPage({ reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return <main style={{ width: "min(100% - 32px, 760px)", margin: "0 auto", paddingTop: "12vh" }}><PageState kind="error" title="Không thể tải trang" description="Không có dữ liệu giả được hiển thị. Hãy thử kết nối lại với EduMS." action={<GradientButton onClick={reset}>Thử lại</GradientButton>} /></main>;
}
