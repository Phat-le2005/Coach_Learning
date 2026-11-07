"use client";
import { Eraser, Highlighter, Pen, Redo2, Undo2 } from "lucide-react";
import type { DrawingTool } from "../types";
import styles from "./writing.module.css";

export function WritingToolbar(props: {tool: DrawingTool; onTool: (tool: DrawingTool) => void; color: string; onColor: (color: string) => void;
  canUndo: boolean; canRedo: boolean; onUndo: () => void; onRedo: () => void; disabled?: boolean}) {
  return <div className={styles.compactToolbar} role="toolbar" aria-label="Công cụ viết cảm ứng">
    <button type="button" disabled={props.disabled} onClick={() => props.onTool("pen")} aria-pressed={props.tool === "pen"} aria-label="Bút" title="Bút viết"><Pen size={19}/>Bút</button>
    <button type="button" disabled={props.disabled} onClick={() => props.onTool("highlighter")} aria-pressed={props.tool === "highlighter"} aria-label="Đánh dấu" title="Đánh dấu"><Highlighter size={19}/></button>
    <button type="button" disabled={props.disabled} onClick={() => props.onTool("eraser")} aria-pressed={props.tool === "eraser"} aria-label="Tẩy" title="Tẩy nét"><Eraser size={19}/></button>
    <span className={styles.toolSeparator}/>
    {["#233c30", "#346cbd", "#bd5650"].map(color => <button type="button" key={color} aria-label={`Màu ${color}`} aria-pressed={props.color === color} onClick={() => props.onColor(color)}><span className={styles.toolColor} style={{background: color}}/></button>)}
    <span className={styles.toolSeparator}/>
    <button type="button" aria-label="Hoàn tác" disabled={props.disabled || !props.canUndo} onClick={props.onUndo}><Undo2 size={19}/></button>
    <button type="button" aria-label="Làm lại" disabled={props.disabled || !props.canRedo} onClick={props.onRedo}><Redo2 size={19}/></button>
  </div>;
}
