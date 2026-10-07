"use client";

import { ArrowUpRight } from "lucide-react";
import { motion } from "motion/react";
import type { CSSProperties } from "react";

import { MasteryBadge } from "@/components/ui/MasteryBadge";
import { OrganicCard } from "@/components/ui/OrganicCard";
import { fadeUp, staggerContainer } from "@/lib/motion";

import { getRegionStateCopy } from "../copy";
import type { KnowledgeRegionViewModel } from "../types";
import styles from "../StudentHome.module.css";
import { SectionHeading } from "./SectionHeading";

export interface KnowledgeGardenProps {
  regions: KnowledgeRegionViewModel[];
}

type GardenStyle = CSSProperties & {
  "--garden-progress": string;
};

export function KnowledgeGarden({ regions }: KnowledgeGardenProps) {
  return (
    <section className={styles.section} id="knowledge-garden" aria-labelledby="knowledge-garden-title">
      <SectionHeading
        eyebrow="Bản đồ phát triển"
        title="Khu vườn tri thức"
        description="Mỗi vùng phát triển theo cách bạn học."
        action={<span className={styles.dragHint}>Cuộn để khám phá <ArrowUpRight size={15} /></span>}
      />
      <motion.div
        className={styles.gardenGrid}
        variants={staggerContainer}
        initial={false}
        whileInView="visible"
        viewport={{ once: true, amount: 0.15 }}
      >
        {regions.map((region, index) => {
          const style: GardenStyle = { "--garden-progress": `${region.progress ?? 0}%` };
          return (
            <motion.div variants={fadeUp} key={region.id} className={styles.gardenCardWrap}>
              <OrganicCard
                className={`${styles.gardenCard} ${styles[`garden_${region.state}`]} ${styles[`gardenAccent_${region.accent}`]}`}
                interactive
              >
                <div className={styles.gardenIndex}>0{index + 1}</div>
                <div className={styles.gardenLandscape} aria-hidden="true">
                  <span className={styles.gardenSun} />
                  <span className={styles.gardenHillBack} />
                  <span className={styles.gardenHillFront} />
                  <span className={styles.gardenStemOne} />
                  <span className={styles.gardenStemTwo} />
                </div>
                <div className={styles.gardenContent}>
                  <MasteryBadge state={region.state === "not_started" ? "not_measured" : region.state} label={getRegionStateCopy(region.state)} />
                  <h3>{region.label}</h3>
                  <div className={styles.gardenProgress} style={style}>
                    <span aria-hidden="true"><i /></span>
                    <strong>{region.progress === undefined ? "—" : `${region.progress}%`}</strong>
                  </div>
                </div>
              </OrganicCard>
            </motion.div>
          );
        })}
      </motion.div>
    </section>
  );
}
