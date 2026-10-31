"use client";
import { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { defaultCamera, type GraphCamera } from "./expression";
import { fitGraphCamera, type GraphBounds } from "./fit-camera";
import type { LabDocument } from "./lab-spec";
import type { LabDrawing } from "./lab-geometry";
import styles from "./MathCanvas.module.css";

interface Props { document: LabDocument; parameters: Record<string, number>; domain: number; initialCamera?: GraphCamera; onCameraChange?: (camera: GraphCamera) => void }
type Camera = THREE.PerspectiveCamera | THREE.OrthographicCamera;
function dispose(group: THREE.Object3D) {
  group.traverse((object) => {
    if (object instanceof THREE.Mesh || object instanceof THREE.Line || object instanceof THREE.Sprite) {
      if ("geometry" in object) object.geometry.dispose();
      for (const material of Array.isArray(object.material) ? object.material : [object.material]) { if ("map" in material && material.map instanceof THREE.Texture) material.map.dispose(); material.dispose(); }
    }
  });
}
function textSprite(text: string, color: string, point: THREE.Vector3) {
  const canvas = document.createElement("canvas"); canvas.width = 256; canvas.height = 64;
  const context = canvas.getContext("2d")!; context.font = "600 25px system-ui"; context.fillStyle = color; context.textAlign = "center"; context.fillText(text, 128, 42);
  const sprite = new THREE.Sprite(new THREE.SpriteMaterial({ map: new THREE.CanvasTexture(canvas), depthTest: false })); sprite.position.copy(point); sprite.scale.set(1.2, .3, 1); return sprite;
}

export function LabView({ document: specification, parameters, domain, initialCamera, onCameraChange }: Props) {
  const host = useRef<HTMLDivElement>(null), callback = useRef(onCameraChange); callback.current = onCameraChange;
  const initial = useRef(initialCamera), bounds = useRef<GraphBounds | null>(null), fitted = useRef(false);
  const [drawing, setDrawing] = useState<LabDrawing | null>(null), [pending, setPending] = useState(true), [error, setError] = useState<string | null>(null), [generation, setGeneration] = useState(0);
  const [graphicsError,setGraphicsError]=useState<string|null>(null);
  const [axes, setAxes] = useState(true), [grid, setGrid] = useState(true);
  const spatial = specification.dimension === "3D";
  const state = useRef<{ scene: THREE.Scene; camera: Camera; controls: OrbitControls; render: () => void; axes: THREE.Group; grid: THREE.GridHelper } | null>(null);
  const submit = useRef<((input: { document: LabDocument; parameters: Record<string, number>; domain: number }) => void) | null>(null);

  useEffect(() => {
    let live = true, active = false, sequence = 0, timer: ReturnType<typeof setTimeout>, queued: { id: number; document: LabDocument; parameters: Record<string, number>; domain: number } | null = null;
    const worker = new Worker(new URL("./lab.worker.ts", import.meta.url));
    const fail = () => { if (!live) return; clearTimeout(timer); worker.terminate(); active = false; submit.current = null; setPending(false); setError("Quá trình dựng hình bị ngắt. Hãy thử lại."); };
    const send = (input: NonNullable<typeof queued>) => { active = true; clearTimeout(timer); timer = setTimeout(fail, 10000); try { worker.postMessage(input); } catch { fail(); } };
    submit.current = (input) => { const request = { ...input, id: ++sequence }; setPending(true); setError(null); if (active) queued = request; else send(request); };
    worker.onmessage = ({ data }: MessageEvent<{ id: number; drawing?: LabDrawing; error?: string }>) => {
      if (!live) return; clearTimeout(timer); active = false;
      if (queued) { const next = queued; queued = null; send(next); return; }
      if (data.id !== sequence) return;
      setPending(false); if (data.drawing) { setDrawing(data.drawing); setError(null); } else { setDrawing(null); setError(data.error ?? "Chưa dựng được hình."); }
    };
    worker.onerror = (event) => { event.preventDefault(); fail(); }; worker.onmessageerror = fail;
    return () => { live = false; clearTimeout(timer); worker.terminate(); submit.current = null; };
  }, [generation]);
  useEffect(() => { submit.current?.({ document: specification, parameters, domain }); }, [specification, parameters, domain, generation]);

  function publishCamera() {
    const current=state.current;
    if(current)callback.current?.({position:current.camera.position.toArray() as GraphCamera["position"],target:current.controls.target.toArray() as GraphCamera["target"],zoom:current.camera.zoom});
  }

  function applyCamera(saved: GraphCamera) {
    const current = state.current; if (!current) return;
    current.camera.position.fromArray(saved.position); current.camera.zoom = saved.zoom ?? 1; current.controls.target.fromArray(saved.target); current.camera.updateProjectionMatrix(); current.controls.update(); current.render(); publishCamera();
  }
  function fit() {
    const current = state.current, element = host.current; if (!current || !element || !bounds.current) return;
    const saved = fitGraphCamera(bounds.current, { position: current.camera.position.toArray() as GraphCamera["position"], target: current.controls.target.toArray() as GraphCamera["target"] }, { spatial, aspect: element.clientWidth / Math.max(element.clientHeight, 1), halfHeight: 4 });
    if (saved) applyCamera(saved);
  }
  useEffect(() => {
    const element = host.current; if (!element) return;
    let renderer: THREE.WebGLRenderer;
    try { renderer = new THREE.WebGLRenderer({ antialias: true }); setGraphicsError(null); } catch { setGraphicsError("Trình duyệt chưa mở được WebGL. Hãy bật tăng tốc đồ họa hoặc thử trình duyệt khác."); return; }
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2)); renderer.setClearColor(0x101d31);
    renderer.domElement.tabIndex = 0; renderer.domElement.setAttribute("role", "img"); renderer.domElement.setAttribute("aria-label", `Khám phá toán học ${spatial ? "3D, kéo để xoay" : "2D, kéo để di chuyển"}; cuộn để phóng to.`); element.appendChild(renderer.domElement);
    const scene = new THREE.Scene(), camera: Camera = spatial ? new THREE.PerspectiveCamera(42, 1, .1, 1500) : new THREE.OrthographicCamera(-5, 5, 5, -5, .1, 1500);
    const controls = new OrbitControls(camera, renderer.domElement); controls.enableRotate = spatial; controls.enableDamping = false; controls.screenSpacePanning = true; controls.minZoom = .05; controls.maxZoom = 30; controls.minDistance = 1; controls.maxDistance = 200;
    const initialValue = initial.current ?? defaultCamera(spatial ? "3D" : "2D"); camera.position.fromArray(initialValue.position); camera.zoom = initialValue.zoom ?? 1; controls.target.fromArray(initialValue.target); camera.updateProjectionMatrix();
    const axisGroup = new THREE.Group(), colors = ["#f18082", "#5fd6aa", "#7db3ff"];
    for (let index = 0; index < (spatial ? 3 : 2); index++) {
      const points = [new THREE.Vector3(), new THREE.Vector3()]; points[0].setComponent(index, -10); points[1].setComponent(index, 10);
      axisGroup.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints(points), new THREE.LineBasicMaterial({ color: colors[index], transparent: true, opacity: .75 })));
      axisGroup.add(textSprite(["x", "y", "z"][index], colors[index], points[1].clone().multiplyScalar(1.04)));
      for (let tick = -9; tick <= 9; tick++) if (tick && tick % 2 === 0) { const point = new THREE.Vector3(); point.setComponent(index, tick); point.setComponent(index === 0 ? 1 : 0, -.18); axisGroup.add(textSprite(String(tick), "#9bacbf", point)); }
    }
    const gridObject = new THREE.GridHelper(20, 20, 0x2b455d, 0x21374c); gridObject.rotation.x = Math.PI / 2; gridObject.position.z = -.015;
    scene.add(axisGroup, gridObject);
    const render = () => renderer.render(scene, camera);
    const change = () => { render(); callback.current?.({ position: camera.position.toArray() as GraphCamera["position"], target: controls.target.toArray() as GraphCamera["target"], zoom: camera.zoom }); };
    controls.addEventListener("change", change);
    const resize = () => { const width = element.clientWidth, height = element.clientHeight; if (!width || !height) return; renderer.setSize(width, height); const aspect = width / height; if (camera instanceof THREE.PerspectiveCamera) camera.aspect = aspect; else { camera.left = -4 * aspect; camera.right = 4 * aspect; camera.top = 4; camera.bottom = -4; } camera.updateProjectionMatrix(); render(); };
    const observer = new ResizeObserver(resize); observer.observe(element);
    const lost = (event: Event) => { event.preventDefault(); setGraphicsError("Kết nối đồ họa bị ngắt. Bấm thử lại để mở lại khung nhìn."); }; renderer.domElement.addEventListener("webglcontextlost", lost);
    state.current = { scene, camera, controls, render, axes: axisGroup, grid: gridObject }; controls.update(); resize(); change();
    return () => { state.current = null; observer.disconnect(); controls.removeEventListener("change", change); controls.dispose(); renderer.domElement.removeEventListener("webglcontextlost", lost); dispose(scene); renderer.dispose(); element.removeChild(renderer.domElement); };
  }, [spatial,generation]);
  useEffect(() => { const current = state.current; if (current) { current.axes.visible = axes; current.grid.visible = grid; current.render(); } }, [axes, grid,generation]);
  useEffect(() => {
    const current = state.current; if (!current || !drawing) return;
    const group = new THREE.Group(), box = new THREE.Box3();
    for (const line of drawing.lines) {
      const points = line.points.map((point) => new THREE.Vector3(...point));
      if (line.arrow && points.length === 2) {
        const direction = points[1].clone().sub(points[0]), length = direction.length();
        if (length > 1e-8) group.add(new THREE.ArrowHelper(direction.normalize(), points[0], length, line.color, Math.min(.3, length * .2), Math.min(.16, length * .1)));
      } else {
        const object = new THREE.Line(new THREE.BufferGeometry().setFromPoints(points), line.dashed ? new THREE.LineDashedMaterial({ color: line.color, dashSize: .13, gapSize: .08 }) : new THREE.LineBasicMaterial({ color: line.color })); object.computeLineDistances(); group.add(object);
      }
      points.forEach((point) => box.expandByPoint(point));
    }
    for (const polygon of drawing.polygons) {
      const shape = new THREE.Shape(polygon.points.map((point) => new THREE.Vector2(point[0], point[1])));
      const mesh = new THREE.Mesh(new THREE.ShapeGeometry(shape), new THREE.MeshBasicMaterial({ color: polygon.color, transparent: true, opacity: .22, side: THREE.DoubleSide, depthWrite: false })); mesh.position.z = -.005; group.add(mesh);
      const outline = new THREE.LineLoop(new THREE.BufferGeometry().setFromPoints(polygon.points.map((point) => new THREE.Vector3(...point))), new THREE.LineBasicMaterial({ color: polygon.color, transparent: true, opacity: .4 })); group.add(outline);
    }
    for (const marker of drawing.markers) {
      const object = new THREE.Mesh(marker.open ? new THREE.RingGeometry(.055, .085, 24) : new THREE.SphereGeometry(.07, 12, 8), new THREE.MeshBasicMaterial({ color: marker.color, side: THREE.DoubleSide })); object.position.fromArray(marker.point); if (!spatial) object.position.z = .04; group.add(object); box.expandByPoint(new THREE.Vector3(...marker.point));
      if (marker.label) group.add(textSprite(marker.label, marker.color, new THREE.Vector3(...marker.point).add(new THREE.Vector3(.15, .25, 0))));
    }
    bounds.current = box.isEmpty() ? null : { min: box.min.toArray() as GraphBounds["min"], max: box.max.toArray() as GraphBounds["max"] };
    current.scene.add(group); if (!fitted.current && bounds.current) { fitted.current = true; if (!initial.current) fit(); } current.render();
    return () => { current.scene.remove(group); dispose(group); };
  }, [drawing, spatial,generation]);
  const zoom = (factor: number) => { const current = state.current; if (!current) return; if (current.camera instanceof THREE.OrthographicCamera) current.camera.zoom = THREE.MathUtils.clamp(current.camera.zoom * factor, .05, 30); else { const offset = current.camera.position.clone().sub(current.controls.target).multiplyScalar(1 / factor); offset.setLength(THREE.MathUtils.clamp(offset.length(), 1, 200)); current.camera.position.copy(current.controls.target).add(offset); } current.camera.updateProjectionMatrix(); current.controls.update(); current.render(); publishCamera(); };
  return <>
    <div className={styles.labViewport}><div ref={host} className={styles.labWebgl}/><span className={styles.labViewBadge}>{specification.dimension} · {spatial ? "Kéo để xoay" : "Kéo để di chuyển"}</span>{pending?<span className={styles.graphPending}>Đang cập nhật…</span>:null}
      {error||graphicsError?<div className={styles.sceneError} role="alert">{graphicsError??error}<button className={styles.button} onClick={()=>setGeneration((value)=>value+1)}>Thử lại</button></div>:null}</div>
    <div className={styles.labViewTools} aria-label="Điều khiển phòng khám phá"><button className={styles.button} type="button" aria-label="Phóng to hình" onClick={()=>zoom(1.25)}>+</button><button className={styles.button} type="button" aria-label="Thu nhỏ hình" onClick={()=>zoom(.8)}>−</button><button className={styles.button} type="button" onClick={fit}>Vừa khung hình</button><button className={styles.button} type="button" onClick={()=>applyCamera(initial.current??defaultCamera(spatial?"3D":"2D"))}>Đặt lại góc nhìn</button><label><input type="checkbox" checked={axes} onChange={(event)=>setAxes(event.target.checked)}/> Trục</label><label><input type="checkbox" checked={grid} onChange={(event)=>setGrid(event.target.checked)}/> Lưới</label></div>
    {drawing?<><div className={styles.labMeasurements}>{drawing.measurements.map((item)=><div key={item.label}><span>{item.label}</span><strong>{item.value}</strong></div>)}</div><div className={styles.labNotices}>{drawing.notices.map((notice)=><p key={notice}>{notice}</p>)}</div></>:null}
  </>;
}
