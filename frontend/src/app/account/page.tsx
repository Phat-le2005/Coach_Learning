import type { Metadata } from "next";
import Link from "next/link";
import { redirect } from "next/navigation";
import { AccountMenu } from "@/components/auth/AccountMenu";
import { SessionHeartbeat } from "@/components/auth/SessionHeartbeat";
import { BrandMark } from "@/features/student-home/components/BrandMark";
import { StudentShell } from "@/features/student-home/components/StudentShell";
import { readSession } from "@/lib/auth/server";
import styles from "./account.module.css";

export const metadata: Metadata = { title: "Hồ sơ tài khoản", description: "Thông tin tài khoản EduMS đang đăng nhập." };

const roleLabel = { STUDENT: "Học sinh", TEACHER: "Giáo viên", PARENT: "Phụ huynh", ADMIN: "Quản trị" } as const;

export default async function AccountPage() {
  const session = await readSession();
  if (!session) redirect("/login?returnTo=%2Faccount");

  const profile = (
    <section className={styles.card} aria-labelledby="account-title">
      <h1 id="account-title">Hồ sơ của tôi</h1>
      <p className={styles.description}>Thông tin tài khoản đang đăng nhập. Bạn có thể quay lại không gian học tập bất cứ lúc nào.</p>
      <dl className={styles.details}>
        <div><dt>Họ và tên</dt><dd>{session.fullName}</dd></div>
        <div><dt>Email</dt><dd>{session.email}</dd></div>
        <div><dt>Vai trò</dt><dd>{roleLabel[session.role]}</dd></div>
      </dl>
      <Link className={styles.back} href={`/${session.role.toLowerCase()}`}>Quay về không gian của tôi</Link>
    </section>
  );

  if (session.role === "STUDENT") return (
    <StudentShell displayName={session.fullName} email={session.email} route="/account">
      <SessionHeartbeat />
      <main className={styles.studentProfile}>{profile}</main>
    </StudentShell>
  );

  return (
    <main className={styles.page}>
      <SessionHeartbeat />
      <div className={styles.content}>
        <header className={styles.header}>
          <BrandMark />
          <AccountMenu fullName={session.fullName} email={session.email} role={session.role} compact />
        </header>
        {profile}
      </div>

    </main>
  );
}
