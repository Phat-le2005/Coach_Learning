import type { CSSProperties } from "react";
import styles from "./nature/ForestAtmosphere.module.css";

type ParticleProps = {
  top: string;
  left: string;
  size: number;
  delay: string;
  duration: string;
  variant: string;
};

const PARTICLES: ParticleProps[] = [
  { top: "8%", left: "12%", size: 3.5, delay: "-2s", duration: "15s", variant: styles.particleMint },
  { top: "16%", left: "74%", size: 4, delay: "-5s", duration: "18s", variant: styles.particleGold },
  { top: "28%", left: "34%", size: 3, delay: "-1s", duration: "16s", variant: styles.particleSky },
  { top: "38%", left: "86%", size: 3.5, delay: "-7s", duration: "20s", variant: styles.particleViolet },
  { top: "48%", left: "18%", size: 4, delay: "-3s", duration: "17s", variant: styles.particleMint },
  { top: "58%", left: "62%", size: 3, delay: "-8s", duration: "19s", variant: styles.particleGold },
  { top: "68%", left: "26%", size: 4.5, delay: "-4s", duration: "16s", variant: styles.particleSky },
  { top: "78%", left: "80%", size: 3.5, delay: "-6s", duration: "22s", variant: styles.particleMint },
  { top: "86%", left: "45%", size: 3, delay: "-2s", duration: "15s", variant: styles.particleGold },
  { top: "22%", left: "52%", size: 2.5, delay: "-9s", duration: "21s", variant: styles.particleViolet },
  { top: "62%", left: "92%", size: 3.5, delay: "-3.5s", duration: "17.5s", variant: styles.particleSky },
  { top: "92%", left: "15%", size: 3, delay: "-1.5s", duration: "18.5s", variant: styles.particleMint },
];

export function ForestAtmosphere() {
  return (
    <div className={styles.atmosphere} aria-hidden="true">
      {/* Flowing Celestial Aurora Waves */}
      <span className={styles.auroraWaveOne} />
      <span className={styles.auroraWaveTwo} />

      {/* Floating Stardust Particles & Twinkling Celestial Fireflies */}
      <div className={styles.cosmicDust}>
        {PARTICLES.map((p, idx) => {
          const style: CSSProperties & { [key: string]: string } = {
            top: p.top,
            left: p.left,
            width: `${p.size}px`,
            height: `${p.size}px`,
            "--particle-delay": p.delay,
            "--particle-duration": p.duration,
          };
          return (
            <span
              key={idx}
              className={`${styles.cosmicParticle} ${p.variant}`}
              style={style}
            />
          );
        })}
      </div>
    </div>
  );
}
