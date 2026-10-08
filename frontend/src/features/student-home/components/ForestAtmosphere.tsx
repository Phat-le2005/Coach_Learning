import styles from "./nature/ForestAtmosphere.module.css";
import { CloudLayer } from "./nature/CloudLayer";
import { FloatingParticles } from "./nature/FloatingParticles";

export function ForestAtmosphere() {
  return (
    <div className={styles.atmosphere} aria-hidden="true">
      <span className={styles.sun} />
      <CloudLayer depth="far" count={3} />
      <CloudLayer depth="near" count={2} />
      <span className={styles.mistPrimary} />
      <span className={styles.mistSecondary} />
      <div className={styles.hills}>
        <span /><span /><span />
      </div>
      <FloatingParticles />
    </div>
  );
}
