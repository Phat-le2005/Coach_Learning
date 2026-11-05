"use client";

import dynamic from "next/dynamic";
import { useCallback, useEffect, useMemo, useRef, useState, type CSSProperties } from "react";
import { Camera, Check, ChevronLeft, ChevronRight, CircleHelp, ExternalLink, Hand, Moon, Pause, Pencil, Play, SearchX, Wifi, WifiOff, X } from "lucide-react";
import type { ClassroomStudentInfo } from "../classroom-types";
import { ACTIVITY_LABELS, assignmentProgress, classroomActivity, classroomPage, presenceLabel } from "../classroom-model";
import { classMomentSummary, classroomStyleKey, defaultDeskStyle, parseClassroomStyles, serializeClassroomStyles, type ClassroomStyles, type DeskStyle } from "../classroom-personalization";
import type { ClassroomSceneController } from "../classroom-scene";
import { MamMascot } from "./MamMascot";
import { StudentPortrait } from "./StudentPortrait";
import { DeskStyleEditor } from "./DeskStyleEditor";
import { ClassroomMomentDialog } from "./ClassroomMomentDialog";
import styles from "../Classroom3D.module.css";
import cozy from "../CozyCampus.module.css";

const Classroom3DScene = dynamic(() => import("./Classroom3DScene"), {
  ssr: false,
  loading: () => <div className={styles.stage}><p className={styles.sceneMessage} role="status">Mầm đang mở cửa lớp…</p></div>,
});

interface Props {
  students: ClassroomStudentInfo[];
  query: string;
  classroomId: string;
  classroomName: string;
  isDemo: boolean;
  onViewStudentWorkspace?: (studentId: string) => void;
}

