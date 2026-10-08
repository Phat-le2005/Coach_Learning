import styles from "./ForestAtmosphere.module.css";

export interface CloudLayerProps {
  depth: "far" | "near";
  count: number;
}

export function CloudLayer({ depth, count }: CloudLayerProps) {
  return (
    <div className={`${styles.cloudLayer} ${styles[`cloudLayer_${depth}`]}`}>
      {Array.from({ length: count }, (_, index) => <span className={styles.cloud} key={`${depth}-${index}`} />)}
    </div>
  );
}
