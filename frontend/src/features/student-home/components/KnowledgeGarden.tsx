"use client";

import { ArrowUpRight } from "lucide-react";
import { motion } from "motion/react";
import Link from "next/link";
import type { CSSProperties } from "react";

import { MasteryBadge } from "@/components/ui/MasteryBadge";
import { OrganicCard } from "@/components/ui/OrganicCard";
import { fadeUp, staggerContainer } from "@/lib/motion";

import { getRegionStateCopy } from "../copy";
import type { KnowledgeBiome, KnowledgeRegionViewModel } from "../types";
import styles from "../StudentHome.module.css";
import { SectionHeading } from "./SectionHeading";

export interface KnowledgeGardenProps {
  regions: KnowledgeRegionViewModel[];
  subjectId?: string;
}

type GardenStyle = CSSProperties & {
  "--garden-progress": string;
};

const fallbackBiomes: KnowledgeBiome[] = ["meadow", "river", "mountain", "forest", "sky"];

export function KnowledgeGarden({ regions, subjectId }: KnowledgeGardenProps) {
  const knowledgeHref = subjectId
    ? `/student/knowledge?subject_id=${encodeURIComponent(subjectId)}`
    : "/student/knowledge";

  return (
    <section className={styles.section} id="knowledge-garden" aria-labelledby="knowledge-garden-title">
      <SectionHeading
        eyebrow="Bản đồ phát triển"
        title="Khu vườn tri thức"
        description="Mỗi vùng phát triển theo cách bạn học."
        action={
          <Link href={knowledgeHref} className={styles.gardenExploreLink}>
            Mở Bản đồ tri thức <ArrowUpRight size={15} />
          </Link>
        }
      />
      {regions.length === 0 ? (
        <OrganicCard className={styles.realDataEmpty} variant="glass">
          <h3>Chưa có dữ liệu chương và chủ đề</h3>
          <p>Learning State hiện chưa trả về cấu trúc chapter/topic. EduMS sẽ không dựng khu vực giả để lấp khoảng trống này.</p>
        </OrganicCard>
      ) : null}
      {regions.length > 0 ? <div className={styles.gardenScrollFrame}>
        <motion.div
          className={styles.gardenGrid}
          variants={staggerContainer}
          initial={false}
          whileInView="visible"
          viewport={{ once: true, amount: 0.15 }}
        >
          {regions.map((region, index) => {
            const style: GardenStyle = { "--garden-progress": `${region.progress ?? 0}%` };
            const biome = region.biome ?? fallbackBiomes[index % fallbackBiomes.length];
            return (
              <motion.div variants={fadeUp} key={region.id} className={styles.gardenCardWrap}>
                <OrganicCard
                  className={`${styles.gardenCard} ${styles[`garden_${region.state}`]} ${styles[`gardenAccent_${region.accent}`]} ${styles[`gardenBiome_${biome}`]}`}
                  data-biome={biome}
                  interactive
                >
                <div className={styles.gardenIndex}>0{index + 1}</div>
                <div className={styles.gardenLandscape} aria-hidden="true">
                  <span className={styles.gardenCloud} />
                  <span className={styles.gardenSun} />
                  <span className={styles.gardenRidge} />
                  <span className={styles.gardenHillBack} />
                  <span className={styles.gardenHillFront} />
                  <span className={styles.gardenRiver} />
                  <span className={styles.gardenPath} />
                  <span className={styles.gardenStemOne} />
                  <span className={styles.gardenStemTwo} />
                  <span className={styles.gardenTree} />
                  <span className={styles.gardenLight} />
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
      </div> : null}
    </section>
  );
}