export function Classroom3DPanel({ students, query, classroomId, classroomName, isDemo, onViewStudentWorkspace }: Props) {
  const [page, setPage] = useState(0);
  const [selectedId, setSelectedId] = useState<string>();
  const [motion, setMotion] = useState(true);
  const [reducedMotion, setReducedMotion] = useState(false);
  const [deskStyles, setDeskStyles] = useState<ClassroomStyles>({});
  const [saved, setSaved] = useState(true);
  const [momentOpen, setMomentOpen] = useState(false);
  const [snapshot, setSnapshot] = useState<string | null>(null);
  const [celebrating, setCelebrating] = useState(false);
  const [celebrationKey, setCelebrationKey] = useState(0);
  const [coach, setCoach] = useState("");
  const [sceneReady, setSceneReady] = useState(false);
  const controller = useRef<ClassroomSceneController | null>(null);
  const goalCelebrated = useRef(false);
  const classroom = useMemo(() => classroomPage(students, query, page), [students, query, page]);
  const selectedSeat = classroom.seats.find((seat) => seat.student && seat.student.id === selectedId);
  const student = selectedSeat?.student;
  const studentIds = useMemo(() => students.map((item) => item.id), [students]);
  const summary = useMemo(() => classMomentSummary(students, classroomName, false, isDemo), [students, classroomName, isDemo]);
  const onlineCount = students.filter((item) => item.presence === "online").length;
  const knownPresence = students.some((item) => item.presence === "online" || item.presence === "offline");
  const helpCount = students.filter((item) => item.helpRequest).length;
  const key = classroomStyleKey(classroomId);

  useEffect(() => {
    const preference = window.matchMedia("(prefers-reduced-motion: reduce)");
    const update = () => setReducedMotion(preference.matches);
    update(); preference.addEventListener("change", update);
    return () => preference.removeEventListener("change", update);
  }, []);

  useEffect(() => {
    function read() {
      try { setDeskStyles(parseClassroomStyles(localStorage.getItem(key), studentIds)); setSaved(true); }
      catch { setSaved(false); }
    }
    read();
    function onStorage(event: StorageEvent) { if (event.key === key) read(); }
    window.addEventListener("storage", onStorage);
    return () => window.removeEventListener("storage", onStorage);
  }, [key, studentIds]);

  useEffect(() => { if (selectedId && !selectedSeat) setSelectedId(undefined); }, [selectedId, selectedSeat]);
  useEffect(() => { if (!coach) return; const timer = setTimeout(() => setCoach(""), 4000); return () => clearTimeout(timer); }, [coach]);
  useEffect(() => { if (!celebrating) return; const timer = setTimeout(() => setCelebrating(false), 2100); return () => clearTimeout(timer); }, [celebrating, celebrationKey]);

  const celebrate = useCallback(() => {
    controller.current?.celebrate(); setCelebrating(true); setCelebrationKey((value) => value + 1);
    setCoach("Một tràng vỗ tay cho những cố gắng của lớp mình!");
  }, []);
  const receiveController = useCallback((value: ClassroomSceneController | null) => { controller.current = value; setSceneReady(Boolean(value)); }, []);
  useEffect(() => {
    if (!summary.goalReached) { goalCelebrated.current = false; return; }
    if (sceneReady && !goalCelebrated.current) { goalCelebrated.current = true; celebrate(); }
  }, [sceneReady, summary.goalReached, celebrate]);

  function changeStyle(next: DeskStyle) {
    if (!student) return;
    const updated = { ...deskStyles, [student.id]: next }; setDeskStyles(updated);
    try { localStorage.setItem(key, serializeClassroomStyles(updated)); setSaved(true); }
    catch { setSaved(false); }
  }
  function closeInspector() {
    const previous = selectedId; setSelectedId(undefined);
    if (previous) requestAnimationFrame(() => document.querySelector<HTMLButtonElement>(`[data-student-id="${CSS.escape(previous)}"]`)?.focus());
  }
  function greetMam() { controller.current?.greetMascot(); setCoach("Chào bạn, mình là Mầm! Một chút mỗi ngày, cả lớp cùng tiến bộ."); }
  function openMoment() { setSnapshot(controller.current?.snapshot() ?? null); setMomentOpen(true); }
  function closeMoment() { setMomentOpen(false); setSnapshot(null); }

  if (students.length > 0 && !classroom.matches.length) return <div className={styles.empty}><SearchX size={26} aria-hidden="true" /><h3>Không tìm thấy học sinh</h3><p>Thử tìm bằng tên khác hoặc email học sinh.</p></div>;

  const selectedStyle = student ? deskStyles[student.id] ?? defaultDeskStyle(student.id) : null;
  const PresenceIcon = student?.presence === "online" ? Wifi : student?.presence === "offline" ? WifiOff : CircleHelp;
  const coachMessage = coach || (!students.length ? "Mầm đã mở cửa lớp. Học sinh sẽ xuất hiện khi tham gia lớp học." : student?.helpRequest ? `${student.name.replace(/\s*\(Demo\s*\d+\)/i, "")} đang cần hỗ trợ. Thầy cô mở bài làm để xem nhé!` : "Mỗi bạn một nhịp. Cả lớp cùng tiến bộ. Chạm một bạn để bắt đầu nhé!");
  return (
    <section aria-label="Lớp học 3D" className={cozy.campus}>
      <div className={styles.room}>
        <div className={styles.roomHeader}>
          <div className={cozy.brand}><MamMascot /><div><span className={cozy.eyebrow}>COZY CAMPUS</span><h3>Lớp Mình</h3><div className={styles.presenceSummary}><span className={styles.onlineCount}><span className={styles.onlineDot} style={knownPresence ? undefined : { background: "#9aa89d" }} />{knownPresence ? `${onlineCount}/${students.length} online` : "Chưa có trạng thái online"}</span><span className={styles.onlineCount}><Hand size={13} aria-hidden="true" />{isDemo ? `${helpCount} cần hỗ trợ` : "Chưa có dữ liệu hỗ trợ"}</span></div></div></div>
          <div className={cozy.headerTools}>
            <div className={cozy.goal}>{summary.hasProgress ? <><span>{summary.completed}/{summary.total} bạn hoàn thành</span><div className={cozy.goalTrack} role="progressbar" aria-label="Mục tiêu hoàn thành bài tập" aria-valuenow={summary.completed} aria-valuemin={0} aria-valuemax={summary.total}><span style={{ width: `${summary.completed / summary.total * 100}%` }} /></div></> : <span>Chưa có tiến độ từng học sinh</span>}</div>
            <button type="button" className={cozy.momentButton} onClick={openMoment}><Camera size={15} aria-hidden="true" />Khoảnh khắc</button>
            <button type="button" className={styles.motionButton} disabled={reducedMotion} aria-pressed={!motion || reducedMotion} onClick={() => setMotion((value) => !value)}>{motion && !reducedMotion ? <Pause size={13} aria-hidden="true" /> : <Play size={13} aria-hidden="true" />}{reducedMotion ? "Đã giảm chuyển động" : motion ? "Tạm dừng chuyển động" : "Bật chuyển động"}</button>
          </div>
        </div>
        <div className={cozy.sceneLayout} data-inspector={Boolean(student)}>
          <div className={cozy.stageArea}>
            <Classroom3DScene seats={classroom.seats} selectedId={student?.id} motion={motion && !reducedMotion} onSelect={setSelectedId} onMascot={greetMam} onController={receiveController} customizations={deskStyles} />
            {celebrating && <div className={cozy.celebration} aria-hidden="true" data-celebration="active" key={celebrationKey}><span className={cozy.celebrationMessage}>Một tràng vỗ tay cho lớp mình! ✦</span>{motion && !reducedMotion && Array.from({ length: 24 }, (_, index) => <i className={cozy.confetti} key={index} style={{ "--x": `${4 + (index * 13) % 92}%`, "--size": `${7 + index % 5}px`, "--color": ["#aac9a2", "#c9b8e3", "#ecc28e", "#a7cbd7"][index % 4], "--delay": `${index % 6 * 50}ms` } as CSSProperties} />)}</div>}
          </div>

          {student && selectedStyle && selectedSeat && <aside className={cozy.inspector} aria-label="Hồ sơ học sinh được chọn" onKeyDown={(event) => { if (event.key === "Escape") closeInspector(); }}>
            <div className={cozy.inspectorHeading}><span>BẠN HỌC · BÀN {selectedSeat.number}</span><button type="button" className={cozy.iconButton} aria-label="Đóng hồ sơ học sinh" onClick={closeInspector}><X size={17} /></button></div>
            <div className={cozy.identity}><div className={cozy.portrait}><StudentPortrait id={student.id} style={selectedStyle} /></div><div><h4>{student.name}</h4><p>{student.email}</p><div className={cozy.presence} data-presence={student.presence ?? "unknown"}><PresenceIcon size={12} aria-hidden="true" />{presenceLabel(student)}</div></div></div>
            <div className={styles.progressGroup}>
              <div>
                <div className={styles.metricLabel}><span>Bài tập đã hoàn thành</span><strong>{assignmentProgress(student) === null ? "Chưa có dữ liệu" : `${student.completedAssignments}/${student.totalAssignments}`}</strong></div>
                {assignmentProgress(student) !== null && <div className={styles.track} role="progressbar" aria-label="Bài tập đã hoàn thành" aria-valuenow={assignmentProgress(student)!} aria-valuemin={0} aria-valuemax={100}><div className={styles.fill} style={{ width: `${assignmentProgress(student)}%` }} /></div>}
              </div>
              <div>
                <div className={styles.metricLabel}><span>Mức độ nắm vững</span><strong>{student.overallMastery === null ? "Chưa có dữ liệu" : `${student.overallMastery}%`}</strong></div>
                {student.overallMastery !== null && <div className={styles.track} role="progressbar" aria-label="Mức độ nắm vững" aria-valuenow={student.overallMastery} aria-valuemin={0} aria-valuemax={100}><div className={styles.fill} style={{ width: `${student.overallMastery}%` }} /></div>}
              </div>
              <div className={styles.secondary}>{ACTIVITY_LABELS[classroomActivity(student)]}{student.latestActivityAt ? ` · ${student.latestActivityAt}` : ""}</div>
            </div>
            <div>
              {student.helpRequest ? <div className={cozy.request}><strong><Hand size={14} aria-hidden="true" />Yêu cầu hỗ trợ</strong>{student.helpRequest.message}</div> : <div><p className={cozy.sectionLabel}>Nội dung cần củng cố</p>{student.weakTopics.length ? <ul className={cozy.topics}>{student.weakTopics.map((topic) => <li key={topic}>{topic}</li>)}</ul> : <div className={styles.secondary}>Chưa có dữ liệu nội dung cần củng cố.</div>}</div>}
              <button type="button" disabled={!onViewStudentWorkspace} className={`${cozy.primaryButton} ${cozy.openWork}`} onClick={() => onViewStudentWorkspace?.(student.id)}><ExternalLink size={14} aria-hidden="true" />{isDemo ? "Bài làm minh họa chưa kết nối" : student.helpRequest ? "Xem bài làm để hỗ trợ" : "Xem bài làm"}</button>
            </div>
            <DeskStyleEditor value={selectedStyle} onChange={changeStyle} saved={saved} />
          </aside>}
        </div>
        <div className={styles.legend} aria-label="Chú giải hoạt động"><span><Pencil size={13} aria-hidden="true" />Đang học</span><span><Hand size={13} aria-hidden="true" />Cần hỗ trợ</span><span><Check size={13} aria-hidden="true" />Hoàn thành</span><span><Moon size={13} aria-hidden="true" />Ngoại tuyến</span></div>
      </div>
      <div className={cozy.campusFooter}>
        <div className={cozy.coach} aria-live="polite"><MamMascot /><span><strong>Mầm nhắn nhỏ: </strong>{coachMessage}</span></div>
        <div className={styles.footer}><span>{query.trim() ? `${classroom.matches.length} kết quả / ${students.length} học sinh` : `${students.length} học sinh · một lớp mình`}</span>{classroom.pageCount > 1 && <div className={styles.pagination}><button className={styles.pageButton} type="button" aria-label="Nhóm học sinh trước" disabled={classroom.page === 0} onClick={() => { setSelectedId(undefined); setPage(classroom.page - 1); }}><ChevronLeft size={15} /></button><span>Nhóm {classroom.page + 1}/{classroom.pageCount}</span><button className={styles.pageButton} type="button" aria-label="Nhóm học sinh sau" disabled={classroom.page === classroom.pageCount - 1} onClick={() => { setSelectedId(undefined); setPage(classroom.page + 1); }}><ChevronRight size={15} /></button></div>}</div>
      </div>
      {momentOpen && <ClassroomMomentDialog isDemo={isDemo} snapshot={snapshot} students={students} classroomName={classroomName} onClose={closeMoment} onCelebrate={celebrate} />}
    </section>
  );
}
