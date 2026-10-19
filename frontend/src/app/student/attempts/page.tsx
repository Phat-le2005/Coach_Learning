import type { Metadata } from "next";
import Link from "next/link";

import { PageState } from "@/components/app-shell/PageState";
import { SessionHeartbeat } from "@/components/auth/SessionHeartbeat";
import { SessionRecovery } from "@/components/auth/SessionRecovery";
import { getWorkspaceSubjects } from "@/features/math-workspace/entry-service";
import { createBackendApiClient } from "@/lib/api/client";
import { requirePageRole } from "@/lib/auth/page-session";
import { readAccessToken } from "@/lib/auth/server";

import { StartWorkspaceForm } from "./StartWorkspaceForm";
import styles from "./attempts.module.css";

export const metadata: Metadata = { title: "Bài làm của tôi · EduMS" };

export default async function StudentAttemptsPage() {
  await requirePageRole("STUDENT", "/student/attempts");
  const accessToken = await readAccessToken();
  if (!accessToken) return <SessionRecovery />;

  try {
    const client = createBackendApiClient();
    const [attemptsResult, subjectsResult] = await Promise.allSettled([
      client.listMathAttempts(accessToken),
      getWorkspaceSubjects(accessToken),
    ]);
    if (attemptsResult.status === "rejected") throw attemptsResult.reason;
    const attempts = attemptsResult.value;
    const subjects = subjectsResult.status === "fulfilled" ? subjectsResult.value : [];

    return (
      <main className={styles.page}>
        <SessionHeartbeat />
        <nav className={styles.breadcrumb} aria-label="Đường dẫn">
          <Link href="/student">Trang học sinh</Link><span aria-hidden="true">/</span><span>Bài làm của tôi</span>
        </nav>
        <header className={styles.header}>
          <span className={styles.eyebrow}>Learning Forest · Không gian giải Toán</span>
          <h1>Bài làm của tôi</h1>
          <p>Viết lời giải trên giấy số, lưu nét viết và xem gợi ý nhận diện công thức trước khi xác nhận.</p>
        </header>
        <section className={styles.panel} aria-labelledby="start-heading">
          <h2 id="start-heading">Bắt đầu bài mới</h2>
          <p>Hệ thống chỉ chọn câu hỏi thực đã được duyệt. Nếu chưa có câu hỏi phù hợp, bạn sẽ nhận thông báo rõ ràng.</p>
          {subjectsResult.status === "fulfilled"
            ? <StartWorkspaceForm subjects={subjects} />
            : <p>Chưa tải được danh sách môn học để bắt đầu bài mới. Bạn vẫn có thể mở các bài làm cũ bên dưới.</p>}
        </section>
        <section className={styles.panel} aria-labelledby="history-heading">
          <h2 id="history-heading">Các lượt làm gần đây</h2>
          {attempts.items.length === 0 ? (
            <p>Bạn chưa có lượt làm bài nào. Hãy chọn môn học ở trên để bắt đầu.</p>
          ) : (
            <ul className={styles.attemptList}>
              {attempts.items.map((attempt) => (
                <li key={attempt.id}>
                  <Link href={`/student/attempts/${attempt.id}`}>
                    <span>Bài làm {attempt.created_at ? new Date(attempt.created_at).toLocaleString("vi-VN") : attempt.id.slice(0, 8)}</span>
                    <span className={styles.status}>{attempt.status}</span>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </section>
      </main>
    );
  } catch {
    return <main className={styles.page}><PageState kind="error" title="Chưa tải được bài làm" description="Không thể kết nối dữ liệu bài làm. Vui lòng kiểm tra backend rồi tải lại trang." action={<Link href="/student/attempts">Thử lại</Link>} /></main>;
  }
}
