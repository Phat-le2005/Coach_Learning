"use client";

import { Activity, ArrowDown, ArrowRight, ClipboardList, GitBranch, RefreshCw, ScanLine, Target } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";

import { StudentTopNav } from "@/features/student-home/components/StudentTopNav";
import { GardenMotionProvider } from "@/features/student-home/components/nature/GardenMotionContext";
import { getPriorityReasonCopy } from "@/features/student-home/copy";
import type { StudentLearningStateRead } from "@/lib/api/contracts";
import type { StudentPriorityReasonCode } from "@/features/student-home/types";
import { masteryChange, type CoreGraph, type CoreMasteryRow } from "./model";
import styles from "./ai-core.module.css";

export interface AICoreViewProps {
  displayName: string; email: string; asOf: string; graph: CoreGraph | null;
  mastery: CoreMasteryRow[]; masteryAvailable: boolean; warnings: string[];
  attempts: { id: string; status: string; createdAt: string; steps: number | null; revision: number }[];
  attemptTotal: number | null; state: StudentLearningStateRead;
}

function percent(value: number | null): string { return value === null ? "Chưa đo" : `${Math.round(value * 100)}%`; }
function dateTime(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "Chưa rõ" : new Intl.DateTimeFormat("vi-VN", {
    dateStyle: "short", timeStyle: "medium", timeZone: "Asia/Ho_Chi_Minh",
  }).format(date);
}
const STATUS: Record<string, string> = { DRAFT: "Bản nháp", IN_PROGRESS: "Đang làm", SUBMITTED: "Đã nộp", EVALUATED: "Đã đánh giá", AUTO_EVALUATED: "Đã đánh giá tự động" };
const MASTERY: Record<string, string> = { NOT_STARTED: "Chưa có bằng chứng", LEARNING: "Đang học", WEAK: "Cần củng cố", PRACTICING: "Đang luyện", MASTERED: "Đã vững", REVIEW_DUE: "Đến hạn ôn" };

