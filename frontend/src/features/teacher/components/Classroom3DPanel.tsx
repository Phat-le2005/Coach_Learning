"use client";

import dynamic from "next/dynamic";
import { useCallback, useEffect, useMemo, useRef, useState, type CSSProperties, type ReactNode } from "react";
import {
  ArrowLeft,
  BookOpen,
  Camera,
  Check,
  ChevronLeft,
  ChevronRight,
  CircleHelp,
  Expand,
  ExternalLink,
  Eye,
  Hand,
  Maximize2,
  Minimize2,
  Moon,
  Pause,
  Pencil,
  Play,
  SearchX,
  Wifi,
  WifiOff,
  X,
  School, ClipboardList, Network, BarChart3, FlaskConical, List, Users, Footprints, DoorOpen,
} from "lucide-react";
import type { ClassroomStudentInfo } from "../classroom-types";
import { ACTIVITY_LABELS, assignmentProgress, classroomActivity, classroomPage, presenceLabel } from "../classroom-model";
import {
  classMomentSummary,
  classroomStyleKey,
  defaultDeskStyle,
  parseClassroomStyles,
  serializeClassroomStyles,
  type ClassroomStyles,
  type DeskStyle,
} from "../classroom-personalization";
import type { ClassroomSceneController, SceneHoverInfo, StationPhase } from "../classroom-scene";
import { MamMascot } from "./MamMascot";
import { StudentPortrait } from "./StudentPortrait";
import { DeskStyleEditor } from "./DeskStyleEditor";
import { ClassroomMomentDialog } from "./ClassroomMomentDialog";
import styles from "../Classroom3D.module.css";
import cozy from "../CozyCampus.module.css";

const Classroom3DScene = dynamic(() => import("./Classroom3DScene"), {
  ssr: false,
  loading: () => (
    <div className={styles.stage}>
      <p className={styles.sceneMessage} role="status">
        Mầm đang mở cửa lớp…
      </p>
    </div>
  ),
});

export const STATIONS = [
  {
    key: "classes",
    label: "Phòng Học Chính",
    stationTitle: "Phòng 1 · Lớp Học Chính",
    icon: <School size={18} aria-hidden="true" />,
    openIcon: <School size={18} aria-hidden="true" />,
    desc: "Quan sát 10 bàn học sinh & tương tác cùng Mầm Xanh",
    actionHint: "Về phòng học chính",
    interactingText: "Đang quan sát Lớp Học Chính...",
  },
  {
    key: "submissions",
    label: "Phòng Chấm Bài",
    stationTitle: "Phòng 2 · Văn Phòng Chấm Bài",
    icon: <ClipboardList size={18} aria-hidden="true" />,
    openIcon: <BookOpen size={18} aria-hidden="true" />,
    desc: "Đi qua cửa sang Văn Phòng Giáo Viên, lật Sổ chấm bài 3D & mở toàn màn hình",
    actionHint: "Sang phòng chấm bài →",
    interactingText: "Đang lật mở Sổ Chấm Bài 3D tại Văn Phòng Giáo Viên...",
  },
  {
    key: "theory",
    label: "Studio Lý Thuyết",
    stationTitle: "Phòng 4 · Studio Sơ Đồ Lý Thuyết",
    icon: <Network size={18} aria-hidden="true" />,
    openIcon: <Network size={18} aria-hidden="true" />,
    desc: "Đi sang Phòng Studio Lý Thuyết, bật Đại Bảng Sơ Đồ Tư Duy 3D",
    actionHint: "← Sang phòng lý thuyết",
    interactingText: "Đang kích hoạt Đại Bảng Sơ Đồ Tư Duy 3D tại Studio...",
  },
  {
    key: "materials",
    label: "Thư Viện Học Liệu",
    stationTitle: "Phòng 3 · Thư Viện Học Liệu & Đề Thi",
    icon: <BookOpen size={18} aria-hidden="true" />,
    openIcon: <BookOpen size={18} aria-hidden="true" />,
    desc: "Đi sang Thư Viện Học Liệu, mở Tủ Đề Thi & Sổ Học Liệu 3D",
    actionHint: "Sang thư viện học liệu →",
    interactingText: "Đang kéo ngăn tủ & lật mở Sổ Đề Thi 3D tại Thư Viện...",
  },
  {
    key: "analytics",
    label: "Phòng Lab AI",
    stationTitle: "Phòng 5 · Phòng Lab Phân Tích AI",
    icon: <BarChart3 size={18} aria-hidden="true" />,
    openIcon: <BarChart3 size={18} aria-hidden="true" />,
    desc: "Đi sang Phòng Lab Mầm Xanh AI, bật Đài Quan Sát Biểu Đồ Hologram 3D",
    actionHint: "← Sang phòng Lab AI",
    interactingText: "Đang kích hoạt Đài Quan Sát Biểu Đồ Năng Lực Hologram 3D...",
  },
] as const;

