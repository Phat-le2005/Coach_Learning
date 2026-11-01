"use client";

import { useEffect, useMemo, useRef, useState, useCallback } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { MathRenderer } from "@/components/ui/MathRenderer";
import type { TheoryNode } from "./api";
import { computeTheory3DLayout, type Node3DLayoutItem } from "./theory-3d-layout";
import { parseExampleBody, formatSolutionLines } from "./notebook-organizer";
import styles from "./TheoryMaps.module.css";

interface Theory3DMapViewProps {
  nodes: TheoryNode[];
  selectedNodeId?: string;
  onSelectNode?: (id: string) => void;
  onOpenInNotebook?: (id: string) => void;
  sourceUrl?: string;
}

interface HoverState {
  node: TheoryNode;
  hexColor: string;
  screenX: number;
  screenY: number;
}

export function Theory3DMapView({
  nodes,
  selectedNodeId,
  onSelectNode,
  onOpenInNotebook,
  sourceUrl,
}: Theory3DMapViewProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);

  const [activeNodeId, setActiveNodeId] = useState<string | null>(selectedNodeId ?? null);
  const [hoveredNode, setHoveredNode] = useState<HoverState | null>(null);
  const [autoRotate, setAutoRotate] = useState(true);
  const [activeSectionId, setActiveSectionId] = useState<string>("all");

  const layout = useMemo(() => computeTheory3DLayout(nodes), [nodes]);

  // Selected node object
  const selectedNode = useMemo(() => {
    if (!activeNodeId) return null;
    return layout.nodeMap.get(activeNodeId)?.node ?? null;
  }, [layout.nodeMap, activeNodeId]);

  // Three.js References
  const sceneRef = useRef<THREE.Scene | null>(null);
  const cameraRef = useRef<THREE.PerspectiveCamera | null>(null);
  const controlsRef = useRef<OrbitControls | null>(null);
  const interactiveMeshesRef = useRef<THREE.Mesh[]>([]);
  const meshMapRef = useRef<Map<string, THREE.Mesh>>(new Map());
  const pulsesRef = useRef<Array<{ mesh: THREE.Mesh; curve: THREE.CubicBezierCurve3; t: number; speed: number }>>([]);
  const beaconRingRef = useRef<THREE.Mesh | null>(null);
  const cameraTargetRef = useRef<{ pos: THREE.Vector3; lookAt: THREE.Vector3; active: boolean } | null>(null);

  // Sync external selectedNodeId prop
  useEffect(() => {
    if (selectedNodeId && selectedNodeId !== activeNodeId) {
      setActiveNodeId(selectedNodeId);
      focusOnNode(selectedNodeId);
    }
  }, [selectedNodeId]);

  const focusOnNode = useCallback((nodeId: string) => {
    const item = layout.nodeMap.get(nodeId);
    if (!item || !cameraRef.current || !controlsRef.current) return;

    const targetPos = item.position.clone().add(new THREE.Vector3(26, 20, 36));
    cameraTargetRef.current = {
      pos: targetPos,
      lookAt: item.position.clone(),
      active: true,
    };
  }, [layout.nodeMap]);

  const resetCamera = useCallback(() => {
    if (!cameraRef.current || !controlsRef.current) return;
    cameraTargetRef.current = {
      pos: new THREE.Vector3(0, 110, 240),
      lookAt: new THREE.Vector3(0, 0, 0),
      active: true,
    };
    setActiveSectionId("all");
  }, []);

  const focusSection = useCallback((sectionId: string) => {
    setActiveSectionId(sectionId);
    if (sectionId === "all") {
      resetCamera();
      return;
    }
    const sec = layout.sections.find((s) => s.id === sectionId);
    if (!sec || !cameraRef.current || !controlsRef.current) return;

    const targetPos = sec.position.clone().add(new THREE.Vector3(sec.position.x * 0.45, 30, sec.position.z * 0.45));
    cameraTargetRef.current = {
      pos: targetPos,
      lookAt: sec.position.clone(),
      active: true,
    };
  }, [layout.sections, resetCamera]);

  // Main Three.js Scene Setup & Animation Loop
  useEffect(() => {
    const canvas = canvasRef.current;
    const container = containerRef.current;
    if (!canvas || !container || !nodes.length) return;

    let animId: number;
    let disposed = false;

    // --- Scene & Fog ---
    const scene = new THREE.Scene();
    sceneRef.current = scene;
    scene.fog = new THREE.FogExp2(0x06110e, 0.0016);

    // --- Camera ---
    const width = container.clientWidth || 800;
    const height = container.clientHeight || 560;
    const camera = new THREE.PerspectiveCamera(52, width / height, 0.5, 1800);
    camera.position.set(0, 110, 240);
    cameraRef.current = camera;

    // --- Renderer ---
    const renderer = new THREE.WebGLRenderer({
      canvas,
      antialias: true,
      alpha: true,
      powerPreference: "high-performance",
    });
    renderer.setSize(width, height);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.15;

    // --- Controls ---
    const controls = new OrbitControls(camera, canvas);
    controls.enableDamping = true;
    controls.dampingFactor = 0.055;
    controls.maxDistance = 550;
    controls.minDistance = 25;
    controls.autoRotate = autoRotate;
    controls.autoRotateSpeed = 0.65;
    controlsRef.current = controls;

    // --- Lights ---
    const ambientLight = new THREE.AmbientLight(0xffffff, 0.95);
    scene.add(ambientLight);

    const dirLight1 = new THREE.DirectionalLight(0xd1fae5, 1.4);
    dirLight1.position.set(100, 150, 100);
    scene.add(dirLight1);

    const dirLight2 = new THREE.DirectionalLight(0x38bdf8, 1.1);
    dirLight2.position.set(-100, -80, -100);
    scene.add(dirLight2);

    const rootPointLight = new THREE.PointLight(0x10b981, 2.8, 180);
    rootPointLight.position.set(0, 0, 0);
    scene.add(rootPointLight);

    // --- Starfield Dust Particles ---
    const starCount = 850;
    const starGeo = new THREE.BufferGeometry();
    const starPositions = new Float32Array(starCount * 3);
    const starColors = new Float32Array(starCount * 3);

    const starColorPalette = [
      new THREE.Color("#10b981"),
      new THREE.Color("#38bdf8"),
      new THREE.Color("#fbbf24"),
      new THREE.Color("#93c5fd"),
      new THREE.Color("#dcfce7"),
    ];

    for (let i = 0; i < starCount; i++) {
      const radius = 80 + Math.random() * 380;
      const theta = Math.random() * Math.PI * 2;
      const phi = Math.acos(Math.random() * 2 - 1);

      starPositions[i * 3] = radius * Math.sin(phi) * Math.cos(theta);
      starPositions[i * 3 + 1] = radius * Math.cos(phi) * 0.7;
      starPositions[i * 3 + 2] = radius * Math.sin(phi) * Math.sin(theta);

      const c = starColorPalette[Math.floor(Math.random() * starColorPalette.length)];
      starColors[i * 3] = c.r;
      starColors[i * 3 + 1] = c.g;
      starColors[i * 3 + 2] = c.b;
    }

    starGeo.setAttribute("position", new THREE.BufferAttribute(starPositions, 3));
    starGeo.setAttribute("color", new THREE.BufferAttribute(starColors, 3));
    const starMat = new THREE.PointsMaterial({
      size: 1.8,
      vertexColors: true,
      transparent: true,
      opacity: 0.65,
      blending: THREE.AdditiveBlending,
    });
    const starField = new THREE.Points(starGeo, starMat);
    scene.add(starField);

    // --- Interactive 3D Nodes ---
    const interactiveMeshes: THREE.Mesh[] = [];
    const meshMap = new Map<string, THREE.Mesh>();
    const nodeGroup = new THREE.Group();
    scene.add(nodeGroup);

    layout.nodes.forEach((item) => {
      const isRoot = item.depth === 0;
      const isSection = item.depth === 1;

      const sphereGeo = new THREE.SphereGeometry(item.size, isRoot ? 32 : isSection ? 24 : 16, isRoot ? 32 : 16);
      const sphereMat = new THREE.MeshStandardMaterial({
        color: item.color,
        emissive: item.color,
        emissiveIntensity: isRoot ? 0.7 : isSection ? 0.45 : 0.28,
        roughness: 0.25,
        metalness: 0.35,
      });

      const mesh = new THREE.Mesh(sphereGeo, sphereMat);
      mesh.position.copy(item.position);
      mesh.userData = { nodeId: item.node.id, layoutItem: item };

      // Atmosphere / Wireframe Ring around Root & Sections
      if (isRoot || isSection) {
        const ringGeo = new THREE.RingGeometry(item.size * 1.35, item.size * 1.5, 32);
        const ringMat = new THREE.MeshBasicMaterial({
          color: item.color,
          side: THREE.DoubleSide,
          transparent: true,
          opacity: 0.4,
          blending: THREE.AdditiveBlending,
        });
        const ring = new THREE.Mesh(ringGeo, ringMat);
        ring.rotation.x = Math.PI / 2;
        mesh.add(ring);
      }

      nodeGroup.add(mesh);
      interactiveMeshes.push(mesh);
      meshMap.set(item.node.id, mesh);
    });

    interactiveMeshesRef.current = interactiveMeshes;
    meshMapRef.current = meshMap;

    // --- Connecting Curves & Traveling Energy Pulses ---
    const connectionsGroup = new THREE.Group();
    scene.add(connectionsGroup);

    const pulseSphereGeo = new THREE.SphereGeometry(0.85, 8, 8);
    const pulses: Array<{ mesh: THREE.Mesh; curve: THREE.CubicBezierCurve3; t: number; speed: number }> = [];

    layout.connections.forEach((conn) => {
      // Tube / Line Geometry for connection beam
      const points = conn.curve.getPoints(24);
      const lineGeo = new THREE.BufferGeometry().setFromPoints(points);
      const lineMat = new THREE.LineBasicMaterial({
        color: conn.color,
        transparent: true,
        opacity: 0.38,
        blending: THREE.AdditiveBlending,
      });
      const line = new THREE.Line(lineGeo, lineMat);
      connectionsGroup.add(line);

      // Energy Pulse traveling along line
      const pulseMat = new THREE.MeshBasicMaterial({
        color: conn.color,
        blending: THREE.AdditiveBlending,
      });
      const pulseMesh = new THREE.Mesh(pulseSphereGeo, pulseMat);
      pulseMesh.position.copy(points[0]);
      connectionsGroup.add(pulseMesh);

      pulses.push({
        mesh: pulseMesh,
        curve: conn.curve,
        t: Math.random(),
        speed: 0.003 + Math.random() * 0.003,
      });
    });

    pulsesRef.current = pulses;

    // --- Selection Beacon Ring ---
    const beaconGeo = new THREE.RingGeometry(6, 7.2, 32);
    const beaconMat = new THREE.MeshBasicMaterial({
      color: 0x34d399,
      side: THREE.DoubleSide,
      transparent: true,
      opacity: 0.85,
      blending: THREE.AdditiveBlending,
    });
    const beaconRing = new THREE.Mesh(beaconGeo, beaconMat);
    beaconRing.rotation.x = Math.PI / 2;
    beaconRing.visible = false;
    scene.add(beaconRing);
    beaconRingRef.current = beaconRing;

    // --- Raycasting & Pointer Handlers ---
    const raycaster = new THREE.Raycaster();
    const pointer = new THREE.Vector2();

    function onPointerMove(event: MouseEvent) {
      if (!canvas) return;
      const rect = canvas.getBoundingClientRect();
      pointer.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
      pointer.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;

      raycaster.setFromCamera(pointer, camera);
      const intersects = raycaster.intersectObjects(interactiveMeshes);

      if (intersects.length > 0) {
        const hit = intersects[0].object as THREE.Mesh;
        const item: Node3DLayoutItem | undefined = hit.userData?.layoutItem;
        if (item && item.node) {
          canvas.style.cursor = "pointer";
          setHoveredNode({
            node: item.node,
            hexColor: item.hexColor,
            screenX: event.clientX - rect.left,
            screenY: event.clientY - rect.top,
          });
          return;
        }
      }

      canvas.style.cursor = "default";
      setHoveredNode(null);
    }

    function onPointerClick(event: MouseEvent) {
      if (!canvas) return;
      const rect = canvas.getBoundingClientRect();
      pointer.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
      pointer.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;

      raycaster.setFromCamera(pointer, camera);
      const intersects = raycaster.intersectObjects(interactiveMeshes);

      if (intersects.length > 0) {
        const hit = intersects[0].object as THREE.Mesh;
        const nodeId: string | undefined = hit.userData?.nodeId;
        if (nodeId) {
          setActiveNodeId(nodeId);
          onSelectNode?.(nodeId);
          focusOnNode(nodeId);
        }
      }
    }

    canvas.addEventListener("mousemove", onPointerMove);
    canvas.addEventListener("click", onPointerClick);

    // --- Resize Handler ---
    function onResize() {
      if (!container || !camera || !renderer) return;
      const newW = container.clientWidth;
      const newH = container.clientHeight;
      camera.aspect = newW / newH;
      camera.updateProjectionMatrix();
      renderer.setSize(newW, newH);
    }
    window.addEventListener("resize", onResize);

    // --- Animation Loop ---
    let lastTime = performance.now();

    function animate(currentTime = performance.now()) {
      if (disposed) return;
      animId = requestAnimationFrame(animate);

      const delta = Math.min((currentTime - lastTime) * 0.001, 0.1);
      lastTime = currentTime;
      const time = currentTime * 0.001;

      // Controls update
      controls.update();

      // Rotate starfield slowly
      starField.rotation.y = time * 0.015;

      // Pulse traveling energy along curves
      pulses.forEach((p) => {
        p.t = (p.t + p.speed) % 1;
        const pt = p.curve.getPoint(p.t);
        p.mesh.position.copy(pt);
      });

      // Selection Beacon Ring follow active node
      if (beaconRingRef.current && activeNodeId) {
        const activeMesh = meshMap.get(activeNodeId);
        if (activeMesh) {
          beaconRingRef.current.visible = true;
          beaconRingRef.current.position.copy(activeMesh.position);
          beaconRingRef.current.position.y += 0.5;
          const scale = 1 + Math.sin(time * 3.5) * 0.15;
          beaconRingRef.current.scale.set(scale, scale, scale);
        }
      }

      // Smooth Camera Fly-To Lerp
      if (cameraTargetRef.current?.active) {
        const tgt = cameraTargetRef.current;
        camera.position.lerp(tgt.pos, 0.05);
        controls.target.lerp(tgt.lookAt, 0.05);

        if (camera.position.distanceTo(tgt.pos) < 1.0 && controls.target.distanceTo(tgt.lookAt) < 1.0) {
          tgt.active = false;
        }
      }

      renderer.render(scene, camera);
    }

    animate();

    return () => {
      disposed = true;
      cancelAnimationFrame(animId);
      window.removeEventListener("resize", onResize);
      canvas.removeEventListener("mousemove", onPointerMove);
      canvas.removeEventListener("click", onPointerClick);

      controls.dispose();
      renderer.dispose();
      starGeo.dispose();
      starMat.dispose();
      pulseSphereGeo.dispose();
    };
  }, [layout, onSelectNode, focusOnNode, autoRotate, activeNodeId]);

  // Update controls autoRotate when state changes
  useEffect(() => {
    if (controlsRef.current) {
      controlsRef.current.autoRotate = autoRotate;
    }
  }, [autoRotate]);

  return (
    <div className={styles.threeDContainer} ref={containerRef}>
      <canvas ref={canvasRef} className={styles.threeDCanvas} />

      {/* Floating 3D HUD Top Bar */}
      <div className={styles.threeDTopBar}>
        <div className={styles.threeDDocBadge}>
          <span className={styles.threeDPulseDot} />
          <strong>🪐 SƠ ĐỒ KHÔNG GIAN 3D</strong>
          <span className={styles.threeDCountTag}>{layout.nodes.length} điểm tri thức</span>
        </div>

        {/* Section Quick Jump Filter */}
        <div className={styles.threeDSectionFilter}>
          <label htmlFor="sec3d-select" className={styles.srOnly}>Góc nhìn chuyên đề</label>
          <select
            id="sec3d-select"
            value={activeSectionId}
            onChange={(e) => focusSection(e.target.value)}
            className={styles.threeDSelect}
          >
            <option value="all">🪐 Toàn cảnh không gian</option>
            {layout.sections.map((s, idx) => (
              <option key={s.id} value={s.id}>
                {idx + 1}. {s.title.replace(/^\d+[\.\s]*/, "")}
              </option>
            ))}
          </select>
        </div>

        {/* 3D Action Tools */}
        <div className={styles.threeDToolButtons}>
          <button
            type="button"
            className={autoRotate ? styles.threeDToolBtnActive : styles.threeDToolBtn}
            onClick={() => setAutoRotate(!autoRotate)}
            title="Bật/Tắt tự động xoay không gian 3D"
          >
            🔄 {autoRotate ? "Đang xoay" : "Dừng xoay"}
          </button>
          <button
            type="button"
            className={styles.threeDToolBtn}
            onClick={resetCamera}
            title="Đưa góc nhìn về trung tâm toàn cảnh"
          >
            🎯 Toàn cảnh
          </button>
        </div>
      </div>

      {/* Gesture Controls Guide (Bottom Left) */}
      <div className={styles.threeDGuideCard}>
        <span className={styles.threeDGuideTitle}>🎮 Thao tác 3D:</span>
        <div className={styles.threeDGuideItems}>
          <span>🖱️ <strong>Chuột trái:</strong> Xoay 360°</span>
          <span>🖱️ <strong>Chuột phải:</strong> Di chuyển (Pan)</span>
          <span>🔍 <strong>Cuộn:</strong> Phóng to / Thu nhỏ</span>
          <span>👆 <strong>Bấm điểm:</strong> Xem chi tiết</span>
        </div>
      </div>

      {/* Interactive Floating Hover Tooltip */}
      {hoveredNode && (
        <div
          className={styles.threeDTooltip}
          style={{ left: hoveredNode.screenX + 14, top: hoveredNode.screenY + 14 }}
        >
          <span
            className={styles.threeDTooltipDot}
            style={{ backgroundColor: hoveredNode.hexColor }}
          />
          <div>
            <div className={styles.threeDTooltipTitle}>{hoveredNode.node.title}</div>
            <div className={styles.threeDTooltipMeta}>
              <span>Trang {hoveredNode.node.source_page}</span>
              <small>• Bấm để mở bài học</small>
            </div>
          </div>
        </div>
      )}

      {/* Slide-Over Interactive Detail Drawer (When a node is selected) */}
      {selectedNode && (
        <aside className={styles.threeDDetailDrawer} aria-label="Chi tiết điểm tri thức 3D">
          <div className={styles.drawerHeader}>
            <div className={styles.drawerTitleGroup}>
              <span className={styles.drawerTypeBadge}>
                {selectedNode.kind === "ROOT"
                  ? "🌟 CHUYÊN ĐỀ GỐC"
                  : selectedNode.kind === "SECTION"
                  ? "📚 BÀI HỌC LỚN"
                  : selectedNode.kind === "FORMULA"
                  ? "📐 CÔNG THỨC TRỌNG TÂM"
                  : selectedNode.kind === "EXAMPLE"
                  ? "💡 VÍ DỤ MINH HỌA"
                  : selectedNode.kind === "NOTE"
                  ? "⚠️ BẪY SAI LẦM"
                  : "🎯 DẠNG TOÁN TIÊU BIỂU"}
              </span>
              <h3 className={styles.drawerTitle}>{selectedNode.title}</h3>
              <span className={styles.drawerPageCitation}>Trang {selectedNode.source_page}</span>
            </div>

            <button
              type="button"
              className={styles.drawerCloseBtn}
              onClick={() => setActiveNodeId(null)}
              aria-label="Đóng bảng chi tiết"
            >
              ✕
            </button>
          </div>

          <div className={styles.drawerBody}>
            {/* 1. Formula Display */}
            {selectedNode.latex && (
              <div className={styles.drawerFormulaCard}>
                <div className={styles.drawerCardHeading}>📐 Công thức KaTeX chuẩn:</div>
                <div className={styles.drawerKatexWrap}>
                  <MathRenderer content={`$$${selectedNode.latex}$$`} />
                </div>
              </div>
            )}

            {/* 2. Step-by-step Procedures */}
            {selectedNode.learning_steps.length > 0 && (
              <div className={styles.drawerMethodCard}>
                <div className={styles.drawerCardHeading}>📝 Các bước giải bài tập:</div>
                <ol className={styles.drawerStepsList}>
                  {selectedNode.learning_steps.map((step, idx) => (
                    <li key={idx}>
                      <strong>Bước {idx + 1}:</strong>{" "}
                      <MathRenderer content={step.instruction.replace(/^Bước\s*\d+[\:\.]\s*/i, "")} />
                      {step.latex && (
                        <div className={styles.drawerStepFormula}>
                          <MathRenderer content={`$$${step.latex}$$`} />
                        </div>
                      )}
                    </li>
                  ))}
                </ol>
              </div>
            )}

            {/* 3. Example Problem & Solution */}
            {(selectedNode.kind === "EXAMPLE" || selectedNode.title.includes("Ví dụ")) && selectedNode.body && (
              <div className={styles.drawerExampleCard}>
                {(() => {
                  const { question, solution } = parseExampleBody(selectedNode.body);
                  const lines = formatSolutionLines(solution);
                  return (
                    <>
                      {question && (
                        <div className={styles.drawerQuestionBox}>
                          <span className={styles.drawerTag}>Đề bài:</span>
                          <MathRenderer content={question} />
                        </div>
                      )}
                      {solution && (
                        <div className={styles.drawerSolutionBox}>
                          <span className={styles.drawerTag}>Lời giải chi tiết:</span>
                          {lines.map((line, lIdx) => (
                            <div key={lIdx} className={styles.drawerSolutionLine}>
                              <MathRenderer content={line} />
                            </div>
                          ))}
                        </div>
                      )}
                    </>
                  );
                })()}
              </div>
            )}

            {/* 4. Concept Definition / Explanation Body */}
            {selectedNode.kind !== "EXAMPLE" && !selectedNode.title.includes("Ví dụ") && selectedNode.body && (
              <div
                className={
                  selectedNode.kind === "NOTE" || selectedNode.title.includes("Bẫy")
                    ? styles.drawerTrapCard
                    : styles.drawerConceptCard
                }
              >
                <div className={styles.drawerCardHeading}>
                  {selectedNode.kind === "NOTE" || selectedNode.title.includes("Bẫy")
                    ? "⚠️ Bẫy sai lầm & Lưu ý phòng tránh:"
                    : "📖 Bản chất lý thuyết & Điều cần nhớ:"}
                </div>
                <div className={styles.drawerProse}>
                  <MathRenderer content={selectedNode.body} />
                </div>
              </div>
            )}
          </div>

          {/* Drawer Footer Actions */}
          <div className={styles.drawerFooter}>
            {onOpenInNotebook && (
              <button
                type="button"
                className={styles.drawerNotebookBtn}
                onClick={() => onOpenInNotebook(selectedNode.id)}
              >
                📖 Mở trong Sổ tay ghi chép →
              </button>
            )}
            {sourceUrl && (
              <a
                href={`${sourceUrl}#page=${selectedNode.source_page}`}
                target="_blank"
                rel="noopener noreferrer"
                className={styles.drawerSourceLink}
              >
                📄 Đối chiếu trang {selectedNode.source_page} PDF ↗
              </a>
            )}
          </div>
        </aside>
      )}
    </div>
  );
}
