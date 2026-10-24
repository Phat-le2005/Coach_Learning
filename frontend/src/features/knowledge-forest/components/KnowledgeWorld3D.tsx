"use client";

import { Compass, Layers, RotateCcw, Sparkles, X, Zap } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";

import { filterKnowledgeForest } from "../filter";
import {
  computeLivingWorld3DLayout,
  type LivingWorld3DLayout,
  type Node3DLayout,
} from "../tree-3d-layout";
import type {
  KnowledgeChapterNode,
  KnowledgeForestViewModel,
  KnowledgeProblemTypeNode,
  KnowledgeStatusFilter,
} from "../types";
import styles from "../KnowledgeWorld3D.module.css";
import { ChapterBranchesSystem, createChapterBranches } from "./3d/ChapterBranch";
import { ConnectionsSystem, createKnowledgeConnections } from "./3d/KnowledgeConnection";
import { createKnowledgeNodes, NodesSystem } from "./3d/KnowledgeNode";
import { createKnowledgeTree, TreeSystem } from "./3d/KnowledgeTree";
import { createTopicClusters, TopicClustersSystem } from "./3d/TopicCluster";
import { KnowledgeCameraController } from "./3d/KnowledgeCameraController";
import { KnowledgeDetailPanel } from "./KnowledgeDetailPanel";
import { KnowledgeNavigation } from "./KnowledgeNavigation";

export interface KnowledgeWorld3DProps {
  data: KnowledgeForestViewModel;
  viewMode: "3D" | "2D";
  onViewModeChange: (mode: "3D" | "2D") => void;
  selectedId?: string;
  onSelectProblemType: (pt: KnowledgeProblemTypeNode) => void;
  onClearSelection: () => void;
  searchQuery: string;
  onSearchChange: (q: string) => void;
  statusFilter: KnowledgeStatusFilter;
  onStatusFilterChange: (f: KnowledgeStatusFilter) => void;
  onResetFilters?: () => void;
}

