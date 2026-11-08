"use client";
import Link from "next/link";
import { useEffect, useId, useRef, useState, type KeyboardEvent } from "react";
import { AnimatePresence, motion, useIsPresent } from "motion/react";
import type { ReactNode } from "react";
import { getHomeRoutes } from "../home-presentation";
import type { StudentHomeViewModel } from "../types";
import ui from "../HomeRefresh.module.css";
import { HomeIcon } from "./HomeIcon";
import { KnowledgeCanopy } from "./KnowledgeCanopy";
import { HeroNatureScene } from "./nature/HeroNatureScene";
import { useGardenMotion, useGardenSectionInView } from "./nature/GardenMotionContext";
const topics = ["Vườn tri thức", "Bài viết tay", "Kế hoạch học"];
const ROTATION_MS = 5000;

function HeroPanel({ id, index, title, description, actions, foot, visual, animated }: {
  id: string; index: number; title: ReactNode; description: ReactNode;
  actions: ReactNode; foot: string; visual: ReactNode; animated: boolean;
}) {
  const present = useIsPresent();
  const duration = animated ? .48 : 0;
  const arrive = { duration, ease: [.16, 1, .3, 1] as const };
  return <motion.div className={ui.heroPanel} id={present ? `${id}-panel-${index}` : undefined}
    role={present ? "tabpanel" : undefined} aria-labelledby={present ? `${id}-tab-${index}` : undefined}
    aria-hidden={!present || undefined} inert={!present} data-present={present}
    initial="enter" animate="visible" exit="leave">
    <div className={ui.heroCopy}>
      <div className={ui.heroTitleClip}><motion.div
        variants={{ enter: { y: animated ? 28 : 0, opacity: 0 }, visible: { y: 0, opacity: 1, transition: arrive }, leave: { y: animated ? -12 : 0, opacity: 0, transition: { duration: animated ? .18 : 0 } } }}>
        {present ? <h1>{title}</h1> : <h2>{title}</h2>}
      </motion.div></div>
      <motion.p className={ui.heroDescription}
        variants={{ enter: { y: animated ? 12 : 0, opacity: 0 }, visible: { y: 0, opacity: 1, transition: { ...arrive, delay: animated ? .07 : 0 } }, leave: { opacity: 0, transition: { duration: animated ? .12 : 0 } } }}>{description}</motion.p>
      <motion.div className={ui.heroActions}
        variants={{ enter: { y: animated ? 8 : 0, opacity: 0 }, visible: { y: 0, opacity: 1, transition: { ...arrive, delay: animated ? .13 : 0 } }, leave: { opacity: 0, transition: { duration: animated ? .1 : 0 } } }}>{actions}</motion.div>
      <motion.p className={ui.heroFoot}
        variants={{ enter: { opacity: 0 }, visible: { opacity: 1, transition: { duration, delay: animated ? .18 : 0 } }, leave: { opacity: 0, transition: { duration: animated ? .1 : 0 } } }}>{foot}</motion.p>
    </div>
    <motion.div className={ui.heroVisual}
      variants={{ enter: { x: animated ? 22 : 0, opacity: 0, scale: animated ? .985 : 1 }, visible: { x: 0, opacity: 1, scale: 1, transition: { ...arrive, delay: animated ? .05 : 0 } }, leave: { x: animated ? -12 : 0, opacity: 0, scale: animated ? .99 : 1, transition: { duration: animated ? .2 : 0 } } }}>{visual}</motion.div>
  </motion.div>;
}
export function FocusHero({ data, onOpenPlan, suspended = false }: { data: StudentHomeViewModel; onOpenPlan: () => void; suspended?: boolean }) {
  const [active, setActive] = useState(0);
  const [playing, setPlaying] = useState(true);
  const [hovered, setHovered] = useState(false);
  const [focused, setFocused] = useState(false);
  const [manualRevision, setManualRevision] = useState(0);
  const { ambientEnabled, isTabHidden } = useGardenMotion();
  const { ref, isInView } = useGardenSectionInView<HTMLElement>("0px");
  const [isReducedMotion, setReducedMotion] = useState(false);
  useEffect(() => {
    // Keep rotation in sync when the OS preference changes while this page is open.
    const preference = window.matchMedia("(prefers-reduced-motion: reduce)");
    const update = () => setReducedMotion(preference.matches);
    update();
    preference.addEventListener("change", update);
    return () => preference.removeEventListener("change", update);
  }, []);
  const canRotate = playing && ambientEnabled && !isReducedMotion && !isTabHidden && isInView && !hovered && !focused && !suspended;
  useEffect(() => {
    if (!canRotate) return;
    const timer = window.setInterval(() => setActive(index => (index + 1) % topics.length), ROTATION_MS);
    return () => window.clearInterval(timer);
  }, [canRotate, manualRevision]);
  const tabRefs = useRef<Array<HTMLButtonElement | null>>([]);
  const id = useId();
  const routes = getHomeRoutes(data);
  const plan = data.todayPlan;
  function change(next: number, focus = false) {
    const index = (next + topics.length) % topics.length;
    setActive(index);
    setManualRevision(value => value + 1);
    if (focus) tabRefs.current[index]?.focus();
  }
  function onTabKey(event: KeyboardEvent, index: number) {
    const next = event.key === "ArrowRight" ? index + 1 : event.key === "ArrowLeft" ? index - 1
      : event.key === "Home" ? 0 : event.key === "End" ? 2 : undefined;
    if (next !== undefined) { event.preventDefault(); change(next, true); }
  }
  const content = [
    { title: <>Hiểu rõ từng bước.<br />Học đúng trọng tâm.</>,
      description: "Nhìn lại lời giải, kết nối kiến thức và tìm phần cần luyện tiếp.",
      foot: "Mỗi bài làm giúp bạn hiểu mình hơn.",
      actions: <><Link className={ui.primary} href={routes.knowledge}>Vũ trụ tri thức<HomeIcon name="graph" size={20} /></Link><Link className={ui.secondary} href={routes.attempts}>Bài tập của tôi<HomeIcon name="arrow-right" size={18} /></Link></>,
      visual: <div className={ui.canopy}><KnowledgeCanopy compact regions={data.knowledgeRegions}
        subjectName={data.subject.name} ghost={data.knowledgeRegions.length === 0}
        actionType={data.currentAction.type} targetName={data.currentAction.targetName} />
        <p className={ui.figureCaption}>{data.knowledgeRegions.length ? "Một góc nhìn chung cho những điều bạn đang học." : "Khám phá chủ đề để bắt đầu kết nối kiến thức."}</p></div> },
    { title: <>Viết lời giải.<br />Nhìn rõ từng bước.</>,
      description: <>Viết tay, tải bài giấy hoặc dùng điện thoại làm bảng viết.<br className={ui.descriptionBreak} /> Xem lại bản chép rồi tiếp tục với bài làm.</>,
      foot: "Bạn trình bày cách làm. EduMS giúp bạn nhìn lại.",
      actions: <><Link className={ui.primary} href={routes.practice} prefetch={false}>Mở giấy viết<HomeIcon name="pen-nib" size={20} /></Link><Link className={ui.secondary} href={routes.attempts}>Bài tập của tôi<HomeIcon name="arrow-right" size={18} /></Link></>,
      visual: <div className={ui.writingFigure}><div className={ui.paper}>
        <div className={ui.paperTop}><span><HomeIcon name="pen-nib" />Bài viết tay</span><small>Minh họa tính năng</small></div>
        <div className={ui.paperInk} aria-label="Ví dụ minh họa: x bình phương cộng 3x trừ 4 bằng 0"><span>x² + 3x − 4 = 0</span></div>
        <div className={ui.paperResult}><div><span>Bản chép — ví dụ</span><small>Chưa xác nhận</small></div><p>x² + 3x − 4 = 0</p></div>
        <div className={ui.paperBottom}><HomeIcon name="check-circle" size={16} />Bạn xem lại bản chép trước khi dùng.</div>
      </div><p className={ui.phoneHint}><HomeIcon name="device-mobile" size={19} />Viết từ điện thoại hoặc máy tính.</p></div> },
    { title: <>Mục tiêu rõ ràng.<br />Nhịp học vừa sức.</>,
      description: <>Chọn điều cần học và sắp thời gian phù hợp.<br className={ui.descriptionBreak} /> Tạo một kế hoạch vừa sức để theo được.</>,
      foot: "Một kế hoạch vừa sức, để bạn theo được.",
      actions: <><button type="button" className={ui.primary} onClick={onOpenPlan}>{plan && plan.totalCount > 0 ? "Xem kế hoạch học" : "Lập kế hoạch học"}<HomeIcon name="calendar-dots" size={20} /></button><Link className={ui.secondary} href={routes.practice} prefetch={false}>Chọn bài luyện<HomeIcon name="arrow-right" size={18} /></Link></>,
      visual: <div className={ui.planner}><div className={ui.plannerTop}><HomeIcon name="calendar-dots" size={25} /><strong>{plan ? "Kế hoạch của bạn" : "Một tuần vừa sức"}</strong></div>
        {plan && plan.tasks.length > 0 ? <><p className={ui.planSummary}>{plan.completedCount}/{plan.totalCount} nhiệm vụ hôm nay · {plan.totalEstimatedMinutes} phút</p><ul className={ui.planPreview}>{plan.tasks.slice(0, 3).map(task => <li key={task.id}><HomeIcon name={task.isCompleted ? "check-circle" : "clock"} size={19} /><span>{task.title}<small>{task.isCompleted ? "Đã hoàn thành" : `${task.estimatedMinutes} phút dự kiến`}</small></span></li>)}</ul></> : <div className={ui.planStart}><HomeIcon name="calendar-dots" size={58} /><h2>Chọn một nhịp học phù hợp.</h2><p>Đặt mục tiêu và quỹ thời gian của bạn. Lịch học sẽ xuất hiện khi bạn tạo kế hoạch.</p></div>}
        <p className={ui.plannerBottom}>Bạn chọn mục tiêu và thời gian phù hợp.</p></div> },
  ];
  return <section ref={ref} className={ui.hero} aria-label="Ba cách học cùng EduMS" aria-roledescription="carousel"
    data-rotation={canRotate ? "running" : "paused"}
    onMouseEnter={() => setHovered(true)} onMouseLeave={() => setHovered(false)}
    onFocusCapture={() => setFocused(true)} onBlurCapture={event => {
      if (!(event.relatedTarget instanceof Node) || !event.currentTarget.contains(event.relatedTarget)) setFocused(false);
    }}>
    <div className={ui.scene}><HeroNatureScene /></div>
    <AnimatePresence initial={false}>
      <HeroPanel key={active} id={id} index={active} {...content[active]} animated={ambientEnabled && !isReducedMotion} />
    </AnimatePresence>
    {topics.map((_, index) => index !== active && <div key={index} hidden role="tabpanel" id={`${id}-panel-${index}`} aria-labelledby={`${id}-tab-${index}`} />)}
    <div className={ui.pagination}><button type="button" className={ui.pageArrow} aria-label="Xem banner trước" onClick={() => change(active - 1)}><HomeIcon name="caret-left" size={19} /></button>
      <div role="tablist" aria-label="Chọn nội dung banner">{topics.map((name, index) => <button type="button" key={name} id={`${id}-tab-${index}`} ref={node => { tabRefs.current[index] = node; }} role="tab" aria-label={`${index + 1}. ${name}`} aria-selected={active === index} aria-controls={`${id}-panel-${index}`} tabIndex={active === index ? 0 : -1} onClick={() => change(index)} onKeyDown={event => onTabKey(event, index)}><span /></button>)}</div>
      <button type="button" className={ui.pageArrow} aria-label="Xem banner tiếp theo" onClick={() => change(active + 1)}><HomeIcon name="caret-right" size={19} /></button>
      <button type="button" className={ui.pageArrow} disabled={isReducedMotion}
        aria-label={isReducedMotion ? "Đã giảm chuyển động" : playing ? "Tạm dừng tự chuyển banner" : "Bật tự chuyển banner"}
        title={isReducedMotion ? "Thiết bị đang chọn giảm chuyển động" : playing ? "Tự chuyển mỗi 5 giây · Tạm dừng" : "Bật tự chuyển mỗi 5 giây"}
        onClick={() => setPlaying(value => !value)}><HomeIcon name={playing && !isReducedMotion ? "pause" : "play"} size={17} /></button>
    </div>
  </section>;
}
