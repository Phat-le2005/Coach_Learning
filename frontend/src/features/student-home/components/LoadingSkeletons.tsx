import styles from "../StudentHome.module.css";

function SkeletonLine({ short = false }: { short?: boolean }) {
  return <span className={short ? styles.skeletonLineShort : styles.skeletonLine} />;
}

export function HeroSkeleton() {
  return (
    <div className={styles.heroSkeleton} aria-hidden="true">
      <div><SkeletonLine short /><SkeletonLine /><SkeletonLine /></div>
      <span className={styles.skeletonOrb} />
    </div>
  );
}

export function MetricSkeleton() {
  return (
    <div className={styles.metricSkeleton} aria-hidden="true">
      <span className={styles.skeletonIcon} />
      <div><SkeletonLine short /><SkeletonLine /></div>
    </div>
  );
}

export function GardenSkeleton() {
  return (
    <div className={styles.gardenSkeleton} aria-hidden="true">
      <span className={styles.skeletonLandscape} />
      <SkeletonLine />
      <SkeletonLine short />
    </div>
  );
}
