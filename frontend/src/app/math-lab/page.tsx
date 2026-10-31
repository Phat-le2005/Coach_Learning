"use client";
import dynamic from "next/dynamic";
import Link from "next/link";
import styles from "@/features/math-canvas/MathCanvas.module.css";
const MathLab = dynamic(() => import("@/features/math-canvas/MathLab").then((module) => module.MathLab), { ssr: false, loading: () => <p>Đang mở phòng khám phá toán học…</p> });
export default function MathLabPage() {
  return <main className={styles.labPage}><nav className={styles.labPageNav}><Link href="/student">← Không gian học tập</Link><span>EduMS / Math Lab</span></nav><MathLab/></main>;
}