export function KnowledgeWorld3D({
  data,
  viewMode,
  onViewModeChange,
  selectedId,
  onSelectProblemType,
  onClearSelection,
  searchQuery,
  onStatusFilterChange,
  statusFilter,
  onSearchChange,
}: KnowledgeWorld3DProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);

  const [showPrerequisites, setShowPrerequisites] = useState(false);
  const [activeChapterId, setActiveChapterId] = useState<string | undefined>(undefined);
  const [showChapterExplorer, setShowChapterExplorer] = useState(false);
  const [isFullscreen, setIsFullscreen] = useState(false);

  // Tooltip & Projected Labels state
  const [hoveredNode, setHoveredNode] = useState<{
    pt: KnowledgeProblemTypeNode;
    screenX: number;
    screenY: number;
  } | null>(null);

  const [projectedChapters, setProjectedChapters] = useState<
    Array<{
      id: string;
      shortName: string;
      fullName: string;
      themeColor: string;
      screenX: number;
      screenY: number;
      completionPercent: number;
      visible: boolean;
    }>
  >([]);

  const [projectedActiveNodes, setProjectedActiveNodes] = useState<
    Array<{
      id: string;
      name: string;
      screenX: number;
      screenY: number;
      themeColor: string;
      pt: KnowledgeProblemTypeNode;
      visible: boolean;
    }>
  >([]);

  // 1. Compute deterministic 3D layout from curriculum data
  const layout = useMemo<LivingWorld3DLayout>(() => {
    return computeLivingWorld3DLayout(data.chapters);
  }, [data.chapters]);

  // Selected Node data
  const selectedNode = useMemo(() => {
    if (!selectedId) return null;
    return layout.nodeMap.get(selectedId)?.data ?? null;
  }, [layout.nodeMap, selectedId]);

  // Active Chapter layout
  const activeChapterLayout = useMemo(() => {
    if (!activeChapterId) return null;
    return layout.chapters.find((c) => c.data.id === activeChapterId) ?? null;
  }, [layout.chapters, activeChapterId]);

  // Filtered nodes
  const matchedProblemTypeIds = useMemo(() => {
    const ids = new Set<string>();
    const res = filterKnowledgeForest({
      chapters: data.chapters,
      concepts: [],
      searchQuery,
      statusFilter,
    });
    res.filteredChapters.forEach((ch) =>
      ch.topics.forEach((t) => t.problemTypes.forEach((pt) => ids.add(pt.id)))
    );
    return ids;
  }, [data.chapters, searchQuery, statusFilter]);

  // Internal references to 3D systems
  const sceneRef = useRef<THREE.Scene | null>(null);
  const cameraRef = useRef<THREE.PerspectiveCamera | null>(null);
  const controlsRef = useRef<OrbitControls | null>(null);
  const cameraControllerRef = useRef<KnowledgeCameraController | null>(null);
  const nodesSystemRef = useRef<NodesSystem | null>(null);
  const connectionsSystemRef = useRef<ConnectionsSystem | null>(null);

  // Keep a ref to activeChapterId for the animation loop
  const activeChapterIdRef = useRef<string | undefined>(activeChapterId);
  useEffect(() => {
    activeChapterIdRef.current = activeChapterId;
  }, [activeChapterId]);

  // Initialize Three.js Scene
  useEffect(() => {
    const canvas = canvasRef.current;
    const container = containerRef.current;
    if (!canvas || !container) return;

    // --- Scene & Fog ---
    const scene = new THREE.Scene();
    sceneRef.current = scene;
    scene.fog = new THREE.FogExp2(0x061e18, 0.0035);

    // --- Camera ---
    const width = container.clientWidth;
    const height = container.clientHeight;
    const camera = new THREE.PerspectiveCamera(50, width / height, 0.1, 2000);
    camera.position.set(
      layout.overviewCamera.position.x,
      layout.overviewCamera.position.y,
      layout.overviewCamera.position.z
    );
    cameraRef.current = camera;

    // --- Renderer ---
    const renderer = new THREE.WebGLRenderer({
      canvas,
      antialias: true,
      alpha: true,
      powerPreference: "high-performance",
    });
    renderer.setSize(width, height);
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    renderer.setPixelRatio(dpr);
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.2;
    renderer.outputColorSpace = THREE.SRGBColorSpace;

    // --- Orbit Controls ---
    const controls = new OrbitControls(camera, canvas);
    controls.enableDamping = true;
    controls.dampingFactor = 0.05;
    controls.maxPolarAngle = Math.PI / 2 + 0.1;
    controls.minDistance = 15;
    controls.maxDistance = 280;
    controls.target.set(
      layout.overviewCamera.target.x,
      layout.overviewCamera.target.y,
      layout.overviewCamera.target.z
    );
    controlsRef.current = controls;

    const cameraController = new KnowledgeCameraController(camera, controls);
    cameraControllerRef.current = cameraController;

    // --- Atmospheric Lights ---
    const ambientLight = new THREE.AmbientLight(0x0f4236, 1.4);
    scene.add(ambientLight);

    const dirLight = new THREE.DirectionalLight(0xd1fbf1, 1.5);
    dirLight.position.set(45, 85, 55);
    scene.add(dirLight);

    const rimLight = new THREE.DirectionalLight(0x67bfd4, 0.9);
    rimLight.position.set(-50, 45, -50);
    scene.add(rimLight);

    const coreLight = new THREE.PointLight(0x8be5c2, 3.2, 55);
    coreLight.position.set(layout.corePosition.x, layout.corePosition.y, layout.corePosition.z);
    scene.add(coreLight);

    // --- 3D Scene Systems ---
    const treeSystem: TreeSystem = createKnowledgeTree(layout.corePosition, layout.trunkSpline);
    scene.add(treeSystem.group);

    const branchesSystem: ChapterBranchesSystem = createChapterBranches(layout.chapters);
    scene.add(branchesSystem.group);

    const topicSystem: TopicClustersSystem = createTopicClusters(layout.chapters);
    scene.add(topicSystem.group);

    const allNodes: Node3DLayout[] = [];
    layout.chapters.forEach((ch) => ch.topics.forEach((t) => allNodes.push(...t.nodes)));
    const nodesSystem: NodesSystem = createKnowledgeNodes(allNodes);
    scene.add(nodesSystem.group);
    nodesSystemRef.current = nodesSystem;

    const connectionsSystem: ConnectionsSystem = createKnowledgeConnections(layout.prerequisiteArcs);
    scene.add(connectionsSystem.group);
    connectionsSystemRef.current = connectionsSystem;

    // --- Raycasting for Pointer Hover & Selection ---
    const raycaster = new THREE.Raycaster();
    const pointer = new THREE.Vector2();

    const handlePointerMove = (e: MouseEvent) => {
      const rect = canvas.getBoundingClientRect();
      pointer.x = ((e.clientX - rect.left) / rect.width) * 2 - 1;
      pointer.y = -((e.clientY - rect.top) / rect.height) * 2 + 1;

      raycaster.setFromCamera(pointer, camera);
      const intersects = raycaster.intersectObjects(nodesSystem.interactiveMeshes);

      if (intersects.length > 0) {
        const top = intersects[0].object;
        const ptData = (top.userData as { data?: KnowledgeProblemTypeNode }).data;
        if (ptData) {
          nodesSystem.highlightNode(ptData.id);
          setHoveredNode({
            pt: ptData,
            screenX: e.clientX - rect.left,
            screenY: e.clientY - rect.top,
          });
          canvas.style.cursor = "pointer";
          return;
        }
      }

      nodesSystem.highlightNode(null);
      setHoveredNode(null);
      canvas.style.cursor = "default";
    };

    const handleClick = (e: MouseEvent) => {
      const rect = canvas.getBoundingClientRect();
      pointer.x = ((e.clientX - rect.left) / rect.width) * 2 - 1;
      pointer.y = -((e.clientY - rect.top) / rect.height) * 2 + 1;

      raycaster.setFromCamera(pointer, camera);
      const intersects = raycaster.intersectObjects(nodesSystem.interactiveMeshes);

      if (intersects.length > 0) {
        const top = intersects[0].object;
        const ptData = (top.userData as { data?: KnowledgeProblemTypeNode }).data;
        if (ptData) {
          onSelectProblemType(ptData);
          return;
        }
      }
    };

    canvas.addEventListener("mousemove", handlePointerMove);
    canvas.addEventListener("click", handleClick);

    // --- Animation & Render Loop ---
    let animationFrameId: number;
    const clock = new THREE.Clock();

    const animate = () => {
      animationFrameId = requestAnimationFrame(animate);
      const elapsedTime = clock.getElapsedTime();

      treeSystem.update(elapsedTime);
      nodesSystem.update(elapsedTime);
      connectionsSystem.update(elapsedTime);
      cameraController.update();

      // Project Chapter Badges to 2D Screen Coordinates with LOD check
      const projChapters: Array<{
        id: string;
        shortName: string;
        fullName: string;
        themeColor: string;
        screenX: number;
        screenY: number;
        completionPercent: number;
        visible: boolean;
      }> = [];

      const tempVec = new THREE.Vector3();
      layout.chapters.forEach((ch) => {
        tempVec.set(ch.position.x, ch.position.y + 4.2, ch.position.z);
        tempVec.project(camera);
        const inFront = tempVec.z < 1.0;
        const screenX = (tempVec.x * 0.5 + 0.5) * container.clientWidth;
        const screenY = (-tempVec.y * 0.5 + 0.5) * container.clientHeight;

        projChapters.push({
          id: ch.data.id,
          shortName: ch.shortName,
          fullName: ch.data.name,
          themeColor: ch.themeColor,
          screenX,
          screenY,
          completionPercent: ch.completionPercent,
          visible:
            inFront &&
            screenX >= 0 &&
            screenX <= container.clientWidth &&
            screenY >= 0 &&
            screenY <= container.clientHeight,
        });
      });
      setProjectedChapters(projChapters);

      // Project Problem Type Node Labels for Active Chapter (LOD in-scene labels)
      const currentActiveCh = activeChapterIdRef.current;
      if (currentActiveCh) {
        const chLayout = layout.chapters.find((c) => c.data.id === currentActiveCh);
        if (chLayout) {
          const projNodes: Array<{
            id: string;
            name: string;
            screenX: number;
            screenY: number;
            themeColor: string;
            pt: KnowledgeProblemTypeNode;
            visible: boolean;
          }> = [];

          chLayout.topics.forEach((topic) => {
            topic.nodes.forEach((node) => {
              tempVec.set(node.position.x, node.position.y + 1.8, node.position.z);
              tempVec.project(camera);
              const inFront = tempVec.z < 1.0;
              const screenX = (tempVec.x * 0.5 + 0.5) * container.clientWidth;
              const screenY = (-tempVec.y * 0.5 + 0.5) * container.clientHeight;

              projNodes.push({
                id: node.data.id,
                name: node.data.name,
                screenX,
                screenY,
                themeColor: node.themeColor,
                pt: node.data,
                visible:
                  inFront &&
                  screenX >= 20 &&
                  screenX <= container.clientWidth - 20 &&
                  screenY >= 40 &&
                  screenY <= container.clientHeight - 40,
              });
            });
          });
          setProjectedActiveNodes(projNodes);
        } else {
          setProjectedActiveNodes([]);
        }
      } else {
        setProjectedActiveNodes([]);
      }

      renderer.render(scene, camera);
    };
    animate();

    // --- Resize Observer ---
    const handleResize = () => {
      if (!container) return;
      const w = container.clientWidth;
      const h = container.clientHeight;
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
      renderer.setSize(w, h);
    };
    window.addEventListener("resize", handleResize);

    // Cleanup
    return () => {
      cancelAnimationFrame(animationFrameId);
      window.removeEventListener("resize", handleResize);
      canvas.removeEventListener("mousemove", handlePointerMove);
      canvas.removeEventListener("click", handleClick);
      controls.dispose();
      treeSystem.dispose();
      branchesSystem.dispose();
      topicSystem.dispose();
      nodesSystem.dispose();
      connectionsSystem.dispose();
      renderer.dispose();
    };
  }, [layout, onSelectProblemType]);

  // Synchronize selection changes with 3D camera and highlight
  useEffect(() => {
    if (!nodesSystemRef.current || !cameraControllerRef.current) return;

    if (selectedId) {
      nodesSystemRef.current.selectNode(selectedId);
      const nodePos = layout.nodeMap.get(selectedId)?.position;
      if (nodePos) {
        cameraControllerRef.current.flyToNode(nodePos);
      }
      const ptNode = layout.nodeMap.get(selectedId);
      if (ptNode) {
        setActiveChapterId(ptNode.chapterId);
      }
      const ptCode = ptNode?.data.code;
      if (connectionsSystemRef.current) {
        connectionsSystemRef.current.setVisible(true);
        connectionsSystemRef.current.highlightConnections(ptCode ?? null);
      }
    } else {
      nodesSystemRef.current.selectNode(null);
      if (connectionsSystemRef.current) {
        connectionsSystemRef.current.setVisible(showPrerequisites);
        connectionsSystemRef.current.highlightConnections(null);
      }
    }
  }, [selectedId, layout.nodeMap, showPrerequisites]);

  // Synchronize search and status filter with node dimming
  useEffect(() => {
    if (!nodesSystemRef.current) return;
    nodesSystemRef.current.nodeMeshes.forEach((mesh, id) => {
      const isMatched = matchedProblemTypeIds.has(id);
      mesh.visible = isMatched;
    });
  }, [matchedProblemTypeIds]);

  // Fly to Chapter & Open Chapter Explorer Dock
  const handleSelectChapter = useCallback(
    (chapterId: string) => {
      setActiveChapterId(chapterId);
      setShowChapterExplorer(true);
      const chLayout = layout.chapters.find((c) => c.data.id === chapterId);
      if (chLayout && cameraControllerRef.current) {
        cameraControllerRef.current.flyToChapter(chLayout.position);
      }
    },
    [layout.chapters]
  );

  // Reset Camera to Overview
  const handleResetCamera = useCallback(() => {
    setActiveChapterId(undefined);
    setShowChapterExplorer(false);
    onClearSelection();
    if (cameraControllerRef.current) {
      cameraControllerRef.current.flyToOverview(layout.overviewCamera);
    }
  }, [layout.overviewCamera, onClearSelection]);

  // Toggle Prerequisite Arcs
  const handleTogglePrerequisites = useCallback(() => {
    setShowPrerequisites((prev) => {
      const next = !prev;
      connectionsSystemRef.current?.setVisible(next);
      return next;
    });
  }, []);

  // Fullscreen
  const handleToggleFullscreen = useCallback(() => {
    if (!containerRef.current) return;
    if (!document.fullscreenElement) {
      containerRef.current.requestFullscreen().catch(() => {});
      setIsFullscreen(true);
    } else {
      document.exitFullscreen().catch(() => {});
      setIsFullscreen(false);
    }
  }, []);

  return (
    <div ref={containerRef} className={styles.worldContainer}>
      {/* Three.js Canvas */}
      <canvas ref={canvasRef} className={styles.canvas3D} />

      {/* Floating Glass Top Navigation */}
      <KnowledgeNavigation
        data={data}
        viewMode={viewMode}
        onViewModeChange={onViewModeChange}
        searchQuery={searchQuery}
        onSearchChange={onSearchChange}
        statusFilter={statusFilter}
        onStatusFilterChange={onStatusFilterChange}
        showPrerequisites={showPrerequisites}
        onTogglePrerequisites={handleTogglePrerequisites}
        onResetCamera={handleResetCamera}
        onSelectChapter={handleSelectChapter}
        activeChapterId={activeChapterId}
        onToggleFullscreen={handleToggleFullscreen}
        isFullscreen={isFullscreen}
      />

      {/* HTML 3D Projected Labels Layer */}
      <div className={styles.htmlOverlayLayer}>
        {/* Compact, Crisp Chapter Badges */}
        {projectedChapters.map((ch) => {
          if (!ch.visible) return null;
          const isActive = ch.id === activeChapterId;
          return (
            <div
              key={ch.id}
              className={`${styles.chapterBadge3D} ${isActive ? styles.chapterBadgeActive : ""}`}
              style={{ left: `${ch.screenX}px`, top: `${ch.screenY}px` }}
              onClick={() => handleSelectChapter(ch.id)}
              title={ch.fullName}
            >
              <span
                className={styles.chapterBadgeDot}
                style={{ backgroundColor: ch.themeColor }}
              />
              <span className={styles.chapterBadgeTitle}>{ch.shortName}</span>
              <span className={styles.chapterBadgeProgress}>{ch.completionPercent}%</span>
            </div>
          );
        })}

        {/* In-Scene 3D Problem Type Node Labels (Active Chapter) */}
        {projectedActiveNodes.map((item) => {
          if (!item.visible) return null;
          return (
            <div
              key={item.id}
              className={styles.nodeBadge3D}
              style={{ left: `${item.screenX}px`, top: `${item.screenY}px` }}
              onClick={() => onSelectProblemType(item.pt)}
            >
              <span
                className={styles.nodeBadgeDot}
                style={{ backgroundColor: item.themeColor }}
              />
              <span className={styles.nodeBadgeTitle}>{item.name}</span>
            </div>
          );
        })}

        {/* Hovered Node Tooltip */}
        {hoveredNode && (
          <div
            className={styles.nodeTooltip3D}
            style={{ left: `${hoveredNode.screenX}px`, top: `${hoveredNode.screenY}px` }}
          >
            <span className={styles.nodeTooltipTitle}>{hoveredNode.pt.name}</span>
            <span className={styles.nodeTooltipState}>
              {hoveredNode.pt.masteryScore !== undefined
                ? `${hoveredNode.pt.masteryScore}% thành thạo`
                : "Chưa bắt đầu"}
            </span>
          </div>
        )}
      </div>

      {/* Floating Chapter Canopy Explorer Dock (Shows all problem types of active chapter clearly) */}
      {showChapterExplorer && activeChapterLayout && (
        <div className={styles.chapterExplorerDock}>
          <div className={styles.chapterExplorerHeader}>
            <div className={styles.chapterExplorerHeaderLeft}>
              <span
                className={styles.chapterBadgeDot}
                style={{ backgroundColor: activeChapterLayout.themeColor }}
              />
              <span className={styles.chapterExplorerTitle}>
                {activeChapterLayout.data.name}
              </span>
              <span className={styles.chapterExplorerMeta}>
                {activeChapterLayout.totalProblemTypes} dạng bài • {activeChapterLayout.completionPercent}%
              </span>
            </div>
            <button
              className={styles.chapterExplorerCloseBtn}
              onClick={() => setShowChapterExplorer(false)}
              aria-label="Thu nhỏ danh sách dạng bài"
            >
              <X size={16} />
            </button>
          </div>

          <div className={styles.chapterExplorerBody}>
            {activeChapterLayout.topics.flatMap((topic) =>
              topic.nodes.map((node) => {
                const isSelected = selectedId === node.data.id;
                return (
                  <div
                    key={node.data.id}
                    className={`${styles.chapterExplorerCard} ${
                      isSelected ? styles.chapterExplorerCardActive : ""
                    }`}
                    onClick={() => onSelectProblemType(node.data)}
                  >
                    <div>
                      <div className={styles.chapterExplorerCardTopic}>{topic.data.name}</div>
                      <div className={styles.chapterExplorerCardName}>{node.data.name}</div>
                    </div>
                    <div className={styles.chapterExplorerCardFooter}>
                      <span className={styles.chapterExplorerCardBadge}>
                        <span
                          style={{
                            width: 6,
                            height: 6,
                            borderRadius: "50%",
                            backgroundColor: node.themeColor,
                            display: "inline-block",
                          }}
                        />
                        <span>
                          {node.data.masteryScore !== undefined
                            ? `${node.data.masteryScore}%`
                            : "Chưa học"}
                        </span>
                      </span>
                      <Zap size={13} color="#8be5c2" />
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </div>
      )}

      {/* Floating Bottom Quick Controls */}
      <div className={styles.bottomControls}>
        <button
          className={styles.controlActionBtn}
          onClick={handleResetCamera}
          title="Toàn cảnh thế giới tri thức"
        >
          <Compass size={14} />
          <span>Toàn cảnh</span>
        </button>

        {activeChapterLayout && (
          <>
            <span style={{ color: "rgba(139, 229, 194, 0.3)" }}>|</span>
            <button
              className={styles.controlActionBtn}
              onClick={() => setShowChapterExplorer((prev) => !prev)}
              title="Mở bảng duyệt dạng bài của chương"
            >
              <Layers size={14} />
              <span>{showChapterExplorer ? "Ẩn dạng bài" : "Xem dạng bài chương"}</span>
            </button>
          </>
        )}

        <span style={{ color: "rgba(139, 229, 194, 0.3)" }}>|</span>
        <button
          className={styles.controlActionBtn}
          onClick={handleTogglePrerequisites}
          title="Bật tắt hiển thị liên kết tiên quyết"
        >
          <span style={{ color: showPrerequisites ? "#8be5c2" : "inherit" }}>
            {showPrerequisites ? "✓ Ẩn quan hệ" : "✦ Hiện quan hệ"}
          </span>
        </button>
      </div>

      {/* Right Floating Detail Panel */}
      <KnowledgeDetailPanel
        node={selectedNode}
        onClose={onClearSelection}
        onSelectRelatedCode={(code) => {
          const ptNode = layout.nodeByCodeMap.get(code)?.data;
          if (ptNode) {
            onSelectProblemType(ptNode);
          }
        }}
        onExploreRelations={(code) => {
          setShowPrerequisites(true);
          connectionsSystemRef.current?.setVisible(true);
          connectionsSystemRef.current?.highlightConnections(code);
        }}
      />
    </div>
  );
}
