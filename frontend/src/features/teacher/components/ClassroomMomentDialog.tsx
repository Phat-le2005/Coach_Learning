"use client";

import { useEffect, useId, useMemo, useRef, useState } from "react";
import { Download, LoaderCircle, PartyPopper, Sprout, X } from "lucide-react";
import { classMomentSummary } from "../classroom-personalization";
import { renderClassroomMoment, renderMamSticker, type MomentFormat } from "../classroom-moment";
import type { ClassroomStudentInfo } from "../classroom-types";
import { MamMascot } from "./MamMascot";
import cozy from "../CozyCampus.module.css";

interface Props { isDemo: boolean; snapshot: string | null; students: ClassroomStudentInfo[]; classroomName: string; onClose: () => void; onCelebrate: () => void }

export function ClassroomMomentDialog({ snapshot, students, classroomName, isDemo, onClose, onCelebrate }: Props) {
  const dialog = useRef<HTMLDialogElement>(null);
  const title = useId();
  const [format, setFormat] = useState<MomentFormat>("post");
  const [showClassName, setShowClassName] = useState(false);
  const [rendered, setRendered] = useState<Awaited<ReturnType<typeof renderClassroomMoment>> | null>(null);
  const [error, setError] = useState("");
  const [stickerBusy, setStickerBusy] = useState(false);
  const [stickerError, setStickerError] = useState("");
  const summary = useMemo(() => classMomentSummary(students, classroomName, showClassName, isDemo), [students, classroomName, showClassName, isDemo]);

  useEffect(() => {
    const element = dialog.current; element?.showModal();
    const oldOverflow = document.body.style.overflow; document.body.style.overflow = "hidden";
    return () => { document.body.style.overflow = oldOverflow; element?.close(); };
  }, []);
  useEffect(() => {
    let canceled = false; setRendered(null); setError("");
    renderClassroomMoment(snapshot, summary, format).then((result) => { if (!canceled) setRendered(result); }).catch(() => { if (!canceled) setError("Chưa tạo được ảnh. Bạn thử lại nhé."); });
    return () => { canceled = true; };
  }, [snapshot, summary, format]);

  function download() {
    if (!rendered) return;
    const url = URL.createObjectURL(rendered.blob);
    const date = new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Ho_Chi_Minh", year: "numeric", month: "2-digit", day: "2-digit" }).format(new Date());
    const link = document.createElement("a"); link.href = url; link.download = `lop-minh-${format}-${date}.png`; link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  async function downloadSticker() {
    setStickerBusy(true); setStickerError("");
    try {
      const blob = await renderMamSticker();
      const url = URL.createObjectURL(blob); const link = document.createElement("a");
      link.href = url; link.download = "mam-sticker.png"; link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch { setStickerError("Chưa tạo được sticker. Bạn thử lại nhé."); }
    finally { setStickerBusy(false); }
  }

  return <dialog ref={dialog} className={cozy.momentDialog} aria-labelledby={title} onCancel={onClose} onClick={(event) => { if (event.target === event.currentTarget) onClose(); }}>
    <div className={cozy.dialogHeader}><div><span className={cozy.eyebrow}>MỘT CHÚT TIẾN BỘ, MỘT KHOẢNH KHẮC ĐẸP</span><h2 id={title}>Khoảnh khắc lớp mình</h2></div><button type="button" aria-label="Đóng khoảnh khắc" className={cozy.iconButton} onClick={onClose}><X size={20} /></button></div>
    <div className={cozy.momentLayout}>
      <div className={cozy.momentPreview}>{rendered ? <img src={rendered.dataUrl} alt="Thẻ Lớp mình hôm nay, không hiển thị tên và email học sinh" width={rendered.width} height={rendered.height} /> : <div className={cozy.previewLoading} role="status">{error || <><LoaderCircle size={22} aria-hidden="true" />Đang giữ lại khoảnh khắc…</>}</div>}</div>
      <div className={cozy.momentOptions}>
        <div className={cozy.mamCard}><MamMascot /><p>Mỗi bạn một nhịp.<br /><strong>Cả lớp cùng tiến bộ.</strong></p></div>
        <span className={cozy.fieldLabel}>Khung ảnh chia sẻ</span><div className={cozy.decorationOptions} role="group" aria-label="Định dạng ảnh"><button type="button" aria-pressed={format === "post"} onClick={() => setFormat("post")}>Bài đăng · 4:5</button><button type="button" aria-pressed={format === "story"} onClick={() => setFormat("story")}>Story · 9:16</button></div>
        <label className={cozy.glassesToggle}><input type="checkbox" checked={showClassName} onChange={(event) => setShowClassName(event.target.checked)} />Hiển thị tên lớp trên ảnh</label>
        <p className={cozy.storageNote}>Tên và email học sinh luôn được ẩn. {summary.hasProgress ? "Số liệu lấy từ tiến độ bài tập hiện có." : "Chưa có dữ liệu tiến độ từng học sinh."}</p>
        <button type="button" className={cozy.primaryButton} disabled={!rendered} onClick={download}><Download size={16} aria-hidden="true" />Tải ảnh PNG</button>
        <button type="button" className={cozy.secondaryButton} disabled={stickerBusy} onClick={downloadSticker}><Sprout size={16} aria-hidden="true" />{stickerBusy ? "Đang tạo sticker…" : "Tải sticker Mầm"}</button>
        {stickerError && <p className={cozy.storageNote} role="status">{stickerError}</p>}
        <button type="button" className={cozy.secondaryButton} onClick={() => { onClose(); onCelebrate(); }}><PartyPopper size={16} aria-hidden="true" />Xem thử ăn mừng trên lớp</button>
      </div>
    </div>
  </dialog>;
}