export function AICoreView(props: AICoreViewProps) {
  const router = useRouter();
  const [refreshing, startTransition] = useTransition();
  const [baseline, setBaseline] = useState<Record<string, number | null> | null>(null);
  const [baselineTime, setBaselineTime] = useState<string | null>(null);
  const measured = props.mastery.filter(row => row.score !== null);
  const stages = [
    { id: "core-attempts", title: "Attempt Tracker", subtitle: "Lượt làm & bước giải", icon: ClipboardList },
    { id: "core-graph", title: "Knowledge Graph", subtitle: "Ánh xạ & tiên quyết", icon: GitBranch },
    { id: "core-mastery", title: "Mastery V1", subtitle: "Năng lực & độ tin cậy", icon: Activity },
    { id: "core-recommendations", title: "Recommendation", subtitle: "Ưu tiên & lịch học", icon: Target },
  ];

  return <GardenMotionProvider><div className={styles.page}>
    <StudentTopNav displayName={props.displayName} email={props.email} currentRoute="/student/ai-core" />
    <main className={styles.main}>
      <header className={styles.hero}>
        <span className={styles.eyebrow}><ScanLine size={16} /> QUAN SÁT HỆ THỐNG HỌC TẬP</span>
        <h1>AI Core</h1>
        <p>Từ bài làm đến quyết định học tiếp: xem dữ liệu nào đang được ghi nhận, năng lực được cập nhật ra sao và vì sao hệ thống đề xuất một nội dung.</p>
        <div className={styles.actions}>
          <button disabled={refreshing} onClick={() => startTransition(() => router.refresh())}><RefreshCw size={16} />{refreshing ? "Đang tải…" : "Làm mới dữ liệu"}</button>
          <button disabled={!props.masteryAvailable} onClick={() => {
            setBaseline(Object.fromEntries(props.mastery.map(row => [row.id, row.score]))); setBaselineTime(props.asOf);
          }}>Ghi mốc so sánh</button>
          <Link href="/student/attempts" target="_blank" rel="noopener noreferrer">Mở bài làm để test <ArrowRight size={15} /></Link>
        </div>
        <p className={styles.timestamp}>Dữ liệu đọc lúc {dateTime(props.asOf)}{props.graph?.synthetic ? " · Hồ sơ mô phỏng" : ""}</p>
      </header>

      <nav className={styles.flow} aria-label="Luồng AI Core">
        {stages.map(({ id, title, subtitle, icon: Icon }, index) => <a href={`#${id}`} key={id}>
          <span className={styles.stageNumber}>0{index + 1}</span><Icon size={22} /><strong>{title}</strong><small>{subtitle}</small>
        </a>)}
      </nav>
      <div className={styles.metrics}>
        <div><span>Bài làm đang lưu</span><strong>{props.attemptTotal ?? "—"}</strong></div>
        <div><span>Khái niệm trong hồ sơ</span><strong>{props.graph?.concepts ?? "—"}</strong></div>
        <div><span>Mục năng lực có bằng chứng</span><strong>{props.masteryAvailable ? measured.length : "—"}</strong><small>khái niệm / dạng bài</small></div>
        <div><span>Mục tiêu ưu tiên</span><strong>{props.state.priority_targets.length}</strong></div>
      </div>
      {!!props.warnings.length && <div className={styles.warning} role="status">{props.warnings.map(warning => <p key={warning}>{warning}</p>)}</div>}
      <p className={styles.explainer}>Trang chỉ đọc trạng thái hiện có. Để quan sát thay đổi, bấm <b>Ghi mốc so sánh</b>, làm và nộp bài ở tab bên cạnh, rồi quay lại bấm <b>Làm mới dữ liệu</b>. Chat với gia sư không tự tạo lượt làm bài hay thay đổi mastery.</p>

      <div className={styles.grid}>
        <section id="core-attempts" className={styles.card}>
          <h2><ClipboardList size={21} /> 01 · Attempt Tracker</h2><p>Những bài làm gần đây trong MathWorkspace; trạng thái nộp bài được giữ riêng với kết quả đánh giá.</p>
          {props.attempts.length ? <ul className={styles.list}>{props.attempts.map(attempt => <li key={attempt.id}>
            <div><Link href={`/student/attempts/${encodeURIComponent(attempt.id)}`} target="_blank" rel="noopener noreferrer">Bài {attempt.id.slice(0, 8).toUpperCase()} ↗</Link><small>{dateTime(attempt.createdAt)}</small></div>
            <div><span className={styles.badge}>{STATUS[attempt.status] ?? attempt.status}</span><small>{attempt.steps === null ? "Chưa đọc số bước" : `${attempt.steps} bước`} · phiên bản {attempt.revision}</small></div>
          </li>)}</ul> : <p className={styles.empty}>{props.attemptTotal === null ? "Chưa đọc được danh sách bài làm." : "Chưa có bài làm được lưu."}</p>}
          <Link className={styles.more} href="/student/attempts">Xem tất cả bài làm →</Link>
        </section>

        <section id="core-graph" className={styles.card}>
          <h2><GitBranch size={21} /> 02 · Knowledge Graph</h2><p>Quan hệ từ hồ sơ kiến thức của chính học sinh; hệ thống dùng chúng để liên kết bài làm với kỹ năng và kiến thức tiên quyết.</p>
          {props.graph ? <>
            <div className={styles.graphStats}><span><b>{props.graph.prerequisites}</b> quan hệ tiên quyết</span><span><b>{props.graph.mappings}</b> ánh xạ dạng bài</span></div>
            {props.graph.relations.length ? <ul className={styles.relations}>{props.graph.relations.slice(0, 6).map((edge, index) => <li key={index}>
              <span>{edge.from}</span><div><small>{edge.kind}</small><ArrowRight size={20} /></div><span>{edge.to}</span>
            </li>)}</ul> : <p className={styles.empty}>Hồ sơ chưa có quan hệ kiến thức để hiển thị.</p>}
            {props.graph.relations.length > 6 && <small>Hiển thị 6 / {props.graph.relations.length} quan hệ trong hồ sơ.</small>}
          </> : <p className={styles.empty}>Chưa tải được đồ thị kiến thức.</p>}
          <Link className={styles.more} href="/student/knowledge">Mở Vũ trụ tri thức →</Link>
        </section>

        <section id="core-mastery" className={`${styles.card} ${styles.full}`}>
          <h2><Activity size={21} /> 03 · Mức độ nắm vững kiến thức</h2>
          <p><span className={styles.badge}>Đang dùng Mastery V1</span> Quy tắc cập nhật tất định dựa trên kết quả, độ khó, trọng số kỹ năng và số gợi ý. <b>Chưa triển khai mô hình BKT.</b></p>
          {baselineTime && <p className={styles.baseline} role="status">Đã ghi mốc {dateTime(baselineTime)}. Cột thay đổi sẽ so với mốc này khi làm mới trang.</p>}
          {props.masteryAvailable && props.mastery.length ? <div className={styles.tableWrap}><table><caption className={styles.caption}>Hiển thị {Math.min(props.mastery.length, 12)} / {props.mastery.length} mục, ưu tiên những mục đã có bằng chứng.</caption>
            <thead><tr><th>Khái niệm / dạng bài</th><th>Nắm vững</th><th>Độ tin cậy</th><th>Lượt</th><th>Trạng thái</th>{baseline && <th>Thay đổi</th>}</tr></thead>
            <tbody>{props.mastery.slice(0, 12).map(row => {
              const delta = baseline ? masteryChange(baseline[row.id], row.score) : null;
              return <tr key={`${row.kind}:${row.id}`}><td><b>{row.name}</b><small>{row.kind}</small></td><td>{percent(row.score)}</td><td>{percent(row.confidence)}</td><td>{row.attempts}</td><td>{MASTERY[row.state] ?? row.state}</td>{baseline && <td className={delta !== null && delta > 0 ? styles.positive : undefined}>{delta === null ? "—" : `${delta > 0 ? "+" : ""}${delta} điểm %`}</td>}</tr>;
            })}</tbody></table></div> : <p className={styles.empty}>Chưa có dữ liệu năng lực để hiển thị.</p>}
          <p className={styles.footnote}>“Chưa đo” là chưa có bằng chứng, không đồng nghĩa học sinh có năng lực 0%. Chỉ kết quả đủ điều kiện mới đi qua bước cập nhật mastery.</p>
        </section>

        <section id="core-recommendations" className={`${styles.card} ${styles.full}`}>
          <h2><Target size={21} /> 04 · Adaptive Recommendation Engine</h2><p>Thứ tự và mã lý do dưới đây do bộ đề xuất trả về. Trang quan sát không tự tính lại thứ tự hoặc sinh lời giải thích bằng AI.</p>
          {props.state.priority_targets.length ? <ol className={styles.priorities}>{props.state.priority_targets.slice(0, 8).map((target, index) => <li key={`${target.target_type}:${target.problem_type_id ?? target.concept_id}`}>
            <span className={styles.rank}>{index + 1}</span><div><strong>{target.target_name}</strong><p>{getPriorityReasonCopy(target.reason_code as StudentPriorityReasonCode)}</p><code>{target.reason_code}</code></div>
            <div><small>Điểm ưu tiên</small><strong>{Math.round(target.priority_score * 10) / 10}</strong><small>Độ khó mục tiêu {percent(target.desired_difficulty)}</small></div>
          </li>)}</ol> : <p className={styles.empty}>Hiện chưa có mục tiêu được bộ đề xuất trả về.</p>}
          <div className={styles.plan}><ArrowDown size={18} /><div><strong>Lịch học hôm nay</strong><p>{props.state.today_plan ? `${props.state.today_plan.total_count} nhiệm vụ · ${props.state.today_plan.total_estimated_minutes} / ${props.state.today_plan.available_daily_minutes} phút` : "Chưa có lịch học hôm nay. Tạo mục tiêu học tập trên trang tổng quan để bắt đầu."}</p></div><Link href="/student#learning-pulse">Xem lộ trình →</Link></div>
        </section>
      </div>
    </main>
  </div></GardenMotionProvider>;
}
