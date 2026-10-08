"use client";

import { ArrowRight, Map } from "lucide-react";
import { motion } from "motion/react";

import { GradientButton } from "@/components/ui/GradientButton";
import { StatusPill } from "@/components/ui/StatusPill";
import { fadeUp, staggerContainer } from "@/lib/motion";

import { getActionCopy } from "../copy";
import type { StudentHomeViewModel } from "../types";
import styles from "../StudentHome.module.css";
import { KnowledgeCanopy } from "./KnowledgeCanopy";

export interface FocusHeroProps {
  data: StudentHomeViewModel;
  showPreviewBadge: boolean;
}

export function FocusHero({ data, showPreviewBadge }: FocusHeroProps) {
  const copy = getActionCopy(data.currentAction.type);

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
          <StatusPill>{data.subject.name}</StatusPill>
          {showPreviewBadge ? <span className={styles.previewBadge}>UI Preview</span> : null}
        </div>
        <p className={styles.greeting}>Chào {data.student.displayName}</p>
        <h1 id="student-focus-title">{copy.title}</h1>
        <p className={styles.heroDescription}>{copy.description}</p>
        {data.currentAction.targetName ? (
          <p className={styles.focusTarget}>
            <span aria-hidden="true" />
            Trọng tâm: <strong>{data.currentAction.targetName}</strong>
          </p>
        ) : null}
        <div className={styles.heroActions}>
          <GradientButton href="#priority-path">
            {copy.primaryLabel}
            <ArrowRight size={18} aria-hidden="true" />
          </GradientButton>
          <GradientButton href="#knowledge-garden" variant="secondary">
            <Map size={17} aria-hidden="true" />
            Xem bản đồ tri thức
          </GradientButton>
        </div>
      </motion.div>

      <motion.div className={styles.heroVisual} variants={fadeUp}>
        <KnowledgeCanopy
          regions={data.knowledgeRegions}
          subjectName={data.subject.name}
          actionType={data.currentAction.type}
          targetName={data.currentAction.targetName}
        />
      </motion.div>
    </motion.section>
  );
}
