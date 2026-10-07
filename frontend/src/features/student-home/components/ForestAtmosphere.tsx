import type { CSSProperties } from "react";

import styles from "../StudentHome.module.css";

type PollenStyle = CSSProperties & {
  "--pollen-x": string;
  "--pollen-y": string;
  "--pollen-delay": string;
  "--pollen-duration": string;
};

const pollen = [
  ["8%", "23%", "-3s", "18s"],
  ["19%", "61%", "-11s", "23s"],
  ["34%", "34%", "-7s", "20s"],
  ["49%", "76%", "-14s", "26s"],
  ["63%", "19%", "-5s", "21s"],
  ["74%", "55%", "-16s", "24s"],
  ["86%", "31%", "-9s", "19s"],
  ["93%", "72%", "-2s", "22s"],
] as const;

export function ForestAtmosphere() {
  return (
    <div className={styles.forestAtmosphere} aria-hidden="true">
      <span className={styles.forestSun} />
      <div className={`${styles.cloudLayer} ${styles.cloudLayerFar}`}>
        <span /><span /><span />
      </div>
      <div className={`${styles.cloudLayer} ${styles.cloudLayerNear}`}>
        <span /><span />
      </div>
      <span className={styles.mistRibbonOne} />
      <span className={styles.mistRibbonTwo} />
      <div className={styles.distantHills}>
        <span /><span /><span />
      </div>
      <div className={styles.pollenField}>
        {pollen.map(([x, y, delay, duration], index) => {
          const style: PollenStyle = {
            "--pollen-x": x,
            "--pollen-y": y,
            "--pollen-delay": delay,
            "--pollen-duration": duration,
          };
          return <i style={style} key={`${x}-${y}-${index}`} />;
        })}
      </div>
    </div>
  );
}
