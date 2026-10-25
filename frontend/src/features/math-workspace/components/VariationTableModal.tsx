"use client";

import React, { useEffect, useRef, useState, type KeyboardEvent } from "react";
import type { VariationTablePayload, VariationTablePoint } from "@/lib/api/contracts";
import { ApiNetworkError, ApiResponseError } from "@/lib/api/client";
import { generateUuid } from "../utils/ink-math";
import {
  addVariationPoint, createVariationTableDraft, removeVariationPoint,
  toVariationTablePayload, trendForSign, validateVariationTable,
  type DraftSign, type VariationTableDraft,
} from "../utils/variation-table";
import styles from "../MathWorkspace.module.css";

interface GridProps {
  value: VariationTableDraft;
  onChange?: (value: VariationTableDraft) => void;
  disabled?: boolean;
}

function TrendArrow({ trend, empty }: { trend: VariationTableDraft["intervals"][number]["trend"]; empty: boolean }) {
  if (empty) return <span className={styles.variationUnknown} aria-hidden="true" />;
  if (trend === "UNKNOWN") return <span className={styles.variationUnknown}>?</span>;
  const path = trend === "UP" ? "M8 44 C34 37 62 16 90 7"
    : trend === "DOWN" ? "M8 7 C34 16 62 37 90 44" : "M8 25 L90 25";
  const tip = trend === "UP" ? "90,7 79,11 86,19"
    : trend === "DOWN" ? "90,44 79,33 84,30" : "90,25 80,18 80,32";
  return <svg className={styles.variationArrow} viewBox="0 0 100 50" role="img"
    aria-label={trend === "UP" ? "Hàm số tăng" : trend === "DOWN" ? "Hàm số giảm" : "Hàm số không đổi"}>
    <path d={path} fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
    <polygon points={tip} fill="currentColor" />
  </svg>;
}

export function VariationTableGrid({ value, onChange, disabled = false }: GridProps) {
  const editable = Boolean(onChange);
  const updatePoint = (index: number, patch: Partial<VariationTablePoint>) => {
    if (!onChange) return;
    onChange({ ...value, points: value.points.map((point, offset) =>
      offset === index ? { ...point, ...patch } : point) });
  };
  const updateSign = (index: number, sign: DraftSign) => {
    if (!onChange) return;
    onChange({ ...value, intervals: value.intervals.map((interval, offset) =>
      offset === index ? { sign, trend: trendForSign(sign) } : interval) });
  };
  return <div className={styles.variationTableScroll}>
    <table className={styles.variationTable} aria-label="Bảng biến thiên của học sinh">
      <tbody>
        <tr>
          <th scope="row">x</th>
          {value.points.map((point, index) => <React.Fragment key={index}>
            <td className={styles.variationPointCell}>
              {editable ? <input disabled={disabled} value={point.x} onChange={(event) => updatePoint(index, { x: event.target.value })}
                aria-label={`Mốc x thứ ${index + 1}`} placeholder={index === 0 ? "−∞" : index === value.points.length - 1 ? "+∞" : "x"} maxLength={80} />
                : <span>{point.x}</span>}
            </td>
            {index < value.intervals.length ? <td className={styles.variationIntervalCell} /> : null}
          </React.Fragment>)}
        </tr>
        <tr>
          <th scope="row">y′</th>
          {value.points.map((point, index) => <React.Fragment key={index}>
            <td className={styles.variationPointCell}>
              {editable ? <select disabled={disabled} value={point.derivative} onChange={(event) =>
                updatePoint(index, { derivative: event.target.value as VariationTablePoint["derivative"] })}
                aria-label={`Đạo hàm tại mốc x thứ ${index + 1}`}>
                <option value="">—</option><option value="0">0</option>
                <option value="undefined">KXD</option><option value="?">?</option>
              </select> : <span>{point.derivative === "undefined" ? "KXD" : point.derivative}</span>}
            </td>
            {index < value.intervals.length ? <td className={styles.variationIntervalCell}>
              {editable ? <select disabled={disabled} value={value.intervals[index].sign}
                onChange={(event) => updateSign(index, event.target.value as DraftSign)}
                aria-label={`Dấu đạo hàm trên khoảng thứ ${index + 1}`}>
                <option value="">Chọn dấu</option><option value="+">+</option>
                <option value="-">−</option><option value="0">0</option><option value="?">?</option>
              </select> : <strong>{value.intervals[index].sign}</strong>}
            </td> : null}
          </React.Fragment>)}
        </tr>
        <tr>
          <th scope="row">y</th>
          {value.points.map((point, index) => <React.Fragment key={index}>
            <td className={styles.variationPointCell}>
              {editable ? <input disabled={disabled} value={point.y} onChange={(event) => updatePoint(index, { y: event.target.value })}
                aria-label={`Giá trị y tại mốc x thứ ${index + 1}`} placeholder="Giá trị" maxLength={80} />
                : <span>{point.y}</span>}
            </td>
            {index < value.intervals.length ? <td className={styles.variationIntervalCell}>
              <TrendArrow trend={value.intervals[index].trend} empty={value.intervals[index].sign === ""} />
            </td> : null}
          </React.Fragment>)}
        </tr>
      </tbody>
    </table>
  </div>;
}

