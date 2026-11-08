"use client";

import Link from "next/link";
import { getPriorityReasonCopy } from "../copy";
import type { PriorityViewModel, StudentHomeViewModel } from "../types";
import ui from "../HomeContent.module.css";
import { HomeIcon } from "./HomeIcon";

export function PriorityPath({ priorities, onSelectPriority, subjectId, mastery, momentum }: {
  priorities: PriorityViewModel[];
  onSelectPriority?: (priority: PriorityViewModel) => void;
  subjectId?: string;
  mastery?: StudentHomeViewModel["mastery"];
  momentum?: StudentHomeViewModel["momentum"];
}) {
  const knowledgeHref = `/student/knowledge${subjectId ? `?subject_id=${encodeURIComponent(subjectId)}` : ""}`;
  const hasScore = Boolean(mastery?.hasEvidence && mastery.score !== undefined && Number.isFinite(mastery.score));
  const score = hasScore ? Math.min(100, Math.max(0, mastery!.score!)) : undefined;

  return <section className={ui.progressSection} id="priority-path" aria-labelledby="home-progress-title">
    <div className={ui.sectionHeading}><h2 id="home-progress-title">Năng lực & trọng tâm học</h2><Link className={ui.textAction} href={knowledgeHref}>Mở Vũ trụ tri thức<HomeIcon name="arrow-up-right" size={17} /></Link></div>
    <div className={ui.progressLayout}>
      <section className={ui.masteryPanel} aria-labelledby="home-mastery-title">
        <div className={ui.planTitle}><HomeIcon name="graph" size={25} /><h3 id="home-mastery-title">Mức độ nắm vững</h3></div>
        {mastery?.hasEvidence ? <>
          <p className={ui.masteryLabel}>{mastery.label}</p>
          {score !== undefined ? <><p className={ui.masteryScore}>{Math.round(score)}<span>%</span></p><progress className={ui.progressBar} max={100} value={score} aria-label={`Mức độ nắm vững ${Math.round(score)} phần trăm`} /></> : <p className={ui.emptyText}>Chưa có điểm tổng hợp.</p>}
          <dl className={ui.masteryFacts}><div><dt>Dạng đã vững</dt><dd>{mastery.masteredProblemTypeCount}</dd></div><div><dt>Cần củng cố</dt><dd>{mastery.weakProblemTypeCount}</dd></div></dl>
          <p className={ui.masteryDetail}>Đã học {mastery.problemTypeStartedCount} dạng và {mastery.conceptStartedCount} khái niệm.</p>
        </> : <><p className={ui.masteryEmptyTitle}>Chưa đủ dữ liệu đánh giá.</p><p className={ui.planDescription}>Sau những bài làm, bạn sẽ thấy mức độ nắm vững và những phần nên luyện thêm tại đây.</p></>}
        {momentum?.activeDays !== undefined && <p className={ui.momentum}>{momentum.activeDays} ngày học liên tục</p>}
      </section>

      <section className={ui.prioritiesPanel} aria-labelledby="home-priorities-title">
        <div className={ui.blockHeading}><h3 id="home-priorities-title">Lộ trình khắc phục & luyện tập ưu tiên</h3>{priorities.length > 0 && <span>{priorities.length} nội dung</span>}</div>
        <p className={ui.priorityIntro}>Những phần nên luyện tiếp từ dữ liệu học tập của bạn, theo thứ tự được đề xuất.</p>
        {priorities.length > 0 ? <ol className={`${ui.workList} ${ui.priorityList}`}>{priorities.map((priority, index) => <li className={ui.priorityRow} key={priority.id}>
          <span className={ui.priorityRank} aria-label={`Ưu tiên ${index + 1}`}>{index + 1}</span>
          <div className={ui.rowCopy}><h4>{priority.targetName}</h4><p className={ui.rowMeta}>{getPriorityReasonCopy(priority.reasonCode)}{priority.mastery !== undefined ? ` · Mức độ nắm vững ${Math.round(priority.mastery)}%` : ""}</p></div>
          <div className={ui.priorityActions}><Link className={ui.textAction} href={priority.practiceRoute || `/student/practice${subjectId ? `?subject_id=${encodeURIComponent(subjectId)}` : ""}`} prefetch={false}>Luyện tập<HomeIcon name="arrow-up-right" size={16} /></Link><Link className={ui.subtleAction} href={`/student/theory?topic=${encodeURIComponent(priority.targetName)}`}>Lý thuyết</Link>{onSelectPriority && <button type="button" className={ui.subtleAction} onClick={() => onSelectPriority(priority)}>Chi tiết</button>}</div>
        </li>)}</ol> : <div className={ui.priorityEmpty}><HomeIcon name="book-open" size={32} /><p>Chưa có đề xuất củng cố.</p><span>Những phần cần ưu tiên sẽ xuất hiện khi có dữ liệu học tập phù hợp.</span></div>}
      </section>
    </div>
  </section>;
}
