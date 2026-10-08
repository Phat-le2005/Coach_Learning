import type { CSSProperties } from "react";

import styles from "./ForestAtmosphere.module.css";

type ParticleStyle = CSSProperties & {
  "--particle-x": string;
  "--particle-y": string;
  "--particle-delay": string;
  "--particle-duration": string;
};

const particles = [
  ["9%", "24%", "-3s", "14s"],
  ["31%", "59%", "-8s", "17s"],
  ["61%", "20%", "-5s", "15s"],
  ["84%", "48%", "-11s", "18s"],
  ["48%", "78%", "0s", "16s"],
  ["93%", "70%", "0s", "18s"],
] as const;

export function FloatingParticles() {
  return (
    <div className={styles.particles}>
      {particles.map(([x, y, delay, duration], index) => {
        const style: ParticleStyle = {
          "--particle-x": x,
          "--particle-y": y,
          "--particle-delay": delay,
          "--particle-duration": duration,
        };
        return <i className={index < 3 ? styles.particleMoving : styles.particleStatic} style={style} key={`${x}-${y}`} />;
      })}
    </div>
  );
}
