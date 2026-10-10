"use client";

import { ChevronDown, Compass, Sprout, TreePine } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import type { ChangeEvent } from "react";

import type { KnowledgeForestViewModel } from "../types";
import styles from "../KnowledgeForest.module.css";

export interface KnowledgeForestHeaderProps {
  data: KnowledgeForestViewModel;
}

export function KnowledgeForestHeader({ data }: KnowledgeForestHeaderProps) {
  const router = useRouter();

  const handleSubjectChange = (event: ChangeEvent<HTMLSelectElement>) => {
    const newSubjectId = event.target.value;
    if (newSubjectId && newSubjectId !== data.subject.id) {
      router.push(`/student/knowledge?subject_id=${encodeURIComponent(newSubjectId)}`);
    }
  };

  const { summary } = data;

  return (
    <header className={styles.header}>
      <div className={styles.headerTop}>
        <nav className={styles.breadcrumb} aria-label="Đường dẫn">
          <Link className={styles.breadcrumbLink} href="/student">
            Trang chủ
          </Link>
          <span aria-hidden="true">/</span>
          <span>Bản đồ tri thức</span>
        </nav>

        {data.availableSubjects.length > 1 ? (
          <div className={styles.subjectSelectorWrap}>
            <select
              id="knowledge-subject-select"
              className={styles.subjectSelect}
              value={data.subject.id}
              onChange={handleSubjectChange}
              aria-label="Chọn môn học để xem bản đồ"
            >
              {data.availableSubjects.map((sub) => (
                <option key={sub.id} value={sub.id}>
                  {sub.name}
                </option>
              ))}
            </select>
            <ChevronDown className={styles.subjectSelectorIcon} size={16} aria-hidden="true" />
          </div>
        ) : (
          <span className={styles.subjectBadge}>
            <Compass size={14} aria-hidden="true" />
            {data.subject.name}
          </span>
        )}
      </div>

      <div className={styles.titleRow}>
        <h1 className={styles.mainTitle}>Khu Rừng Tri Thức</h1>
        {data.accessMode === "SELF_STUDY_DISCOVERY" ? (
          <span className={styles.subjectBadge}>
            <Sprout size={14} aria-hidden="true" />
            Tự học chủ động · {data.subject.name}
          </span>
        ) : data.availableSubjects.length > 1 ? (
          <span className={styles.subjectBadge}>
            <TreePine size={14} aria-hidden="true" />
            {data.subject.name}
          </span>
        ) : null}
      </div>

      <p className={styles.subtitle}>
        {data.accessMode === "SELF_STUDY_DISCOVERY"
          ? "Khám phá chương, chủ đề và dạng bài đã được phát hành mà không cần lớp học. Các trạng thái chưa học là dữ liệu thật; chưa có điểm số nào được giả lập."
          : "Bản đồ năng lực học tập cá nhân hóa được kết nối trực tiếp từ dữ liệu thực tế. Khám phá từng vùng kiến thức, củng cố gốc rễ và theo dõi tiến trình làm chủ môn học."}
      </p>

      {/* Stats Bar */}
      <div className={styles.statsBar} aria-label="Tóm tắt năng lực">
        <div className={styles.statItem}>
          <span className={styles.statLabel}>Độ vững môn học</span>
          <span className={styles.statValue}>
            {summary.masteryScore !== undefined ? `${summary.masteryScore}%` : "—"}
          </span>
          <span className={styles.statSubtext}>
            {summary.attemptCount > 0 ? `${summary.attemptCount} lượt làm bài` : "Chưa đủ dữ liệu"}
          </span>
        </div>

        <div className={styles.statItem}>
          <span className={styles.statLabel}>Tổng dạng bài</span>
          <span className={styles.statValue}>{summary.problemTypeCount}</span>
          <span className={styles.statSubtext}>
            Đã tiếp cận: {summary.startedProblemTypeCount} dạng
          </span>
        </div>

        <div className={styles.statItem}>
          <span className={styles.statLabel}>Đã vững vàng</span>
          <span className={styles.statValue} style={{ color: "var(--mint-700)" }}>
            {summary.masteredCount}
          </span>
          <span className={styles.statSubtext}>Thành thạo ≥ 80%</span>
        </div>

        <div className={styles.statItem}>
          <span className={styles.statLabel}>Cần cải thiện</span>
          <span className={styles.statValue} style={{ color: "var(--coral-500)" }}>
            {summary.weakCount}
          </span>
          <span className={styles.statSubtext}>Lỗ hổng cần bù đắp</span>
        </div>

        <div className={styles.statItem}>
          <span className={styles.statLabel}>Đến hạn ôn</span>
          <span className={styles.statValue} style={{ color: "var(--amber-600)" }}>
            {summary.reviewDueCount}
          </span>
          <span className={styles.statSubtext}>Giãn cách ôn tập</span>
        </div>
      </div>
    </header>
  );
}
