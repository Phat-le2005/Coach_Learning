"use client";
import { useState, type ReactNode } from "react";
import { Check, ChevronDown, Maximize2, Minimize2, Minus, Move, Plus, RotateCcw, RotateCw, Scan, SlidersHorizontal } from "lucide-react";
import type { GraphCameraPreset } from "./camera-presets";
import styles from "./MathCanvas.module.css";

interface Props {
  dimension:"2D"|"3D"; disabled:boolean; onZoom:(factor:number)=>void; onFit:()=>void; onReset:()=>void;
  expanded?:boolean; onExpand?:()=>void; dragMode?:"rotate"|"pan"; onDragMode?:(mode:"rotate"|"pan")=>void;
  preset?:GraphCameraPreset|null; onPreset?:(preset:GraphCameraPreset)=>void; children:ReactNode;
}
export function ScenePlotToolbar({dimension,disabled,onZoom,onFit,onReset,expanded,onExpand,dragMode,onDragMode,preset,onPreset,children}:Props){
  const [settingsOpen,setSettingsOpen]=useState(false);
  return <div className={styles.plotControls}>
    <div className={styles.plotToolbar} role="group" aria-label={`Điều khiển đồ thị ${dimension}`}>
      {onDragMode?<div className={styles.plotToolGroup} aria-label="Thao tác kéo">
        <button type="button" aria-pressed={dragMode==="rotate"} onClick={()=>onDragMode("rotate")} disabled={disabled}><RotateCw size={15}/><span>Xoay</span></button>
        <button type="button" aria-pressed={dragMode==="pan"} onClick={()=>onDragMode("pan")} disabled={disabled}><Move size={15}/><span>Di chuyển</span></button>
      </div>:<span className={styles.plotPanHint}><Move size={15}/> Kéo để di chuyển</span>}
      <div className={styles.plotZoomGroup} aria-label="Thu phóng">
        <button type="button" aria-label={`Thu nhỏ đồ thị ${dimension}`} title="Thu nhỏ" disabled={disabled} onClick={()=>onZoom(.8)}><Minus size={17}/></button>
        <button type="button" aria-label={`Phóng to đồ thị ${dimension}`} title="Phóng to" disabled={disabled} onClick={()=>onZoom(1.25)}><Plus size={17}/></button>
      </div>
      <button type="button" className={styles.plotFit} disabled={disabled} onClick={onFit} title="Căn đồ thị vừa khung"><Scan size={16}/><span>Vừa hình</span></button>
      <button type="button" className={styles.plotIconButton} disabled={disabled} onClick={onReset} aria-label="Đặt lại góc nhìn" title="Đặt lại góc nhìn"><RotateCcw size={16}/></button>
      <div className={styles.plotToolbarEnd}>
        <button type="button" aria-label="Tùy chỉnh đồ thị" title="Tùy chỉnh đồ thị" aria-expanded={settingsOpen} onClick={()=>setSettingsOpen(!settingsOpen)} className={styles.plotSettingsToggle}><SlidersHorizontal size={15}/><span>Tùy chỉnh</span><ChevronDown size={13}/></button>
        {onExpand?<button type="button" className={styles.plotIconButton} aria-pressed={!!expanded} aria-label={expanded?"Thu gọn đồ thị":"Mở rộng đồ thị"} title={expanded?"Thu gọn đồ thị":"Mở rộng đồ thị"} onClick={onExpand}>{expanded?<Minimize2 size={16}/>:<Maximize2 size={16}/>}</button>:null}
      </div>
    </div>
    {settingsOpen?<div className={styles.plotSettings}>
      {onPreset?<label className={styles.plotPresetLabel}>Góc nhìn<select aria-label="Góc nhìn đồ thị 3D" value={preset??"CUSTOM"} disabled={disabled} onChange={(event)=>onPreset(event.target.value as GraphCameraPreset)}><option value="CUSTOM" disabled>Góc nhìn tự do</option><option value="PERSPECTIVE">Phối cảnh</option><option value="OXY">Nhìn từ mặt Oxy</option><option value="OXZ">Nhìn từ mặt Oxz</option><option value="OYZ">Nhìn từ mặt Oyz</option></select></label>:null}
      <div className={styles.plotSettingItems}>{children}</div>
      <p><Check size={12}/> Thay đổi được áp dụng ngay trên đồ thị.</p>
    </div>:null}
  </div>;
}
