"use client";

import { useEffect, useId, useRef, useState } from "react";
import { RotateCcw } from "lucide-react";
import styles from "./MathCanvas.module.css";

interface Props {
  label: string;
  value: number;
  onChange: (value: number) => void;
  min?: number;
  max?: number;
  step?: number;
  defaultValue?: number;
  disabled?: boolean;
  onInteraction?: () => void;
}

/** Keep incomplete numeric edits local; only finite, bounded values reach geometry. */
export function GraphValueControl({ label, value, onChange, min = -5, max = 5, step = 0.1, defaultValue = 0, disabled, onInteraction }: Props) {
  const id = useId();
  const [draft, setDraft] = useState(value.toFixed(2));
  const editing = useRef(false);
  useEffect(() => { if (!editing.current) setDraft(value.toFixed(2)); }, [value]);

  function commit() {
    const parsed = draft.trim() ? Number(draft) : NaN;
    const next = Number.isFinite(parsed) ? Math.min(max, Math.max(min, parsed)) : value;
    setDraft(next.toFixed(2));
    if (next !== value) onChange(next);
  }

  return <div className={styles.valueControl}>
    <div className={styles.valueControlHeading}>
      <label htmlFor={id}>{label}</label>
      <div className={styles.valueEntry}>
        <input id={id} type="number" aria-label={`Giá trị ${label.toLowerCase()}`} inputMode="decimal" min={min} max={max} step={step}
          value={draft} disabled={disabled} onFocus={() => { editing.current = true; onInteraction?.(); }} onChange={(event) => {
            const text = event.target.value;
            setDraft(text);
            const next = text.trim() ? Number(text) : NaN;
            if (Number.isFinite(next) && next >= min && next <= max) onChange(next);
          }} onBlur={() => { editing.current = false; commit(); }} onKeyDown={(event) => {
            if (event.key === "Enter") { event.preventDefault(); event.currentTarget.blur(); }
            if (event.key === "Escape") { event.preventDefault(); setDraft(value.toFixed(2)); }
          }} />
        <button type="button" aria-label={`Đặt lại ${label.toLowerCase()}`} title={`Đặt lại: ${defaultValue}`} disabled={disabled || value === defaultValue}
          onClick={() => { onInteraction?.(); setDraft(defaultValue.toFixed(2)); onChange(defaultValue); }}><RotateCcw size={13} /></button>
      </div>
    </div>
    <input type="range" aria-label={label} min={min} max={max} step={step} value={value} disabled={disabled}
      onPointerDown={onInteraction} onChange={(event) => { onInteraction?.(); onChange(Number(event.target.value)); }} />
    <div className={styles.valueBounds} aria-hidden="true"><span>{min}</span><span>{max}</span></div>
  </div>;
}
