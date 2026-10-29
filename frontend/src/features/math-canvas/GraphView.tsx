"use client";

import { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { defaultCamera, type GraphCamera, type GraphSettings, type MathExpression } from "./expression";
import { describeGraphView, isSpatialView, resolveGraphView, sampleViewPoint } from "./presentation";
import { useImplicitGeometry } from "./useImplicitGeometry";
import { fitGraphCamera, type GraphBounds } from "./fit-camera";
import styles from "./MathCanvas.module.css";

interface Props { model: MathExpression; settings: GraphSettings; initialCamera?: GraphCamera; onCameraChange?: (camera: GraphCamera) => void }
type Camera = THREE.PerspectiveCamera | THREE.OrthographicCamera;
interface SceneState { scene: THREE.Scene; camera: Camera; controls: OrbitControls; render: () => void; change: () => void }
export { defaultCamera } from "./expression";

function dispose(group: THREE.Object3D) {
  group.traverse((obj) => {
    if (obj instanceof THREE.Mesh || obj instanceof THREE.Line || obj instanceof THREE.Sprite) {
      if ("geometry" in obj) obj.geometry.dispose();
      (Array.isArray(obj.material) ? obj.material : [obj.material]).forEach((material) => {
        if ("map" in material && material.map instanceof THREE.Texture) material.map.dispose();
        material.dispose();
      });
    }
  });
}
function label(text: string, position: THREE.Vector3, color: string, size = .42): THREE.Sprite {
  const canvas = document.createElement("canvas"); canvas.width = 128; canvas.height = 64;
  const ctx = canvas.getContext("2d")!;
  ctx.font = "600 30px system-ui"; ctx.textAlign = "center"; ctx.textBaseline = "middle";
  ctx.fillStyle = color; ctx.fillText(text, 64, 32);
  const sprite = new THREE.Sprite(new THREE.SpriteMaterial({ map: new THREE.CanvasTexture(canvas), depthTest: false }));
  sprite.position.copy(position); sprite.scale.set(size * 2, size, 1); return sprite;
}

export function GraphView({ model, settings, initialCamera, onCameraChange }: Props) {
  const mode = resolveGraphView(model, settings), spatial = isSpatialView(mode);
  const host = useRef<HTMLDivElement>(null);
  const cameraCallback = useRef(onCameraChange); cameraCallback.current = onCameraChange;
  const sceneState = useRef<SceneState | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [sampleCount, setSampleCount] = useState(0);
  const [truncated, setTruncated] = useState(false);
  const [fitError, setFitError] = useState<string | null>(null);
  const bounds = useRef<GraphBounds | null>(null);
  const fittedCamera = useRef<GraphCamera | null>(null);
  const initiallyFitted = useRef(false);
  const implicit = useImplicitGeometry(model, settings);
  const [showAxes, setShowAxes] = useState(true), [showGrid, setShowGrid] = useState(true), [wireframe, setWireframe] = useState(false);
  const initial = useRef(initialCamera); initial.current = initialCamera;
  const domain = useRef(settings.domain); domain.current = settings.domain;
  const description = describeGraphView(model, settings);

  const applyCamera = (saved: GraphCamera) => {
    const state = sceneState.current; if (!state) return;
    state.camera.position.fromArray(saved.position); state.controls.target.fromArray(saved.target); state.camera.zoom = saved.zoom ?? 1;
    state.camera.updateProjectionMatrix(); state.controls.update(); state.change();
  };
  const fit = () => {
    const state = sceneState.current, element = host.current;
    if (!state || !element || !bounds.current || !element.clientHeight) return;
    const saved = fitGraphCamera(bounds.current, {
      position: state.camera.position.toArray() as GraphCamera["position"], target: state.controls.target.toArray() as GraphCamera["target"],
    }, { spatial, aspect: element.clientWidth / element.clientHeight, halfHeight: Math.max(4, domain.current * 1.2) });
    if (!saved) { setFitError("Hình vượt phạm vi quan sát. Thử thu hẹp miền hoặc đổi tham số."); return; }
    if (!fittedCamera.current) fittedCamera.current = saved;
    applyCamera(saved); setFitError(null);
  };

  useEffect(() => {
    const element = host.current;
    if (!element) return;
    let renderer: THREE.WebGLRenderer;
    try { renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true }); }
    catch { setError("Thiết bị chưa bật WebGL. Hãy bật tăng tốc đồ họa hoặc thử trình duyệt khác để xem hình."); return; }
    setError(null);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2)); renderer.setClearColor(0x0b1627, 1);
    renderer.domElement.tabIndex = 0; renderer.domElement.setAttribute("role", "img");
    element.appendChild(renderer.domElement);
    const scene = new THREE.Scene();
    const camera: Camera = spatial ? new THREE.PerspectiveCamera(42, 1, .1, 500) : new THREE.OrthographicCamera(-5, 5, 5, -5, .1, 500);
    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableRotate = spatial; controls.minDistance = 1; controls.maxDistance = 120;
    controls.minZoom = .05; controls.maxZoom = 30; controls.screenSpacePanning = true;
    controls.mouseButtons.LEFT = spatial ? THREE.MOUSE.ROTATE : THREE.MOUSE.PAN;
    controls.touches.ONE = spatial ? THREE.TOUCH.ROTATE : THREE.TOUCH.PAN;
    controls.listenToKeyEvents(renderer.domElement);
    const saved = initial.current ?? defaultCamera(spatial ? "3D" : "2D");
    camera.position.fromArray(saved.position); controls.target.fromArray(saved.target); camera.zoom = saved.zoom ?? 1;
    camera.updateProjectionMatrix(); controls.update();
    scene.add(new THREE.HemisphereLight(0xd6f4ff, 0x163048, 2.8));
    const light = new THREE.DirectionalLight(0xffffff, 2.5); light.position.set(5, 10, 8); scene.add(light);
    const render = () => renderer.render(scene, camera);
    const change = () => {
      render(); cameraCallback.current?.({ position: camera.position.toArray() as GraphCamera["position"], target: controls.target.toArray() as GraphCamera["target"], zoom: camera.zoom });
    };
    const lost = (event: Event) => { event.preventDefault(); setError("Ngữ cảnh đồ họa đã bị ngắt. Đóng rồi mở lại Math View để khôi phục."); };
    renderer.domElement.addEventListener("webglcontextlost", lost);
    controls.addEventListener("change", change);
    const resize = new ResizeObserver(() => {
      const width = element.clientWidth, height = element.clientHeight;
      if (!width || !height) return;
      renderer.setSize(width, height);
      if (camera instanceof THREE.PerspectiveCamera) camera.aspect = width / height;
      else { const half = Math.max(4, domain.current * 1.2); camera.left = -half * width / height; camera.right = -camera.left; camera.top = half; camera.bottom = -half; }
      camera.updateProjectionMatrix(); render();
    });
    resize.observe(element); sceneState.current = { scene, camera, controls, render, change }; change();
    return () => {
      resize.disconnect(); controls.removeEventListener("change", change); controls.dispose();
      renderer.domElement.removeEventListener("webglcontextlost", lost); dispose(scene);
      renderer.dispose(); renderer.domElement.remove(); sceneState.current = null;
      bounds.current = null; fittedCamera.current = null; initiallyFitted.current = false;
    };
  }, [mode, spatial]);

  useEffect(() => {
    host.current?.querySelector("canvas")?.setAttribute("aria-label", `${description}. ${spatial ? "Kéo xoay" : "Kéo di chuyển"}, cuộn hoặc dùng nút để zoom.`);
  }, [description, spatial]);

  useEffect(() => {
    const state = sceneState.current, element = host.current;
    if (!state || !element || !(state.camera instanceof THREE.OrthographicCamera) || !element.clientHeight) return;
    const half = Math.max(4, settings.domain * 1.2);
    state.camera.left = -half * element.clientWidth / element.clientHeight; state.camera.right = -state.camera.left;
    state.camera.top = half; state.camera.bottom = -half; state.camera.updateProjectionMatrix(); state.render();
  }, [settings.domain, mode]);

  useEffect(() => {
    const state = sceneState.current; if (!state) return;
    const d = settings.domain, extent = d * 1.12, group = new THREE.Group();
    const grid = new THREE.GridHelper(2 * d, Math.min(40, Math.max(4, Math.round(2 * d))), 0x49617d, 0x25384f);
    if (!spatial) grid.rotation.x = Math.PI / 2;
    grid.visible = showGrid; group.add(grid);
    if (showAxes) {
      const heightIsZ = model.dimension === "3D";
      const names = ["x", heightIsZ ? "z" : "y", heightIsZ ? "y" : "z"], colors = ["#fb7185", "#6ee7b7", "#7dbbff"];
      for (let axis = 0; axis < (spatial ? 3 : 2); axis++) {
        const direction = new THREE.Vector3().setComponent(axis, 1);
        group.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints([direction.clone().multiplyScalar(-extent), direction.clone().multiplyScalar(extent)]), new THREE.LineBasicMaterial({ color: colors[axis] })));
        group.add(label(names[axis], direction.clone().multiplyScalar(extent * 1.08), colors[axis], d * .12));
        for (const value of [-d, -d / 2, d / 2, d]) {
          const pos = direction.clone().multiplyScalar(value); pos.setComponent((axis + 1) % (spatial ? 3 : 2), -d * .055);
          group.add(label(Number(value.toFixed(1)).toString(), pos, "#a7bacf", d * .085));
        }
      }
      group.add(label("O", new THREE.Vector3(-d * .07, -d * .07, 0), "#a7bacf", d * .1));
    }
    state.scene.add(group); state.render();
    return () => { state.scene.remove(group); dispose(group); };
  }, [mode, spatial, model.dimension, settings.domain, showAxes, showGrid]);

  useEffect(() => {
    const state = sceneState.current; if (!state) return;
    const group = new THREE.Group(); let valid = 0, limited = false;
    if (model.kind === "implicit") {
      const data = implicit.data;
      if (!data) { setSampleCount(0); return; }
      const geometry = new THREE.BufferGeometry(); geometry.setAttribute("position", new THREE.BufferAttribute(data.positions, 3));
      if (data.primitive === "triangles") {
        geometry.computeVertexNormals(); group.add(new THREE.Mesh(geometry, new THREE.MeshStandardMaterial({ color: 0x58cfb8, side: THREE.DoubleSide, roughness: .55, wireframe })));
      } else group.add(new THREE.LineSegments(geometry, new THREE.LineBasicMaterial({ color: 0x62e4ce })));
      valid = data.positions.length / 3; limited = data.truncated;
    } else if (mode === "SURFACE_3D" || mode === "EXTRUDED_3D") {
      const n = 64, positions: number[] = [], colors: number[] = [], indices: number[] = [], finite: boolean[] = [];
      for (let j = 0; j <= n; j++) for (let i = 0; i <= n; i++) {
        const x = -settings.domain + 2 * settings.domain * i / n, y = -settings.domain + 2 * settings.domain * j / n;
        const z = sampleViewPoint(model, settings, x, y)[1]; finite.push(Number.isFinite(z));
        positions.push(x, Number.isFinite(z) ? z : 0, y);
        const color = new THREE.Color().setHSL(.56 - Math.atan(Number.isFinite(z) ? z / 4 : 0) * .18, .75, .56); colors.push(color.r,color.g,color.b);
      }
      for (let j = 0; j < n; j++) for (let i = 0; i < n; i++) {
        const a = j * (n + 1) + i, b = a + 1, c = a + n + 1, d = c + 1;
        if ([a,b,c,d].every((k) => finite[k]) && Math.max(...[a,b,c,d].map(k => positions[k*3+1])) - Math.min(...[a,b,c,d].map(k => positions[k*3+1])) < settings.domain * 2) indices.push(a,c,b,b,c,d);
      }
      const geometry = new THREE.BufferGeometry(); geometry.setAttribute("position", new THREE.Float32BufferAttribute(positions,3));
      geometry.setAttribute("color", new THREE.Float32BufferAttribute(colors,3)); geometry.setIndex(indices); geometry.computeVertexNormals();
      group.add(new THREE.Mesh(geometry, new THREE.MeshStandardMaterial({ vertexColors: true, side: THREE.DoubleSide, roughness: .48, wireframe })));
      valid = indices.length;
    } else {
      let segment: THREE.Vector3[] = [];
      const flush = () => { if (segment.length > 1) { group.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints(segment), new THREE.LineBasicMaterial({ color: 0x62e4ce }))); valid += segment.length; } segment = []; };
      for (let i = 0; i <= 900; i++) {
        const x = -settings.domain + 2 * settings.domain * i / 900, y = sampleViewPoint(model, settings, x)[1];
        if (!Number.isFinite(y) || Math.abs(y) > 1000) { flush(); continue; }
        if (segment.length && Math.abs(y - segment[segment.length - 1].y) > settings.domain * 2) flush();
        segment.push(new THREE.Vector3(x,y,0));
      }
      flush();
    }
    // Only include referenced vertices: unused samples near poles must not distort camera fitting.
    const box = new THREE.Box3(), point = new THREE.Vector3();
    group.traverse((object) => {
      if (!(object instanceof THREE.Mesh || object instanceof THREE.Line)) return;
      const position = object.geometry.getAttribute("position"), index = object.geometry.getIndex();
      for (let i = 0; i < (index?.count ?? position.count); i++) {
        point.fromBufferAttribute(position, index ? index.getX(i) : i);
        if (Number.isFinite(point.x) && Number.isFinite(point.y) && Number.isFinite(point.z)) box.expandByPoint(point);
      }
    });
    bounds.current = valid && !box.isEmpty() ? { min: box.min.toArray() as GraphBounds["min"], max: box.max.toArray() as GraphBounds["max"] } : null;
    setSampleCount(valid); setTruncated(limited); setFitError(null); state.scene.add(group);
    if (valid && !initiallyFitted.current) {
      initiallyFitted.current = true;
      if (!initial.current) fit();
    }
    state.render();
    return () => { state.scene.remove(group); dispose(group); bounds.current = null; };
  }, [model, settings, mode, spatial, wireframe, implicit.data]);

  const reset = () => {
    const state = sceneState.current; if (!state) return;
    const saved = initialCamera ?? fittedCamera.current ?? defaultCamera(spatial ? "3D" : "2D");
    applyCamera(saved); setFitError(null);
  };
  const zoom = (factor: number) => {
    const state = sceneState.current; if (!state) return;
    if (state.camera instanceof THREE.OrthographicCamera) state.camera.zoom = THREE.MathUtils.clamp(state.camera.zoom * factor, .05, 30);
    else {
      const offset = state.camera.position.clone().sub(state.controls.target);
      offset.setLength(THREE.MathUtils.clamp(offset.length() / factor, 1, 120)); state.camera.position.copy(state.controls.target).add(offset);
    }
    state.camera.updateProjectionMatrix(); state.controls.update(); state.change();
  };
  return <div>
    <div className={styles.graphFrame}>
      <div ref={host} className={styles.graph} />
      <div className={styles.graphLegend}>{model.dimension === "3D" ? spatial ? "x: đỏ · y: xanh dương · z: xanh lá" : "x: đỏ · z: xanh lá" : spatial ? "x: đỏ · y: xanh lá · z: xanh dương" : "x: đỏ · y: xanh lá"} · {spatial ? "Kéo xoay" : "Kéo di chuyển"} · Cuộn/chụm để zoom</div>
      <div className={styles.viewportActions}>
        <button type="button" aria-label="Phóng to đồ thị" onClick={() => zoom(1.25)}>+</button>
        <button type="button" aria-label="Thu nhỏ đồ thị" onClick={() => zoom(.8)}>−</button>
        <button type="button" disabled={!sampleCount || implicit.pending} onClick={fit}>Vừa đồ thị</button>
        <button type="button" onClick={reset}>Đặt lại góc nhìn</button>
      </div>
      {implicit.pending && !error ? <span className={styles.graphPending} role={sampleCount ? undefined : "status"} aria-live={sampleCount ? "off" : "polite"}>Đang cập nhật hình…</span> : null}
      {error ? <p role="alert" className={styles.graphError}>{error}</p> : implicit.error ? <div className={styles.graphError} role="alert"><p>{implicit.error}</p><button type="button" onClick={implicit.retry}>Thử lại</button></div>
        : !implicit.pending && sampleCount === 0 ? <p className={styles.graphError} role="status">Chưa thấy hình trong miền này. Thử đổi miền hoặc tham số; chi tiết quá nhỏ có thể chưa được lấy mẫu.</p> : null}
    </div>
    <div className={styles.row} role="group" aria-label="Hiển thị đồ thị">
      <label><input type="checkbox" checked={showAxes} onChange={(e) => setShowAxes(e.target.checked)} /> Trục và tọa độ</label>
      <label><input type="checkbox" checked={showGrid} onChange={(e) => setShowGrid(e.target.checked)} /> Lưới</label>
      {spatial && (model.kind === "implicit" && model.dimension === "3D" || mode === "SURFACE_3D" || mode === "EXTRUDED_3D") ? <label><input type="checkbox" checked={wireframe} onChange={(e) => setWireframe(e.target.checked)} /> Khung lưới</label> : null}
    </div>
    {truncated ? <p className={styles.muted}>Hình đã đạt giới hạn chi tiết. Thu hẹp miền để xem rõ hơn.</p> : null}
    {fitError ? <p className={styles.muted} role="status">{fitError}</p> : null}
  </div>;
}