const STATION_PIN_ITEMS = STATIONS.filter((s) => s.key !== "classes");

export type ViewMode = "normal" | "full" | "compact";

interface Props {
  students: ClassroomStudentInfo[];
  query?: string;
  onQueryChange?: (query: string) => void;
  classroomId: string;
  classroomName: string;
  isDemo?: boolean;
  onToggleDemo?: (demo: boolean) => void;
  onSwitchTo2D?: () => void;
  onViewStudentWorkspace?: (studentId: string) => void;
  currentStation?: string;
  stationPhase?: StationPhase;
  onStationSelect?: (station: string) => void;
  onStationPhaseChange?: (station: string, phase: StationPhase) => void;
  viewMode?: ViewMode;
  onToggleViewMode?: (mode: ViewMode) => void;
  stationWorkspace?: ReactNode;
}

export function Classroom3DPanel({
  students,
  query = "",
  onQueryChange,
  classroomId,
  classroomName,
  isDemo = false,
  onToggleDemo,
  onSwitchTo2D,
  onViewStudentWorkspace,
  currentStation = "classes",
  stationPhase: controlledPhase,
  onStationSelect,
  onStationPhaseChange,
  viewMode: controlledViewMode,
  onToggleViewMode,
  stationWorkspace,
}: Props) {
  const [localViewMode, setLocalViewMode] = useState<ViewMode>("full");
  const activeViewMode = controlledViewMode ?? localViewMode;

  const setViewMode = (mode: ViewMode) => {
    setLocalViewMode(mode);
    onToggleViewMode?.(mode);
  };

  const [localPhase, setLocalPhase] = useState<StationPhase>("ready");
  const activePhase = controlledPhase ?? localPhase;
  const [drawerPeeking3D, setDrawerPeeking3D] = useState(false);
  const [hoverInfo, setHoverInfo] = useState<SceneHoverInfo | null>(null);
  const [rosterOpen, setRosterOpen] = useState(false);

  const handlePhaseChange = useCallback(
    (station: string, phase: StationPhase) => {
      setLocalPhase(phase);
      if (phase === "walking") {
        setDrawerPeeking3D(false);
      }
      onStationPhaseChange?.(station, phase);
    },
    [onStationPhaseChange],
  );

  // Reset peek & hover when changing rooms
  useEffect(() => {
    setDrawerPeeking3D(false);
    setHoverInfo(null);
  }, [currentStation]);

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
  const stationPinRefs = useRef<(HTMLElement | null)[]>([]);
  const goalCelebrated = useRef(false);
  const classroom = useMemo(() => classroomPage(students, query, page), [students, query, page]);
  const selectedSeat = classroom.seats.find((seat) => seat.student && seat.student.id === selectedId);
  const student = selectedSeat?.student;
  const studentIds = useMemo(() => students.map((item) => item.id), [students]);
  const summary = useMemo(
    () => classMomentSummary(students, classroomName, false, isDemo),
    [students, classroomName, isDemo],
  );
  const onlineCount = students.filter((item) => item.presence === "online").length;
  const knownPresence = students.some((item) => item.presence === "online" || item.presence === "offline");
  const helpCount = students.filter((item) => item.helpRequest).length;
  const key = classroomStyleKey(classroomId);

  useEffect(() => {
    const preference = window.matchMedia("(prefers-reduced-motion: reduce)");
    const update = () => {
      setReducedMotion(preference.matches);
    };
    update();
    preference.addEventListener("change", update);
    window.addEventListener("resize", update);
    return () => {
      preference.removeEventListener("change", update);
      window.removeEventListener("resize", update);
    };
  }, []);

  useEffect(() => {
    function read() {
      try {
        setDeskStyles(parseClassroomStyles(localStorage.getItem(key), studentIds));
        setSaved(true);
      } catch {
        setSaved(false);
      }
    }
    read();
    function onStorage(event: StorageEvent) {
      if (event.key === key) read();
    }
    window.addEventListener("storage", onStorage);
    return () => window.removeEventListener("storage", onStorage);
  }, [key, studentIds]);

  useEffect(() => {
    if (selectedId && !selectedSeat) setSelectedId(undefined);
  }, [selectedId, selectedSeat]);

  useEffect(() => {
    if (!coach) return;
    const timer = setTimeout(() => setCoach(""), 4000);
    return () => clearTimeout(timer);
  }, [coach]);

  useEffect(() => {
    if (!celebrating) return;
    const timer = setTimeout(() => setCelebrating(false), 2100);
    return () => clearTimeout(timer);
  }, [celebrating, celebrationKey]);

  const celebrate = useCallback(() => {
    controller.current?.celebrate();
    setCelebrating(true);
    setCelebrationKey((value) => value + 1);
    setCoach("Một tràng vỗ tay cho những cố gắng của lớp mình!");
  }, []);

  const receiveController = useCallback((value: ClassroomSceneController | null) => {
    controller.current = value;
    setSceneReady(Boolean(value));
  }, []);

  useEffect(() => {
    if (!summary.goalReached) {
      goalCelebrated.current = false;
      return;
    }
    if (sceneReady && !goalCelebrated.current) {
      goalCelebrated.current = true;
      celebrate();
    }
  }, [sceneReady, summary.goalReached, celebrate]);

  function changeStyle(next: DeskStyle) {
    if (!student) return;
    const updated = { ...deskStyles, [student.id]: next };
    setDeskStyles(updated);
    try {
      localStorage.setItem(key, serializeClassroomStyles(updated));
      setSaved(true);
    } catch {
      setSaved(false);
    }
  }

  function closeInspector() {
    const previous = selectedId;
    setSelectedId(undefined);
    if (previous) {
      requestAnimationFrame(() =>
        document.querySelector<HTMLButtonElement>(`[data-student-id="${CSS.escape(previous)}"]`)?.focus(),
      );
    }
  }

  function greetMam() {
    controller.current?.greetMascot();
    setCoach("Chào bạn, mình là Mầm! Một chút mỗi ngày, cả lớp cùng tiến bộ.");
  }

  function openMoment() {
    setSnapshot(controller.current?.snapshot() ?? null);
    setMomentOpen(true);
  }

  function closeMoment() {
    setMomentOpen(false);
    setSnapshot(null);
  }

  if (students.length > 0 && !classroom.matches.length) {
    return (
      <div className={styles.empty}>
        <SearchX size={26} aria-hidden="true" />
        <h3>Không tìm thấy học sinh</h3>
        <p>Thử tìm bằng tên khác hoặc email học sinh.</p>
      </div>
    );
  }

  const selectedStyle = student ? deskStyles[student.id] ?? defaultDeskStyle(student.id) : null;
  const PresenceIcon = student?.presence === "online" ? Wifi : student?.presence === "offline" ? WifiOff : CircleHelp;
  const currentStationMeta = STATIONS.find((s) => s.key === currentStation) ?? STATIONS[0];
  const isAtWorkStation = currentStation !== "classes";
  const showStationOverlay = isAtWorkStation && activePhase === "ready" && !drawerPeeking3D && Boolean(stationWorkspace);
  const isStudentPopoverOpen = Boolean(
    student && selectedStyle && selectedSeat && currentStation === "classes" && activePhase === "ready",
  );
  const anyPopoverOpen = showStationOverlay || isStudentPopoverOpen;

  const coachMessage =
    coach ||
    (!students.length
      ? "Mầm đã mở cửa lớp. Học sinh sẽ xuất hiện khi tham gia lớp học."
      : student?.helpRequest
      ? `${student.name.replace(/\s*\(Demo\s*\d+\)/i, "")} đang cần hỗ trợ. Thầy cô mở bài làm để xem nhé!`
      : isAtWorkStation
      ? `Thầy cô đang ở ${currentStationMeta.stationTitle} (${currentStationMeta.label}). Nhấp "Về giữa lớp 3D" khi muốn đi tuần lại nhé!`
      : "Chọn một học sinh để xem tình hình học tập, hoặc mở Học liệu, Lý thuyết, Chấm bài ở thanh phía trên.");

  return (
    <section aria-label="Lớp học 3D" className={cozy.campus}>
      {activeViewMode === "compact" && (
        <div className={styles.compactBar} role="region" aria-label="Thanh trạng thái 3D thu gọn">
          <div className={styles.compactInfo}>
            <MamMascot />
            <div className={styles.compactStation}>
              <span className={styles.compactStationTag}>TRẠM HIỆN TẠI</span>
              <strong>
                {currentStationMeta.icon} {currentStationMeta.label}
              </strong>
            </div>
          </div>

          <div className={styles.stationQuickBar} role="tablist" aria-label="Chuyển trạm 3D">
            {STATIONS.map((st) => {
              const active = currentStation === st.key;
              return (
                <button
                  key={st.key}
                  type="button"
                  role="tab"
                  aria-selected={active}
                  className={`${styles.stationPill} ${active ? styles.stationPillActive : ""}`}
                  onClick={() => onStationSelect?.(st.key)}
                  title={`${st.label}: ${st.desc}`}
                >
                  <span aria-hidden="true">{st.icon}</span>
                  <span className={styles.stationPillText}>{st.label}</span>
                </button>
              );
            })}
          </div>

          <button
            type="button"
            className={styles.compactExpandBtn}
            onClick={() => setViewMode("normal")}
            title="Mở rộng lại không gian 3D"
          >
            <Maximize2 size={14} aria-hidden="true" />
            <span>Mở 3D</span>
          </button>
        </div>
      )}

      <div
        className={styles.room}
        data-view-mode={activeViewMode}
        style={
          activeViewMode === "compact"
            ? { height: 0, minHeight: 0, overflow: "hidden", border: "none", margin: 0, padding: 0 }
            : undefined
        }
      >
        <div className={cozy.sceneLayout} data-inspector="false">
          <div className={cozy.stageArea}>
            {/* Top-left Floating Room Status Badge */}
            <div
              className={styles.floatingStationBadge}
              data-hidden={anyPopoverOpen}
              aria-live="polite"
            >
              <span className={styles.badgeIcon} aria-hidden="true">
                {activePhase === "walking" ? <Footprints size={18} aria-hidden="true" /> : activePhase === "interacting" ? currentStationMeta.openIcon : currentStationMeta.icon}
              </span>
              <div className={styles.badgeText}>
                <span className={styles.badgeSub}>
                  {activePhase === "walking" ? "Đang chuyển phòng…" : activePhase === "interacting" ? "Đang mở nội dung…" : "Lớp học 3D"}
                </span>
                <span className={styles.badgeTitle}>{currentStationMeta.stationTitle}</span>
              </div>
              {isAtWorkStation && activePhase === "ready" && drawerPeeking3D && (
                <button
                  type="button"
                  className={styles.reopenBookBtn}
                  onClick={() => setDrawerPeeking3D(false)}
                >
                  <BookOpen size={13} aria-hidden="true" />
                  <span>Mở lại khung {currentStationMeta.label}</span>
                </button>
              )}
              {isAtWorkStation && (
                <button
                  type="button"
                  className={styles.backToAisleMiniBtn}
                  onClick={() => onStationSelect?.("classes")}
                  title="Đi bộ ra mở Cửa số 5 về Phòng Học Chính"
                >
                  <ArrowLeft size={13} aria-hidden="true" />
                  <span>Về lớp học</span>
                </button>
              )}
            </div>

            {/* Collapsible Right-Side Student Roster & Quick Controls Drawer */}
            <div
              className={styles.rosterDrawerWrap}
              data-open={rosterOpen}
              data-hidden={anyPopoverOpen}
              aria-label="Danh sách học sinh và điều khiển thu gọn bên phải"
            >
              <div className={styles.topRightHudRow}>
                <button
                  type="button"
                  className={styles.hudMiniBtn}
                  onClick={openMoment}
                  title="Chụp khoảnh khắc lớp học 3D"
                >
                  <Camera size={14} aria-hidden="true" />
                  <span>Khoảnh khắc</span>
                </button>
                {onToggleDemo && (
                  <button
                    type="button"
                    className={`${styles.hudMiniBtn} ${isDemo ? styles.hudMiniBtnActive : ""}`}
                    onClick={() => onToggleDemo(!isDemo)}
                    title="Bật/tắt chế độ minh họa 10 học sinh mẫu"
                  >
                    <FlaskConical size={14} aria-hidden="true" /><span>{isDemo ? "Đang xem lớp mẫu" : "Minh họa 10 bạn"}</span>
                  </button>
                )}
                {onSwitchTo2D && (
                  <button
                    type="button"
                    className={styles.hudMiniBtn}
                    onClick={onSwitchTo2D}
                    title="Chuyển sang chế độ danh sách 2D"
                  >
                    <List size={14} aria-hidden="true" /><span>Chế độ 2D</span>
                  </button>
                )}
                <button
                  type="button"
                  className={styles.rosterToggleBtn}
                  aria-expanded={rosterOpen}
                  onClick={() => setRosterOpen((v) => !v)}
                  title={rosterOpen ? "Thu gọn danh sách học sinh" : "Mở danh sách học sinh"}
                >
                  <Users size={14} aria-hidden="true" /><span>Học sinh ({students.length})</span>
                  {rosterOpen ? <ChevronRight size={14} aria-hidden="true" /> : <ChevronLeft size={14} aria-hidden="true" />}
                </button>
              </div>

              {rosterOpen && (
                <div className={styles.rosterDrawerBody}>
                  <div className={styles.rosterDrawerHeader}>
                    <strong>Danh sách lớp ({students.length})</strong>
                    <small>Nhấn vào HS để Giáo viên đi bộ tới bàn</small>
                  </div>
                  {onQueryChange && (
                    <div className={styles.rosterSearchWrap}>
                      <input
                        type="search"
                        className={styles.rosterSearchInput}
                        placeholder="Tìm tên hoặc email học sinh…"
                        value={query}
                        onChange={(e) => onQueryChange(e.target.value)}
                      />
                    </div>
                  )}
                  <div className={styles.rosterDrawerList}>
                    {classroom.seats.map((seat) => {
                      const st = seat.student;
                      if (!st) return null;
                      const active = st.id === selectedId;
                      const act = classroomActivity(st);
                      return (
                        <button
                          key={st.id}
                          type="button"
                          className={`${styles.rosterStudentItem} ${active ? styles.rosterStudentItemActive : ""}`}
                          onClick={() => {
                            if (currentStation !== "classes") {
                              onStationSelect?.("classes");
                            }
                            setSelectedId(st.id);
                            setRosterOpen(false);
                          }}
                        >
                          <span className={styles.rosterSeatBadge}>Bàn {seat.number}</span>
                          <span className={styles.rosterStudentName}>
                            {st.name.replace(/\s*\(Demo\s*\d+\)\s*$/i, "")}
                          </span>
                          <span className={styles.rosterStatusDot} data-activity={act} title={ACTIVITY_LABELS[act]} />
                        </button>
                      );
                    })}
                  </div>
                  {classroom.pageCount > 1 && (
                    <div className={styles.pagination} style={{ padding: "6px 10px" }}>
                      <button
                        className={styles.pageButton}
                        type="button"
                        disabled={classroom.page === 0}
                        onClick={() => {
                          setSelectedId(undefined);
                          setPage(classroom.page - 1);
                        }}
                      >
                        <ChevronLeft size={14} />
                      </button>
                      <span style={{ fontSize: "0.75rem" }}>
                        Nhóm {classroom.page + 1}/{classroom.pageCount}
                      </span>
                      <button
                        className={styles.pageButton}
                        type="button"
                        disabled={classroom.page === classroom.pageCount - 1}
                        onClick={() => {
                          setSelectedId(undefined);
                          setPage(classroom.page + 1);
                        }}
                      >
                        <ChevronRight size={14} />
                      </button>
                    </div>
                  )}
                </div>
              )}
            </div>

            {/* 3D Hover Info Bubble (Shows when hovering over any Door, Student, or 3D Prop!) */}
            {hoverInfo && !showStationOverlay && !(student && currentStation === "classes" && activePhase === "ready") && (
              <div
                className={styles.hoverTooltip3D}
                style={{ left: `${hoverInfo.x}px`, top: `${hoverInfo.y}px` }}
                aria-hidden="true"
              >
                {hoverInfo.badge && <span className={styles.hoverTooltipBadge}>{hoverInfo.badge}</span>}
                <strong className={styles.hoverTooltipTitle}>{hoverInfo.title}</strong>
                {hoverInfo.subtitle && <span className={styles.hoverTooltipSub}>{hoverInfo.subtitle}</span>}
              </div>
            )}

            <Classroom3DScene
              seats={classroom.seats}
              selectedId={student?.id}
              station={currentStation}
              viewMode={activeViewMode}
              motion={motion && !reducedMotion}
              onSelect={(id) => {
                if (currentStation !== "classes") {
                  onStationSelect?.("classes");
                }
                setSelectedId(id);
              }}
              onStationSelect={(st) => {
                if (st === currentStation && isAtWorkStation) {
                  setDrawerPeeking3D((prev) => !prev);
                } else {
                  onStationSelect?.(st);
                }
              }}
              onStationPhaseChange={handlePhaseChange}
              stationPinRefs={stationPinRefs.current}
              onHoverChange={setHoverInfo}
              onMascot={greetMam}
              onController={receiveController}
              customizations={deskStyles}
            />

            {/* Choreography Banner while Teacher Walks to Door -> Opens Door -> Walks to Desk (or Student Desk) */}
            {((isAtWorkStation && (activePhase === "walking" || activePhase === "interacting")) ||
              (currentStation === "classes" && activePhase === "walking")) && (
              <div className={styles.choreographyBanner} role="status" aria-live="polite">
                <div className={styles.choreographyIconWrap} aria-hidden="true">
                  {activePhase === "walking" ? <DoorOpen size={20} aria-hidden="true" /> : currentStationMeta.openIcon}
                </div>
                <div className={styles.choreographyMeta}>
                  <strong>
                    {currentStation === "classes" && student
                      ? `Giáo viên đang đi bộ tới bàn của ${student.name}...`
                      : currentStation === "classes"
                      ? "Giáo viên đang mở cửa quay về Phòng Học Chính..."
                      : activePhase === "walking"
                      ? `Giáo viên đang đi tới mở cửa vào ${currentStationMeta.stationTitle}...`
                      : currentStationMeta.interactingText}
                  </strong>
                  <span>
                    {activePhase === "walking"
                      ? "Đi bộ từ vị trí ban đầu ➔ Mở cánh cửa 3D ➔ Tiến từ từ tới bàn làm việc"
                      : "Đang mở học cụ trên bàn & hiển thị khung thông tin 70% màn hình"}
                  </span>
                </div>
                <button
                  type="button"
                  className={styles.choreographySkipBtn}
                  onClick={() => controller.current?.skipStationAnimation()}
                >
                  Mở ngay ⏭
                </button>
              </div>
            )}

            {/* 70% Screen Hover/Popover Card for Specialized Room Workspace (Only after Teacher arrives at desk!) */}
            {showStationOverlay && (
              <div
                className={styles.stationOverlayBackdrop}
                onClick={(e) => {
                  if (e.target === e.currentTarget) {
                    setDrawerPeeking3D(true);
                  }
                }}
              >
                <div
                  className={styles.stationBookOverlay}
                  role="region"
                  aria-label={`Khung thông tin nổi 70%: ${currentStationMeta.label}`}
                >
                  <div className={styles.stationBookHeader}>
                    <div className={styles.stationBookTitleGroup}>
                      <div>
                        <h4 className={styles.stationBookTitle}>{currentStationMeta.label}</h4>
                      </div>
                    </div>

                    <div className={styles.stationBookActions}>
                      <button
                        type="button"
                        className={styles.stationPeek3DBtn}
                        onClick={() => setDrawerPeeking3D(true)}
                        title="Thu nội dung để xem phòng 3D"
                      >
                        <Eye size={14} aria-hidden="true" />
                        <span>Xem phòng 3D</span>
                      </button>
                      <button
                        type="button"
                        className={styles.stationCloseBookBtn}
                        onClick={() => onStationSelect?.("classes")}
                      >
                        <ArrowLeft size={14} aria-hidden="true" />
                        <span>Về lớp học</span>
                      </button>
                    </div>
                  </div>

                  <div className={styles.stationBookBody}>{stationWorkspace}</div>
                </div>
              </div>
            )}

            {/* 70% Screen Hover/Popover Card for Selected Student (Only after Teacher finishes walking to Student's Desk!) */}
            {student && selectedStyle && selectedSeat && currentStation === "classes" && activePhase === "ready" && (
              <div
                className={styles.stationOverlayBackdrop}
                onClick={(e) => {
                  if (e.target === e.currentTarget) {
                    closeInspector();
                  }
                }}
              >
                <div
                  className={styles.stationBookOverlay}
                  role="dialog"
                  aria-label="Hồ sơ học sinh được chọn"
                  onKeyDown={(event) => {
                    if (event.key === "Escape") closeInspector();
                  }}
                >
                  <div className={styles.stationBookHeader}>
                    <div className={styles.stationBookTitleGroup}>
                      <span className={styles.stationBookBadgeIcon} aria-hidden="true">
                        🎓
                      </span>
                      <div>
                        <span className={styles.stationBookEyebrow}>
                          BẠN HỌC · BÀN {selectedSeat.number} · KHUNG NỔI 70% MÀN HÌNH
                        </span>
                        <h4 className={styles.stationBookTitle}>{student.name}</h4>
                      </div>
                    </div>
                    <div className={styles.stationBookActions}>
                      <button
                        type="button"
                        className={styles.stationCloseBookBtn}
                        onClick={closeInspector}
                      >
                        <X size={14} aria-hidden="true" />
                        <span>Đóng hồ sơ · Quay lại Lớp 3D</span>
                      </button>
                    </div>
                  </div>

                  <div className={styles.stationBookBody}>
                    <div className={styles.studentPopoverGrid}>
                      <div className={styles.studentPopoverLeft}>
                        <div className={cozy.identity}>
                          <div className={cozy.portrait}>
                            <StudentPortrait id={student.id} style={selectedStyle} />
                          </div>
                          <div>
                            <h4>{student.name}</h4>
                            <p>{student.email}</p>
                            <div className={cozy.presence} data-presence={student.presence ?? "unknown"}>
                              <PresenceIcon size={12} aria-hidden="true" />
                              {presenceLabel(student)}
                            </div>
                          </div>
                        </div>

                        <div className={styles.progressGroup} style={{ marginTop: "1.25rem" }}>
                          <div>
                            <div className={styles.metricLabel}>
                              <span>Bài tập đã hoàn thành</span>
                              <strong>
                                {assignmentProgress(student) === null
                                  ? "Chưa có dữ liệu"
                                  : `${student.completedAssignments}/${student.totalAssignments}`}
                              </strong>
                            </div>
                            {assignmentProgress(student) !== null && (
                              <div
                                className={styles.track}
                                role="progressbar"
                                aria-label="Bài tập đã hoàn thành"
                                aria-valuenow={assignmentProgress(student)!}
                                aria-valuemin={0}
                                aria-valuemax={100}
                              >
                                <div className={styles.fill} style={{ width: `${assignmentProgress(student)}%` }} />
                              </div>
                            )}
                          </div>
                          <div>
                            <div className={styles.metricLabel}>
                              <span>Mức độ nắm vững</span>
                              <strong>
                                {student.overallMastery === null ? "Chưa có dữ liệu" : `${student.overallMastery}%`}
                              </strong>
                            </div>
                            {student.overallMastery !== null && (
                              <div
                                className={styles.track}
                                role="progressbar"
                                aria-label="Mức độ nắm vững"
                                aria-valuenow={student.overallMastery}
                                aria-valuemin={0}
                                aria-valuemax={100}
                              >
                                <div className={styles.fill} style={{ width: `${student.overallMastery}%` }} />
                              </div>
                            )}
                          </div>
                          <div className={styles.secondary}>
                            {ACTIVITY_LABELS[classroomActivity(student)]}
                            {student.latestActivityAt ? ` · ${student.latestActivityAt}` : ""}
                          </div>
                        </div>

                        <div style={{ marginTop: "1.25rem" }}>
                          {student.helpRequest ? (
                            <div className={cozy.request}>
                              <strong>
                                <Hand size={14} aria-hidden="true" />
                                Yêu cầu hỗ trợ
                              </strong>
                              {student.helpRequest.message}
                            </div>
                          ) : (
                            <div>
                              <p className={cozy.sectionLabel}>Nội dung cần củng cố</p>
                              {student.weakTopics.length ? (
                                <ul className={cozy.topics}>
                                  {student.weakTopics.map((topic) => (
                                    <li key={topic}>{topic}</li>
                                  ))}
                                </ul>
                              ) : (
                                <div className={styles.secondary}>Chưa có dữ liệu nội dung cần củng cố.</div>
                              )}
                            </div>
                          )}
                          <button
                            type="button"
                            disabled={!onViewStudentWorkspace}
                            className={`${cozy.primaryButton} ${cozy.openWork}`}
                            style={{ marginTop: "1rem" }}
                            onClick={() => onViewStudentWorkspace?.(student.id)}
                          >
                            <ExternalLink size={14} aria-hidden="true" />
                            {isDemo
                              ? "Bài làm minh họa chưa kết nối"
                              : student.helpRequest
                              ? "Xem bài làm để hỗ trợ"
                              : "Xem bài làm chi tiết"}
                          </button>
                        </div>
                      </div>

                      <div className={styles.studentPopoverRight}>
                        <DeskStyleEditor value={selectedStyle} onChange={changeStyle} saved={saved} />
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            )}

            {celebrating && (
              <div className={cozy.celebration} aria-hidden="true" data-celebration="active" key={celebrationKey}>
                <span className={cozy.celebrationMessage}>Một tràng vỗ tay cho lớp mình! ✦</span>
                {motion &&
                  !reducedMotion &&
                  Array.from({ length: 24 }, (_, index) => (
                    <i
                      className={cozy.confetti}
                      key={index}
                      style={
                        {
                          "--x": `${4 + ((index * 13) % 92)}%`,
                          "--size": `${7 + (index % 5)}px`,
                          "--color": ["#aac9a2", "#c9b8e3", "#ecc28e", "#a7cbd7"][index % 4],
                          "--delay": `${(index % 6) * 50}ms`,
                        } as CSSProperties
                      }
                    />
                  ))}
              </div>
            )}
          </div>
        </div>
      </div>

      {momentOpen && (
        <ClassroomMomentDialog
          isDemo={isDemo}
          snapshot={snapshot}
          students={students}
          classroomName={classroomName}
          onClose={closeMoment}
          onCelebrate={celebrate}
        />
      )}
    </section>
  );
}
