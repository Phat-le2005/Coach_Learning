import { Leaf } from "lucide-react";
import { redirect } from "next/navigation";

import styles from "./page.module.css";

export default function HomePage() {
  if (process.env.NEXT_PUBLIC_UI_PREVIEW_MODE === "true") {
    redirect("/student");
  }

  return (
    <main className={styles.page}>
      <section className={styles.card} aria-labelledby="welcome-title">
        <span className={styles.mark} aria-hidden="true">
          <Leaf size={28} strokeWidth={1.8} />
        </span>
        <p className={styles.eyebrow}>EduMS · Verdant</p>
        <h1 className={styles.title} id="welcome-title">
          Học tập có định hướng.
        </h1>
        <p className={styles.copy}>
          Không gian học tập đang sẵn sàng. Trải nghiệm dành cho học sinh sẽ hiển thị dữ liệu thật sau khi kết nối tài khoản.
        </p>
        <a className={styles.link} href="/student">
          Mở không gian học tập
        </a>
      </section>
    </main>
  );
}
