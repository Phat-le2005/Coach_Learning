"use client";

import Link from "next/link";
import { useState } from "react";
import { getHomeRoutes, homeDate, homeTaskHref, homeTaskTypeLabel } from "../home-presentation";
import type { StudentHomeViewModel } from "../types";
import ui from "../HomeContent.module.css";
import { HomeIcon } from "./HomeIcon";

export function HomeToday({ data, onOpenPlan, onDetails, onRecalculate, recalculating, feedback }: {
  data: StudentHomeViewModel;
  onOpenPlan: () => void;
  onDetails: () => void;
  onRecalculate: () => void;
  recalculating: boolean;
  feedback?: string | null;
}) {
  const [expanded, setExpanded] = useState(false);
  const routes = getHomeRoutes(data);
  const action = data.resolvedAction;
  const plan = data.todayPlan;
  const tasks = plan?.tasks ?? [];
  const shownTasks = expanded ? tasks : tasks.slice(0, 3);
  const hasAction = action.type !== "IDLE";
  const hasClassroom = data.learningContext.mode === "CLASSROOM";
  const reviewHref = action.type === "REVIEW_DUE" && routes.recommended ? routes.recommended : routes.knowledge;

  return <div className={ui.content} id="learning-pulse">
    <section className={ui.learningSection} aria-labelledby="home-next-title">
      <div className={ui.sectionHeading}><h2 id="home-next-title">Việc nên làm tiếp theo</h2></div>
      <div className={ui.nextAction}>
        <span className={ui.nextIcon}><HomeIcon name={action.type === "REVIEW_DUE" ? "book-open" : "pen-nib"} size={28} /></span>
        <div className={ui.nextCopy}>
          <h3>{hasAction ? action.title : "Bắt đầu bằng một bài làm"}</h3>
          <p>{hasAction ? action.description : "Chọn một bài để viết lời giải. EduMS sẽ có thêm dữ liệu để gợi ý phần nên học tiếp."}</p>
          <div className={ui.actionRow}>
            <Link className={ui.mainAction} href={routes.recommended ?? (hasAction ? routes.knowledge : routes.practice)} prefetch={false}>
              {routes.recommended ? action.primaryLabel : hasAction ? "Khám phá kiến thức" : "Chọn bài để làm"}<HomeIcon name="arrow-right" size={18} />
            </Link>
            {hasAction && <button type="button" className={ui.textAction} onClick={onDetails}>Chi tiết bước học</button>}
          </div>
        </div>
      </div>
    </section>

    <section className={`${ui.learningSection} ${ui.scheduleSection}`} aria-labelledby="home-schedule-title">
      <div className={ui.sectionHeading}><h2 id="home-schedule-title">Lịch học & việc cần làm</h2><span>Một nơi cho bài làm, lịch ôn và kế hoạch của bạn.</span></div>
      <div className={ui.scheduleLayout}>
        <div className={ui.workColumn}>
          <section className={ui.workSection} aria-labelledby="home-tasks-title">
            <div className={ui.blockHeading}><h3 id="home-tasks-title">Nhiệm vụ hôm nay</h3>{plan && <span>{plan.completedCount}/{plan.totalCount} hoàn tất</span>}</div>
            {tasks.length > 0 ? <>
              <ul className={ui.workList}>{shownTasks.map(task => <li className={ui.taskRow} key={task.id}>
                <span className={task.isCompleted ? ui.completedIcon : ui.rowIcon}><HomeIcon name={task.isCompleted ? "check-circle" : "book-open"} size={22} /></span>
                <div className={ui.rowCopy}><h4>{task.title}</h4><p className={ui.rowMeta}>{homeTaskTypeLabel(task.taskType)} · {task.estimatedMinutes} phút{task.isCompleted ? " · Đã hoàn thành" : ""}</p>{task.topicName && <p className={ui.topicName}>{task.topicName}</p>}</div>
                {!task.isCompleted && <>
                  {(task.taskType === "LEARN" || task.taskType === "CONCEPT_ACQUISITION") && <Link className={ui.rowAction} href="/student/theory" prefetch={false} aria-label={`Xem lý thuyết: ${task.title}`}><HomeIcon name="book-open" size={20} /></Link>}
                  <Link className={ui.rowAction} href={homeTaskHref(task, data.subject.id)} prefetch={false} aria-label={`Luyện: ${task.title}`}><HomeIcon name="arrow-up-right" size={20} /></Link>
                </>}
              </li>)}</ul>
              {tasks.length > 3 && <button type="button" className={ui.expandAction} aria-expanded={expanded} onClick={() => setExpanded(value => !value)}>{expanded ? "Thu gọn danh sách" : `Xem thêm ${tasks.length - 3} nhiệm vụ`}</button>}
            </> : <p className={ui.emptyText}>{plan ? "Hôm nay chưa có nhiệm vụ trong kế hoạch." : "Chưa có nhiệm vụ được lên lịch. Bạn vẫn có thể tự chọn bài để học."}</p>}
          </section>

          <section className={ui.workSection} aria-labelledby="home-review-title">
            <div className={ui.blockHeading}><h3 id="home-review-title">Ôn tập đến hạn</h3><span>{data.review.dueCount} nội dung</span></div>
            {data.review.dueTargets.length > 0 ? <ul className={ui.workList}>{data.review.dueTargets.map(target => <li className={ui.reviewRow} key={target.scheduleId}>
              <HomeIcon name="clock" size={20} /><div className={ui.rowCopy}><h4>{target.targetName}</h4>{homeDate(target.nextReviewAt) && <p className={ui.rowMeta}>Lịch ôn {homeDate(target.nextReviewAt)}</p>}</div>
            </li>)}</ul> : <p className={ui.emptyText}>{data.review.dueCount > 0 ? `Có ${data.review.dueCount} nội dung đến hạn ôn.` : "Chưa có nội dung đến hạn ôn."}</p>}
            {data.review.upcomingCount > 0 && <p className={ui.upcomingNote}>{data.review.upcomingCount} nội dung sắp đến lịch ôn.</p>}
            {data.review.dueCount > 0 && <Link className={ui.textAction} href={reviewHref} prefetch={false}>{action.type === "REVIEW_DUE" && routes.recommended ? "Mở nội dung được gợi ý" : "Mở bản đồ kiến thức"}<HomeIcon name="arrow-right" size={17} /></Link>}
          </section>

          {hasClassroom && <section className={ui.workSection} aria-labelledby="home-classroom-title">
            <div className={ui.blockHeading}><h3 id="home-classroom-title">Bài tập từ lớp</h3><Link className={ui.textAction} href="/student/attempts?tab=classroom">Xem bài lớp<HomeIcon name="arrow-right" size={17} /></Link></div>
            <div className={ui.assignmentCounts}><span className={data.assignments.overdueCount > 0 ? ui.warning : undefined}><strong>{data.assignments.overdueCount}</strong> quá hạn</span><span><strong>{data.assignments.inProgressCount}</strong> đang làm</span><span><strong>{data.assignments.pendingCount}</strong> chưa nộp</span></div>
            {data.assignments.upcoming.length > 0 ? <ul className={ui.workList}>{data.assignments.upcoming.map(assignment => <li className={ui.taskRow} key={assignment.assignmentId}>
              <div className={ui.rowCopy}><h4>{assignment.title}</h4><p className={assignment.isOverdue ? ui.warning : ui.rowMeta}>{assignment.isOverdue ? "Đã quá hạn" : "Bài tập từ lớp"}{homeDate(assignment.dueAt) ? ` · Hạn ${homeDate(assignment.dueAt)}` : ""}</p></div>
              <Link className={ui.rowAction} href={`/student/assignments/${encodeURIComponent(assignment.assignmentId)}`} prefetch={false} aria-label={`Mở bài lớp: ${assignment.title}`}><HomeIcon name="arrow-up-right" size={20} /></Link>
            </li>)}</ul> : <p className={ui.emptyText}>{data.assignments.activeCount === 0 ? "Chưa có bài lớp cần nộp." : `${data.assignments.activeCount} bài tập đang chờ bạn trong danh sách bài lớp.`}</p>}
          </section>}
        </div>

        <aside className={ui.planPanel} aria-labelledby="home-plan-title">
          <div className={ui.planTitle}><HomeIcon name="calendar-dots" size={24} /><h3 id="home-plan-title">Kế hoạch học</h3></div>
          {plan ? <>
            <p className={ui.planDate}>Hôm nay{homeDate(plan.date) ? ` · ${homeDate(plan.date)}` : ""}</p>
            <p className={ui.planProgress}><strong>{plan.completedCount}</strong><span>/ {plan.totalCount} nhiệm vụ</span></p>
            {plan.totalCount > 0 && <progress className={ui.progressBar} max={plan.totalCount} value={plan.completedCount} aria-label={`${plan.completedCount} trên ${plan.totalCount} nhiệm vụ hoàn tất`} />}
            <dl className={ui.planFacts}><div><dt>Thời gian dự kiến</dt><dd>{plan.totalEstimatedMinutes} phút</dd></div><div><dt>Quỹ thời gian mỗi ngày</dt><dd>{plan.availableMinutes} phút</dd></div></dl>
            {plan.notice && <p className={ui.planNotice}>{plan.notice}</p>}
          </> : <><p className={ui.planEmptyTitle}>Chọn một nhịp học vừa sức.</p><p className={ui.planDescription}>Bạn chưa lập kế hoạch. Đặt mục tiêu và dành khoảng thời gian phù hợp để bắt đầu.</p></>}
          <button type="button" className={ui.planAction} onClick={onOpenPlan}>{plan && plan.totalCount > 0 ? "Xem lộ trình 7 ngày" : "Lập kế hoạch học"}<HomeIcon name="arrow-right" size={18} /></button>
          {plan && plan.totalCount > 0 && <button type="button" className={ui.recalculateAction} disabled={recalculating} onClick={onRecalculate}>{recalculating ? "Đang cập nhật…" : "Cập nhật kế hoạch"}</button>}
          {feedback && <p className={ui.feedback} role="status">{feedback}</p>}
        </aside>
      </div>
    </section>
  </div>;
}
