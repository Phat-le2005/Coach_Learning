"use client";

import { Minus, Sprout, Star } from "lucide-react";
import type { CSSProperties } from "react";
import { BAG_COLORS, type DeskDecoration, type DeskStyle } from "../classroom-personalization";
import cozy from "../CozyCampus.module.css";

export function DeskStyleEditor({ value, onChange, saved }: { value: DeskStyle; onChange: (next: DeskStyle) => void; saved: boolean }) {
  const decorations: { value: DeskDecoration; label: string; Icon: typeof Sprout }[] = [
    { value: "plant", label: "Chậu cây", Icon: Sprout }, { value: "star", label: "Ngôi sao", Icon: Star }, { value: "none", label: "Gọn gàng", Icon: Minus },
  ];
  return <fieldset className={cozy.styleEditor}><legend>Trang trí góc bàn</legend>
    <span className={cozy.fieldLabel}>Màu cặp sách</span>
    <div className={cozy.swatches} role="group" aria-label="Màu cặp sách">{Object.entries(BAG_COLORS).map(([key, color]) => <button type="button" key={key} className={cozy.swatch} style={{ "--swatch-color": color.hex } as CSSProperties} aria-label={color.label} aria-pressed={value.bagColor === key} onClick={() => onChange({ ...value, bagColor: key as DeskStyle["bagColor"] })}><span />{color.label}</button>)}</div>
    <span className={cozy.fieldLabel}>Một chút cá tính</span>
    <div className={cozy.decorationOptions} role="group" aria-label="Đồ trang trí bàn">{decorations.map(({ value: decoration, label, Icon }) => <button key={decoration} type="button" aria-pressed={value.decoration === decoration} onClick={() => onChange({ ...value, decoration })}><Icon size={15} aria-hidden="true" />{label}</button>)}</div>
    <label className={cozy.glassesToggle}><input type="checkbox" checked={value.glasses} onChange={(event) => onChange({ ...value, glasses: event.target.checked })} />Đeo kính cho bạn học</label>
    <p className={cozy.storageNote} role="status">{saved ? "Lựa chọn được lưu trên trình duyệt này." : "Đang áp dụng trên lớp học."}</p>
  </fieldset>;
}
