import type { Metadata } from "next";
import { Compass, GitBranch, Lock, ShieldCheck, Sparkles } from "lucide-react";

import { KnowledgeTreeIllustration } from "@/components/auth/KnowledgeTreeIllustration";
import { LoginForm } from "@/components/auth/LoginForm";
import { BrandMark } from "@/features/student-home/components/BrandMark";
import { redirectAuthenticatedUser } from "@/lib/auth/page-session";
import { safeReturnPath } from "@/lib/auth/rbac";

import styles from "./login.module.css";

export const metadata: Metadata = {
  title: "Đăng nhập · EduMS",
  description: "Đăng nhập an toàn vào EduMS · Khu Rừng Tri Thức.",
};

interface LoginPageProps {
  searchParams: Promise<{ returnTo?: string; reason?: string }>;
}

export default async function LoginPage({ searchParams }: LoginPageProps) {
  await redirectAuthenticatedUser();
  const query = await searchParams;

  return (
    <main className={styles.page}>
      {/* Sky Atmosphere with warm sun glow & ambient mist */}
      <div className={styles.skyAtmosphere} aria-hidden="true">
        <span className={styles.skySun} />
        <span className={styles.ambientMistFar} />
        <span className={styles.ambientMistNear} />
      </div>

      <section className={styles.stage} aria-labelledby="login-title">
        {/* Left Column: Khu Rừng Tri Thức */}
        <div className={styles.story}>
          {/* Nature Atmosphere Effects */}
          <div className={styles.storyClouds} aria-hidden="true">
            <span className={`${styles.storyCloud} ${styles.storyCloud1}`} />
            <span className={`${styles.storyCloud} ${styles.storyCloud2}`} />
          </div>
          <div className={styles.storyParticles} aria-hidden="true">
            <span className={`${styles.storyParticle} ${styles.storyParticle1}`} />
            <span className={`${styles.storyParticle} ${styles.storyParticle2}`} />
            <span className={`${styles.storyParticle} ${styles.storyParticle3}`} />
            <span className={`${styles.storyParticle} ${styles.storyParticle4}`} />
            <span className={`${styles.storyParticle} ${styles.storyParticle5}`} />
          </div>

          <div className={styles.storyContent}>
            <BrandMark />

            <div className={styles.storyBadge}>
              <Sparkles size={13} aria-hidden="true" />
              <span>Khu Rừng Tri Thức · EduMS</span>
            </div>

            <h1 id="login-title" className={styles.storyTitle}>
              Nơi tri thức đâm chồi, từng bước tiến vững chắc.
            </h1>

            <p className={styles.storyDesc}>
              Mỗi bài học là một hạt mầm. EduMS phân tích lỗ hổng gốc rễ, đồng hành và cá nhân hóa hành trình học tập dựa trên dữ liệu thực tế.
            </p>

            <div className={styles.featureList} aria-label="Đặc điểm học tập tại EduMS">
              <div className={styles.featureChip}>
                <span className={styles.featureIcon} aria-hidden="true">
                  <Compass size={16} />
                </span>
                <span>Dữ liệu thực nghiệm</span>
              </div>
              <div className={styles.featureChip}>
                <span className={styles.featureIcon} aria-hidden="true">
                  <GitBranch size={16} />
                </span>
                <span>Phục hồi gốc rễ</span>
              </div>
              <div className={styles.featureChip}>
                <span className={styles.featureIcon} aria-hidden="true">
                  <ShieldCheck size={16} />
                </span>
                <span>Lộ trình thích ứng</span>
              </div>
            </div>
          </div>

          {/* Majestic Grand Knowledge Tree SVG */}
          <div className={styles.treeStage}>
            <KnowledgeTreeIllustration />
          </div>
        </div>

        {/* Right Column: Form Đăng Nhập Hiện Đại */}
        <div className={styles.card}>
          <div className={styles.cardHeader}>
            <div className={styles.cardBadge}>
              <Lock size={12} aria-hidden="true" />
              <span>Cổng truy cập an toàn</span>
            </div>
            <h2 className={styles.cardTitle}>Đăng nhập</h2>
            <p className={styles.cardSubtitle}>
              Sử dụng tài khoản được cấp để tiếp tục hành trình học tập.
            </p>
          </div>

          <LoginForm
            returnTo={safeReturnPath(query.returnTo ?? null) ?? undefined}
            expired={query.reason === "expired"}
          />
        </div>
      </section>
    </main>
  );
}
