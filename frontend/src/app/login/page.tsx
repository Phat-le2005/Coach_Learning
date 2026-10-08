import type { Metadata } from "next";

import { LoginForm } from "@/components/auth/LoginForm";
import { BrandMark } from "@/features/student-home/components/BrandMark";
import { redirectAuthenticatedUser } from "@/lib/auth/page-session";
import { safeReturnPath } from "@/lib/auth/rbac";

import styles from "./login.module.css";

export const metadata: Metadata = { title: "Đăng nhập", description: "Đăng nhập an toàn vào EduMS." };
interface LoginPageProps { searchParams: Promise<{ returnTo?: string; reason?: string }> }

export default async function LoginPage({ searchParams }: LoginPageProps) {
  await redirectAuthenticatedUser();
  const query = await searchParams;
  return (
    <main className={styles.page}>
      <div className={styles.sky} aria-hidden="true"><span /><span /><span /></div>
      <section className={styles.stage} aria-labelledby="login-title">
        <div className={styles.story}>
          <BrandMark />
          <p className={styles.eyebrow}>Learning Forest</p>
          <h1 id="login-title">Trở lại khu rừng tri thức của bạn.</h1>
          <p>Mỗi phiên học tiếp tục đúng từ dữ liệu thật của bạn trong EduMS.</p>
          <div className={styles.tree} aria-hidden="true"><i /><b /><b /><b /><span /><span /><span /><span /></div>
        </div>
        <div className={styles.card}>
          <div className={styles.cardHeader}>
            <span>EduMS secure access</span>
            <h2>Đăng nhập</h2>
            <p>Sử dụng tài khoản đã được cấp cho vai trò của bạn.</p>
          </div>
          <LoginForm returnTo={safeReturnPath(query.returnTo ?? null) ?? undefined} expired={query.reason === "expired"} />
        </div>
      </section>
    </main>
  );
}
