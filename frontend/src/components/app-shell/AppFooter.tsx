import { BookOpen, Compass, GraduationCap, Leaf, Sparkles, Trees } from "lucide-react";
import Link from "next/link";

import styles from "./AppFooter.module.css";

export interface AppFooterProps {
  variant?: "student" | "teacher" | "auth" | "default";
  compact?: boolean;
}

export function AppFooter({ variant = "student", compact = false }: AppFooterProps) {
  if (variant === "teacher") return null;

  const homeHref =
    variant === "auth" ? "/login" : "/student";

  return (
    <footer
      className={`${styles.footer} ${compact ? styles.footerCompact : ""}`}
      aria-label="Chân trang EduMS"
    >
      <div className={styles.footerCard}>
        <div className={styles.topGrid}>
          <div className={styles.brandCol}>
            <Link href={homeHref} className={styles.brandLink}>
              <span className={styles.brandMark} aria-hidden="true">
                <Leaf size={19} />
              </span>
              <span className={styles.brandText}>
                <strong>EduMS</strong>
                <span>Living Learning Garden</span>
              </span>
            </Link>
            <p className={styles.brandDesc}>
              Không gian học tập Toán 12 thông minh — kết hợp bản đồ năng lực cá nhân hóa,
              bài làm từng bước có dẫn giải và đồng hành sư phạm theo thời gian thực.
            </p>
            <div className={styles.badgeRow}>
              <span className={styles.badgePill}>
                <Sparkles size={13} aria-hidden="true" />
                Toán 12 · GDPT 2018
              </span>
              <span className={styles.badgePill}>
                <GraduationCap size={13} aria-hidden="true" />
                AI Sư phạm từng bước
              </span>
            </div>
          </div>

          <nav className={styles.navCol} aria-label="Điều hướng không gian học tập">
            <h3 className={styles.colTitle}>Không gian học tập</h3>
            <ul className={styles.linkList}>
              <li>
                <Link href="/student" className={styles.navLink}>
                  <Compass size={14} aria-hidden="true" />
                  Khu vườn học tập
                </Link>
              </li>
              <li>
                <Link href="/student/assignments" className={styles.navLink}>
                  <BookOpen size={14} aria-hidden="true" />
                  Bài tập của lớp
                </Link>
              </li>
              <li>
                <Link href="/student/knowledge" className={styles.navLink}>
                  <Trees size={14} aria-hidden="true" />
                  Vũ trụ tri thức
                </Link>
              </li>
              <li>
                <Link href="/student/theory" className={styles.navLink}>
                  <BookOpen size={14} aria-hidden="true" />
                  Kho lý thuyết
                </Link>
              </li>
              <li>
                <Link href="/student/attempts" className={styles.navLink}>
                  <Sparkles size={14} aria-hidden="true" />
                  Tự luyện toán
                </Link>
              </li>
            </ul>
          </nav>

          <nav className={styles.navCol} aria-label="Tài khoản và vai trò">
            <h3 className={styles.colTitle}>Cổng truy cập</h3>
            <ul className={styles.linkList}>
              <li>
                <Link href="/account" className={styles.navLink}>
                  Hồ sơ tài khoản
                </Link>
              </li>
              <li>
                <Link href="/teacher" className={styles.navLink}>
                  Không gian Giáo viên
                </Link>
              </li>
              <li>
                <Link href="/login" className={styles.navLink}>
                  Đăng nhập / Đăng ký
                </Link>
              </li>
            </ul>
          </nav>

          <div className={styles.navCol}>
            <h3 className={styles.colTitle}>Phương pháp học</h3>
            <ul className={styles.linkList}>
              <li className={styles.infoItem}>Chẩn đoán mầm năng lực theo chuyên đề</li>
              <li className={styles.infoItem}>Nhắc ôn tập ngắt quãng đúng nhịp nhớ</li>
              <li className={styles.infoItem}>Trình bày lời giải & bảng biến thiên chuẩn</li>
              <li className={styles.infoItem}>Lộ trình 7 ngày thích ứng mục tiêu kỳ thi</li>
            </ul>
          </div>
        </div>

        <div className={styles.bottomBar}>
          <p className={styles.copyright}>
            © {new Date().getFullYear()} EduMS · Khu Rừng Tri Thức Toán Học. Bảo lưu mọi quyền.
          </p>
          <div className={styles.bottomMeta}>
            <span>Phiên bản Giáo dục THPT</span>
            <span className={styles.metaDot} aria-hidden="true" />
            <span>Hỗ trợ LaTeX & Nhận diện chữ viết tay</span>
          </div>
        </div>
      </div>
    </footer>
  );
}
