"use client";

import { ArrowRight, Route } from "lucide-react";
import { motion } from "motion/react";
import { useRouter } from "next/navigation";
import type { ChangeEvent } from "react";

import { GradientButton } from "@/components/ui/GradientButton";
import { StatusPill } from "@/components/ui/StatusPill";
import { fadeUp, staggerContainer } from "@/lib/motion";

import type { StudentHomeViewModel } from "../types";
import styles from "../StudentHome.module.css";
import { KnowledgeCanopy } from "./KnowledgeCanopy";

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
      <div className={styles.heroDecor} aria-hidden="true">
        <span className={styles.heroAurora} />
        <span className={styles.heroMist} />
        <span className={styles.heroHorizon} />
        <span className={styles.heroCloud} />
        <span className={styles.heroLeafOne} />
        <span className={styles.heroLeafTwo} />
        <span className={styles.heroSpark}>✦</span>
        <span className={styles.heroFireflyOne} />
        <span className={styles.heroFireflyTwo} />
      </div>

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
        </div>
        <p className={styles.greeting}>Chào {data.student.displayName}</p>
        <h1 id="student-focus-title">
          {isSelfStudyOnboarding ? `Mở lối vào ${data.subject.name}` : action.title}
        </h1>
        <p className={styles.heroDescription}>
          {isSelfStudyOnboarding
            ? "Chọn một chương và khám phá từng dạng bài theo nhịp của bạn. Mọi tiến độ chỉ bắt đầu khi có hoạt động học thật."
            : action.description}
        </p>
        {!isSelfStudyOnboarding && action.targetName ? (
          <p className={styles.focusTarget}>
            <span aria-hidden="true" />
            Trọng tâm: <strong>{action.targetName}</strong>
          </p>
        ) : null}
        <div className={styles.heroActions}>
          {isSelfStudyOnboarding ? (
            <GradientButton href={knowledgeHref}>
              Bắt đầu tự học
              <ArrowRight size={18} aria-hidden="true" />
            </GradientButton>
          ) : action.hasAvailableRoute && action.route ? (
            <GradientButton href={action.route}>
              {action.primaryLabel}
              <ArrowRight size={18} aria-hidden="true" />
            </GradientButton>
          ) : (
            <GradientButton onClick={onOpenActionDetail}>
              {action.primaryLabel}
              <ArrowRight size={18} aria-hidden="true" />
            </GradientButton>
          )}
          {!isSelfStudyOnboarding ? (
            <GradientButton href={knowledgeHref} variant="secondary">
              <Route size={17} aria-hidden="true" />
              Bản đồ tri thức
            </GradientButton>
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
