"use client";

import { ArrowRight, Compass, Leaf, Orbit, PenTool } from "lucide-react";
import { motion } from "motion/react";
import { useRouter } from "next/navigation";
import type { ChangeEvent } from "react";

import { GradientButton } from "@/components/ui/GradientButton";
import { StatusPill } from "@/components/ui/StatusPill";
import { fadeUp, staggerContainer } from "@/lib/motion";

import styles from "../StudentHome.module.css";
import type { StudentHomeViewModel } from "../types";
import { KnowledgeCanopy } from "./KnowledgeCanopy";
import { HeroNatureScene } from "./nature/HeroNatureScene";

export interface FocusHeroProps {
  data: StudentHomeViewModel;
  onOpenActionDetail: () => void;
}

export function FocusHero({ data, onOpenActionDetail }: FocusHeroProps) {
  const router = useRouter();
  const action = data.resolvedAction;
  const isSelfStudyOnboarding = data.learningContext.mode === "SELF_STUDY_ONBOARDING";
  const knowledgeHref = `/student/knowledge${
    data.subject.id ? `?subject_id=${encodeURIComponent(data.subject.id)}` : ""
  }`;

  const topPriority = data.priorities[0];
  const isGenericAction =
    !action.targetName &&
    (action.type === "CONTINUE_PRACTICE" || action.type === "IDLE" || action.type === "LEARNING_PRIORITY");

  const displayTitle = isSelfStudyOnboarding
    ? `Mở lối vào ${data.subject.name}`
    : isGenericAction && topPriority
      ? `Khắc phục: ${topPriority.targetName}`
      : action.title;

  const displayDescription = isSelfStudyOnboarding
    ? "Khám phá các chòm sao, chủ đề và từng dạng bài theo nhịp của bạn. Mọi tiến độ sẽ được đo lường chính xác khi có hoạt động học thật."
    : isGenericAction && topPriority
      ? "AI đã phân tích bài giải gần đây của bạn và phát hiện bước biến đổi cần củng cố. Hãy dành ~5 phút làm 2-3 câu ngắn để lấy lại 100% độ chuẩn xác!"
      : action.description;

  const displayTargetName = action.targetName || (topPriority ? topPriority.targetName : undefined);

  const primaryPracticeHref =
    action.hasAvailableRoute && action.route
      ? action.route
      : topPriority?.practiceRoute
        ? topPriority.practiceRoute
        : data.subject.id
          ? `/student/practice?subject_id=${encodeURIComponent(data.subject.id)}`
          : "/student/practice";

  const primaryPracticeLabel =
    action.hasAvailableRoute && action.primaryLabel
      ? action.primaryLabel
      : topPriority
        ? `Luyện ngay dạng bài này (~5p)`
        : "Bắt đầu luyện tập ngay";

  const handleSubjectChange = (event: ChangeEvent<HTMLSelectElement>) => {
    const selectedSubjectId = event.target.value;
    if (selectedSubjectId && selectedSubjectId !== data.subject.id) {
      router.push(`/student?subject_id=${encodeURIComponent(selectedSubjectId)}`);
    }
  };

  return (
    <motion.section
      className={styles.hero}
      aria-labelledby="student-focus-title"
      variants={staggerContainer}
      initial="hidden"
      animate="visible"
    >
      {/* Living Nature Panorama: Clouds, Falling Leaves, Mountains, Swaying Canopy, Sunbeams */}
      <HeroNatureScene />

      <motion.div className={styles.heroCopy} variants={fadeUp}>
        <div className={styles.heroMeta}>
          {data.availableSubjects.length > 1 ? (
            <div className={styles.subjectSelectorWrap}>
              <select
                id="student-subject-select"
                className={styles.subjectSelect}
                value={data.subject.id}
                onChange={handleSubjectChange}
                aria-label="Chọn môn học"
              >
                {data.availableSubjects.map((sub) => (
                  <option key={sub.id} value={sub.id}>
                    {sub.name}
                  </option>
                ))}
              </select>
            </div>
          ) : (
            <StatusPill>
              {isSelfStudyOnboarding ? `Tự học · ${data.subject.name}` : data.subject.name}
            </StatusPill>
          )}
          <span className={styles.heroGardenTag}>
            <Leaf size={12} aria-hidden="true" />
            Living Learning Garden
          </span>
        </div>

        <p className={styles.greeting}>Chào {data.student.displayName}</p>
        <h1 id="student-focus-title">{displayTitle}</h1>
        <p className={styles.heroDescription}>{displayDescription}</p>

        {!isSelfStudyOnboarding && displayTargetName ? (
          <div className={styles.focusTargetBadgeRow}>
            <p className={styles.focusTarget}>
              <span aria-hidden="true" />
              Trọng tâm: <strong>{displayTargetName}</strong>
            </p>
            <span className={styles.focusTimeEstimatePill}>⚡ 2 - 3 câu · ~5 phút</span>
          </div>
        ) : null}

        <div className={styles.heroActions}>
          {isSelfStudyOnboarding ? (
            <GradientButton href={knowledgeHref}>
              Bắt đầu tự học
              <ArrowRight size={18} aria-hidden="true" />
            </GradientButton>
          ) : (
            <GradientButton href={primaryPracticeHref}>
              {primaryPracticeLabel}
              <ArrowRight size={18} aria-hidden="true" />
            </GradientButton>
          )}

          {!isSelfStudyOnboarding ? (
            <GradientButton href={knowledgeHref} variant="secondary">
              <Orbit size={17} aria-hidden="true" />
              Vũ trụ tri thức
            </GradientButton>
          ) : null}

          {!isSelfStudyOnboarding ? (
            <button
              type="button"
              onClick={onOpenActionDetail}
              className={styles.heroDetailTrigger}
            >
              <Compass size={15} aria-hidden="true" />
              Chi tiết bước học
            </button>
          ) : null}
        </div>
      </motion.div>

      <motion.div className={styles.heroVisual} variants={fadeUp}>
        <KnowledgeCanopy
          regions={data.knowledgeRegions}
          subjectName={data.subject.name}
          ghost={data.knowledgeRegions.length === 0}
          actionType={data.currentAction.type}
          targetName={data.currentAction.targetName}
        />
      </motion.div>
    </motion.section>
  );
}
