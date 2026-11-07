"use client";
import { useEffect, useRef, useState } from "react";
import { Check, ChevronLeft, ChevronRight, Laptop, LoaderCircle, LockKeyhole, Smartphone } from "lucide-react";
import { MathCanvas } from "../components/MathCanvas";
import type { DrawingTool, InkStroke } from "../types";
import { deviceRequest, type DevicePairing } from "./device-client";
import { useLiveInk } from "./useLiveInk";
import { WritingToolbar } from "./WritingToolbar";
import styles from "./writing.module.css";

export function DeviceWriter() {
  const [session, setSession] = useState<DevicePairing | null>(null);
  const [error, setError] = useState("");
  const [ended, setEnded] = useState(false);
  const startup = useRef<Promise<DevicePairing> | null>(null);
  useEffect(() => {
    let alive = true; let polling = false;
    const parameters = new URLSearchParams(window.location.hash.slice(1));
    const code = parameters.get("code");
    // Invitation stays out of server/referrer logs and is removed immediately.
    if (window.location.hash) window.history.replaceState(null, "", window.location.pathname);
    const poll = async () => {
      if (polling) return; polling = true;
      try {const value = await deviceRequest<DevicePairing>("/api/ink-device/session"); if (alive) {setSession(value); setError("");}}
      catch (failure) {if (alive) {
        setError(failure instanceof Error ? failure.message : "Chưa kết nối được.");
        // A network hiccup must not unmount an active canvas or discard a partial stroke.
        if ([401, 403, 409, 410].includes((failure as {status?: number}).status ?? 0)) setSession(null);
      }}
      finally {polling = false;}
    };
    if (!startup.current) {
      if (code) {
          const agent = navigator.userAgent;
          const name = /iPad|Macintosh/.test(agent) && navigator.maxTouchPoints > 1 ? "iPad" : /iPhone/.test(agent) ? "iPhone" : /Android/.test(agent) ? "Điện thoại Android" : "Thiết bị viết";
          startup.current = deviceRequest<DevicePairing>("/api/ink-device/claim", {code, device_name: name});
      } else startup.current = deviceRequest<DevicePairing>("/api/ink-device/session");
    }
    void startup.current.then(value => {if (alive) setSession(value);}).catch(failure => {if (alive) setError(failure instanceof Error ? failure.message : "Mã kết nối không còn hiệu lực.");});
    const timer = setInterval(() => void poll(), 2500);
    return () => {alive = false; clearInterval(timer);};
  }, []);
  if (session?.status === "ACTIVE" && !ended) return <ConnectedWriter session={session} onEnd={() => setEnded(true)}/>;
  return <main className={styles.waitingPage}><div className={styles.waitingCard}>
    <div className={styles.deviceIllustration}><Smartphone size={32}/><span/><Laptop size={32}/></div>
    <h1>{ended ? "Đã kết thúc phiên viết" : session?.status === "PENDING" ? "Chỉ còn một bước nữa" : error ? "Chưa thể kết nối" : "Đang kết nối với máy tính"}</h1>
    {session?.status === "PENDING" ? <><p>Trên máy tính, nhấn <strong>Cho phép viết</strong> khi thấy mã này.</p><strong className={styles.confirmationCode}>{session.confirmation}</strong><p>Không cần đăng nhập trên thiết bị này.</p></>
      : ended ? <p>Nét viết đã được lưu. Bạn có thể tiếp tục làm bài trên máy tính.</p>
      : error ? <p role="alert">{error}</p> : <LoaderCircle className={styles.spin} size={26}/>}
    <p className={styles.privacy}><LockKeyhole size={15}/>Thiết bị chỉ được viết vào bài đã kết nối.</p>
  </div></main>;
}

function ConnectedWriter({session, onEnd}: {session: DevicePairing; onEnd: () => void}) {
  const [page, setPage] = useState(session.page_index);
  const [pageCount, setPageCount] = useState(Math.max(session.page_count ?? 1, session.page_index + 1));
  const [strokes, setStrokes] = useState<InkStroke[]>([]);
  const [tool, setTool] = useState<DrawingTool>("pen");
  const [color, setColor] = useState("#233c30");
  const [drawing, setDrawing] = useState(false);
  const [error, setError] = useState("");
  const live = useLiveInk({attemptId: session.attempt_id, pageIndex: page, enabled: true, apiBase: "/api/ink-device/ink",
    onSnapshot: snapshot => setStrokes(snapshot.strokes), onPageAvailable: index => setPageCount(n => Math.max(n, index + 1))});
  const navigate = async (next: number) => {if (!drawing && next >= 0 && next < 30 && await live.flush()) {setStrokes([]); setPage(next); setPageCount(n => Math.max(n, next + 1));}};
  const finish = async () => {
    if (drawing) return;
    if (!await live.flush()) {setError("Vẫn đang lưu nét viết. Giữ trang này mở và thử lại khi có mạng."); return;}
    try {await deviceRequest("/api/ink-device/disconnect", {}); onEnd();} catch (failure) {setError(failure instanceof Error ? failure.message : "Chưa ngắt được kết nối.");}
  };
  const status = live.pendingCount ? "Đang lưu nét viết…" : live.status === "connected" ? "Đã kết nối · Đã lưu" : live.status === "offline" ? "Mất mạng · Nét viết được giữ trên thiết bị" : "Đang kết nối lại…";
  return <main className={styles.writer}>
    <header className={styles.writerHeader}><div><strong>Bảng viết của bạn</strong><small data-live-status={live.status} data-pending={live.pendingCount}>{live.status === "connected" ? <Check size={12}/> : <LoaderCircle size={12} className={styles.spin}/>} {status}</small></div>
      <button type="button" className={styles.textButton} disabled={drawing} onClick={() => void finish()}>Kết thúc</button></header>
    <WritingToolbar tool={tool} onTool={setTool} color={color} onColor={setColor} canUndo={live.canUndo} canRedo={live.canRedo} onUndo={live.undo} onRedo={live.redo} disabled={!live.initialized}/>
    {error || live.error ? <p role="alert" className={styles.error}>{error || live.error}</p> : null}
    <section className={styles.writerPaper} aria-label="Bảng viết cảm ứng"><MathCanvas strokes={strokes} onStrokesChange={(next, observed) => live.change(next, observed ?? strokes)} currentTool={tool} penColor={color} penWidth={2.5} highlighterWidth={16} paperGrid="grid" zoomLevel={1}
      responsive isReadOnly={!live.initialized} remoteDrafts={live.drafts} onLiveStroke={live.stream} onDrawingStateChange={setDrawing}/></section>
    <nav className={styles.writerPage} aria-label="Điều hướng trang viết"><button type="button" disabled={page === 0 || drawing} onClick={() => void navigate(page - 1)} aria-label="Trang trước"><ChevronLeft size={16}/></button>
      <span>Trang {page + 1} / {pageCount}</span><button type="button" disabled={page === 29 || drawing} onClick={() => void navigate(page + 1)} aria-label={page === pageCount - 1 ? "Thêm trang" : "Trang sau"}><ChevronRight size={16}/></button></nav>
  </main>;
}
