"use client";

import { BarChart3, AlertTriangle, TrendingDown, BookOpen, CheckCircle2, Award, AlertCircle, HelpCircle } from "lucide-react";
import type { TeacherAnalytics, TeacherClassroom } from "../api";
import styles from "../TeacherDashboard.module.css";

export interface AnalyticsTabProps {
  selectedClass?: TeacherClassroom;
  analytics: TeacherAnalytics | null;
  isLoading: boolean;
}

export function AnalyticsTab({
  selectedClass,
  analytics,
  isLoading,
}: AnalyticsTabProps) {
  const percent = (v: number) => `${Math.round(v * 100)}%`;

  if (!selectedClass) {
    return (
      <div className={styles.sectionCard}>
        <div className={styles.emptyCard}>
          <AlertCircle size={32} className={styles.emptyIcon} aria-hidden="true" />
          <h4 className={styles.emptyTitle}>Chưa chọn lớp học</h4>
          <p className={styles.emptyDesc}>Vui lòng chọn lớp học để xem báo cáo năng lực và sức khỏe học tập.</p>
        </div>
      </div>
    );
  }

  if (isLoading || !analytics) {
    return (
      <div className={styles.sectionCard}>
        <div className={styles.tableLoadingState}>
          <div className={styles.spinner} aria-hidden="true" />
          <p>Đang tổng hợp báo cáo năng lực từ cơ sở dữ liệu thật...</p>
        </div>
      </div>
    );
  }

  const attentionList = analytics.students_needing_attention;
  const weakProblemTypes = analytics.weak_problem_types;
  const chapters = analytics.chapter_progress;
  const subjects = analytics.subject_progress;

  return (
    <div className={styles.tabContentWrap}>
      {/* 1. Cảnh báo can thiệp: Học sinh cần giáo viên quan tâm */}
      <div className={styles.sectionCard}>
        <div className={styles.sectionCardHeader}>
          <div>
            <div className={styles.badgeCluster}>
              <h3 className={styles.sectionHeading}>
                Học sinh cần giáo viên đồng hành &amp; can thiệp
              </h3>
              <span className={attentionList.length > 0 ? styles.badgeAlertCount : styles.studentTotalPill}>
                {attentionList.length} em cần lưu ý
              </span>
            </div>
            <p className={styles.sectionSubheading}>
              AI phát hiện tự động dựa trên tần suất học, mức độ ngắt quãng hoặc chuỗi bài làm vấp lỗi
            </p>
          </div>
        </div>

        {attentionList.length === 0 ? (
          <div className={styles.alertEmptyCard}>
            <CheckCircle2 size={32} className={styles.textVerdant} aria-hidden="true" />
            <div>
              <h4 className={styles.emptyTitle}>Tiến độ học tập của lớp đang rất ổn định</h4>
              <p className={styles.emptyDesc}>
                Không có học sinh nào bị gián đoạn học tập quá hạn hoặc gặp báo động nghiêm trọng.
              </p>
            </div>
          </div>
        ) : (
          <div className={styles.attentionGrid}>
            {attentionList.map((st) => (
              <div key={st.student_id} className={styles.attentionCard}>
                <div className={styles.attentionCardHeader}>
                  <div className={styles.attentionStudentNameWrap}>
                    <div className={styles.attentionAvatar} aria-hidden="true">
                      {st.student_name[0] || "H"}
                    </div>
                    <div>
                      <strong className={styles.studentFullName}>{st.student_name}</strong>
                      <span className={styles.attentionSubText}>Tài khoản chính thức</span>
                    </div>
                  </div>
                  <span className={styles.severityBadgeHigh}>
                    <AlertTriangle size={12} aria-hidden="true" />
                    Cần chú ý
                  </span>
                </div>
                <div className={styles.attentionReasonBox}>
                  <strong>Lý do AI ghi nhận:</strong> {st.summary_reason}
                </div>
                <div className={styles.attentionCardActionHint}>
                  💡 Gợi ý: Giáo viên nên nhắn tin hoặc gọi nhắc nhở để giúp em không bị tụt lại so với lớp.
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* 2. Dạng bài yếu nhất của lớp (Điểm rơi kiến thức) */}
      <div className={styles.sectionCard}>
        <div className={styles.sectionCardHeader}>
          <div>
            <div className={styles.badgeCluster}>
              <h3 className={styles.sectionHeading}>
                Dạng bài học sinh hay làm sai &amp; hổng bước giải
              </h3>
              <span className={styles.badgeAmberCount}>
                {weakProblemTypes.length} dạng bài trọng tâm
              </span>
            </div>
            <p className={styles.sectionSubheading}>
              Phân tích từ toàn bộ bước giải trên giấy số của học sinh trong lớp để gợi ý trọng tâm tiết học tới
            </p>
          </div>
        </div>

        {weakProblemTypes.length === 0 ? (
          <div className={styles.emptyCard}>
            <CheckCircle2 size={32} className={styles.textVerdant} aria-hidden="true" />
            <h4 className={styles.emptyTitle}>Chưa phát hiện điểm hổng diện rộng</h4>
            <p className={styles.emptyDesc}>
              Lớp học chưa có dạng bài nào có tỷ lệ sai vượt ngưỡng báo động.
            </p>
          </div>
        ) : (
          <div className={styles.weakGrid}>
            {weakProblemTypes.map((pt) => (
              <div key={pt.id} className={styles.weakCard}>
                <div className={styles.weakCardTop}>
                  <span className={styles.weakCardBadge}>
                    <TrendingDown size={14} aria-hidden="true" />
                    Tỷ lệ đúng thấp
                  </span>
                  <span className={styles.weakStudentCount}>
                    {pt.student_count} học sinh vấp phải
                  </span>
                </div>

                <h4 className={styles.weakProblemTitle}>{pt.name}</h4>

                <div className={styles.weakScoreRow}>
                  <span>Điểm thành thạo trung bình:</span>
                  <strong className={styles.weakScoreValue}>{percent(pt.average_score)}</strong>
                </div>

                <div className={styles.weakPedagogicalTip}>
                  💡 Khuyến nghị giáo viên: Dành 10-15 phút đầu tiết tới trên lớp để chữa mẫu dạng bài này trên bảng.
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* 3. Tiến độ & Độ vững theo từng Chương trong SGK */}
      <div className={styles.sectionCard}>
        <div className={styles.sectionCardHeader}>
          <div>
            <h3 className={styles.sectionHeading}>
              Độ làm chủ kiến thức theo từng Chương SGK
            </h3>
            <p className={styles.sectionSubheading}>
              Thước đo chuẩn hóa mức độ làm chủ kiến thức của cả lớp theo chương trình chuẩn Bộ GD&amp;ĐT
            </p>
          </div>
        </div>

        {chapters.length === 0 ? (
          <div className={styles.emptyCard}>
            <BookOpen size={32} className={styles.emptyIcon} aria-hidden="true" />
            <h4 className={styles.emptyTitle}>Chưa có dữ liệu bài làm theo chương</h4>
            <p className={styles.emptyDesc}>
              Khi học sinh thực hiện các bài luyện tập trên giấy số, dữ liệu từng chương sẽ được tính toán tự động.
            </p>
          </div>
        ) : (
          <div className={styles.chaptersGridModern}>
            {chapters.map((ch) => {
              const masteryPct = Math.round(ch.average_mastery * 100);
              return (
                <div key={ch.chapter_id} className={styles.chapterCardModern}>
                  <div className={styles.chapterCardTop}>
                    <span className={styles.chapterSubjectPill}>Toán 12</span>
                    <span className={styles.chapterProficientText}>
                      <strong>{ch.total_student_count}</strong> học sinh trong lớp
                    </span>
                  </div>

                  <h4 className={styles.chapterCardTitle} title={ch.chapter_name}>
                    {ch.chapter_name}
                  </h4>

                  <div className={styles.chapterMasterySection}>
                    <div className={styles.chapterMasteryHeader}>
                      <span>Mức độ làm chủ trung bình</span>
                      <strong className={styles.chapterMasteryNum}>{masteryPct}%</strong>
                    </div>

                    <div className={styles.chapterProgressBarTrack}>
                      <div
                        className={styles.chapterProgressBarFill}
                        style={{ width: `${Math.max(4, masteryPct)}%` }}
                      />
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* 4. Tổng kết Bằng chứng & Tính xác thực dữ liệu */}
      <div className={styles.pedagogicalNoticeCard}>
        <HelpCircle size={20} className={styles.noticeIcon} aria-hidden="true" />
        <div>
          <h4 className={styles.noticeHeading}>Nguyên tắc sư phạm dữ liệu thực của EduMS</h4>
          <p className={styles.noticeText}>
            Hệ thống chỉ tính toán và hiển thị các chỉ số dựa trên bài giải thực tế của học sinh đã nộp. Không tự vẽ số liệu giả hoặc làm tròn tùy tiện để giáo viên luôn có góc nhìn trung thực nhất về lớp học của mình.
          </p>
        </div>
      </div>
    </div>
  );
}
