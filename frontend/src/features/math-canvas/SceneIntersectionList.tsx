"use client";
import type { CompiledScene } from "./scene";
import type { SceneDrawing } from "./scene-geometry";
import styles from "./MathCanvas.module.css";

export function SceneIntersectionList({scene,drawing,ready,onFocus}:{scene:CompiledScene;drawing:SceneDrawing|null;ready:boolean;onFocus:(point:[number,number])=>void}){
  if(!ready||!drawing||scene.layers.filter((layer)=>layer.visible&&layer.relations.length===1&&layer.relations[0].operator==="=").length<2)return null;
  return <section className={styles.intersectionPanel} aria-label="Giao điểm các đồ thị"><strong>Giao điểm gần đúng ({drawing.intersections.length})</strong>
    {drawing.intersections.length?<div className={styles.intersectionPoints}>{drawing.intersections.map((point,index)=><button type="button" className={styles.button} key={index} onClick={()=>onFocus(point)}>{`P${index+1} (${point[0].toFixed(3)}; ${point[1].toFixed(3)})`}</button>)}</div>:<p>Chưa tìm thấy giao điểm trong miền đang chọn. Thử tăng miền khảo sát; kết quả lấy mẫu chưa khẳng định hệ vô nghiệm.</p>}
    <p>Các điểm được tìm bằng lấy mẫu; tiếp xúc hoặc chi tiết nhỏ có thể chưa được phát hiện.</p>
  </section>;
}
