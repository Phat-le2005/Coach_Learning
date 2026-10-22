"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { PageState } from "@/components/app-shell/PageState";
import { GradientButton } from "@/components/ui/GradientButton";
import { BrowserAuthError, refreshBrowserSession } from "@/lib/auth/browser";

export function SessionRecovery() {
  const router = useRouter();
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    let active = true;
    async function recover() {
      try {
        await refreshBrowserSession();
        if (active) router.refresh();
      } catch (error) {
        if (active && error instanceof BrowserAuthError && (error.status === 401 || error.status === 403)) window.location.assign("/login?reason=expired");
        else if (active) setFailed(true);
      }
    }
    void recover();
    return () => { active = false; };
  }, [router]);
  return <main style={{ width: "min(100% - 32px, 760px)", margin: "0 auto", paddingTop: "12vh" }}>{failed ? <PageState kind="error" title="Không thể làm mới phiên" description="Dịch vụ xác thực hiện chưa kết nối được. Không có dữ liệu thay thế được hiển thị." action={<GradientButton onClick={() => window.location.reload()}>Thử lại</GradientButton>} /> : <PageState kind="loading" title="Đang làm mới phiên" description="EduMS đang xác thực lại phiên an toàn trước khi tải dữ liệu học tập." />}</main>;
}