interface ModalProps {
  initial?: VariationTablePayload;
  onSave: (payload: VariationTablePayload, actionId: string) => Promise<void>;
  onClose: () => void;
}

export function VariationTableModal({ initial, onSave, onClose }: ModalProps) {
  const [draft, setDraft] = useState<VariationTableDraft>(() => initial
    ? { points: initial.points.map((point) => ({ ...point })),
        intervals: initial.intervals.map((interval) => ({ ...interval })) }
    : createVariationTableDraft());
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const actionId = useRef(generateUuid()).current;
  const dialogRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const previous = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    dialogRef.current?.querySelector<HTMLInputElement>("input")?.focus();
    return () => previous?.focus();
  }, []);

  const close = () => {
    if (saving) return;
    if (dirty && !window.confirm("Bảng chưa lưu sẽ mất phần đã nhập. Đóng bảng?")) return;
    onClose();
  };
  const handleKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key === "Escape") { event.preventDefault(); close(); }
    if (event.key !== "Tab") return;
    const focusable = Array.from(dialogRef.current?.querySelectorAll<HTMLElement>(
      "button:not(:disabled), input:not(:disabled), select:not(:disabled)") ?? []);
    const first = focusable[0], last = focusable[focusable.length - 1];
    if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
    else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
  };
  const save = async () => {
    if (saving) return;
    const problem = validateVariationTable(draft);
    if (problem) {
      setError(problem === "TABLE_X_REQUIRED_OR_DUPLICATE"
        ? "Điền các mốc x khác nhau, không để trống."
        : problem === "TABLE_SIGNS_REQUIRED"
          ? "Chọn dấu y′ cho mỗi khoảng để hệ thống tự vẽ mũi tên."
          : "Các cột của bảng chưa hợp lệ. Hãy kiểm tra lại.");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await onSave(toVariationTablePayload(draft), actionId);
      onClose();
    } catch (caught: unknown) {
      setError(caught instanceof ApiNetworkError || (caught instanceof ApiResponseError && caught.status >= 500)
        ? "Chưa nhận được kết quả lưu. Giữ nguyên bảng và bấm Lưu lại; hệ thống sẽ kiểm tra thao tác cũ."
        : caught instanceof ApiResponseError && caught.status === 409
          ? "Bài làm đã thay đổi ở nơi khác. Tải lại trang để kiểm tra trước khi sửa tiếp."
          : caught instanceof ApiResponseError && caught.status === 401
            ? "Phiên đăng nhập đã hết hạn. Đăng nhập lại ở tab khác rồi lưu tiếp."
            : caught instanceof Error ? caught.message : "Không thể lưu bảng biến thiên.");
    } finally { setSaving(false); }
  };

  return <div ref={dialogRef} className={styles.modalOverlay} role="dialog" aria-modal="true"
    aria-labelledby="variation-table-title" onKeyDown={handleKeyDown}>
    <div className={styles.variationModal}>
      <header className={styles.variationHeader}>
        <div>
          <h2 id="variation-table-title">Bảng biến thiên</h2>
          <p>Điền các mốc x, dấu y′ và giá trị y. Mũi tên tăng/giảm được vẽ từ dấu y′ em chọn.</p>
        </div>
        <button type="button" className={styles.buttonSecondary} onClick={close} disabled={saving}>Đóng</button>
      </header>
      <div className={styles.variationBody}>
        <p className={styles.pageReviewNotice}>Đây là bước giải do em nhập, chưa được tự chấm. Ô y có thể để trống nếu chưa xác định.</p>
        <VariationTableGrid value={draft} disabled={saving} onChange={(next) => { setDraft(next); setDirty(true); setError(null); }} />
        <div className={styles.variationControls}>
          <button type="button" className={styles.buttonSecondary} onClick={() => { setDraft(addVariationPoint(draft)); setDirty(true); }}
            disabled={saving || draft.points.length >= 12}>+ Thêm mốc x</button>
          <button type="button" className={styles.buttonSecondary} onClick={() => { setDraft(removeVariationPoint(draft)); setDirty(true); }}
            disabled={saving || draft.points.length <= 2}>Bớt mốc x</button>
        </div>
        {error ? <p className={styles.ocrErrorBanner} role="alert">{error}</p> : null}
      </div>
      <footer className={styles.variationFooter}>
        <button type="button" className={styles.buttonSecondary} onClick={close} disabled={saving}>Hủy</button>
        <button type="button" className={styles.buttonPrimary} onClick={() => void save()} disabled={saving}>
          {saving ? "Đang lưu..." : initial ? "Lưu chỉnh sửa" : "Lưu bảng vào bài làm"}
        </button>
      </footer>
    </div>
  </div>;
}
