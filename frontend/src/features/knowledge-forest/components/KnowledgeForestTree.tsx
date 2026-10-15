"use client";

import {
  Maximize2,
  Minus,
  Moon,
  Orbit,
  Plus,
  RotateCcw,
  Sparkles,
  Sun,
  TreePine,
} from "lucide-react";
import {
  type KeyboardEvent as ReactKeyboardEvent,
  type PointerEvent as ReactPointerEvent,
  type WheelEvent as ReactWheelEvent,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import { getMasteryStateLabel } from "../copy";
import { filterKnowledgeForest } from "../filter";
import {
  buildGalaxyConstellationLayout,
  fitGalaxyCamera,
  focusGalaxyCamera,
  GALAXY_DIMENSIONS,
  panGalaxyCamera,
  zoomGalaxyCameraAt,
} from "../galaxy-constellation-layout";
import {
  buildLivingTreeLayout,
  fitTreeCamera,
  focusTreeCamera,
  LIVING_TREE_DIMENSIONS,
  panTreeCamera,
  type TreeCamera,
  type TreePoint,
  type TreeRect,
  type TreeViewport,
  zoomTreeCameraAt,
} from "../living-tree-layout";
import type {
  KnowledgeChapterNode,
  KnowledgeProblemTypeNode,
  KnowledgeStatusFilter,
} from "../types";
import styles from "../KnowledgeForest.module.css";

export interface KnowledgeForestTreeProps {
  chapters: KnowledgeChapterNode[];
  subjectName: string;
  selectedId?: string;
  initialNodeId?: string;
  onSelectProblemType: (problemType: KnowledgeProblemTypeNode) => void;
  onClearSelection: () => void;
  searchQuery: string;
  statusFilter: KnowledgeStatusFilter;
  onResetFilters?: () => void;
}

type FocusTarget =
  | { kind: "chapter"; id: string; chapterId: string }
  | { kind: "topic"; id: string; chapterId: string }
  | { kind: "leaf"; id: string; chapterId: string; topicId: string }
  | null;

interface GestureStart {
  camera: TreeCamera;
  midpoint: TreePoint;
  distance: number;
}

const INITIAL_CAMERA: TreeCamera = { x: 0, y: 0, scale: 0.5 };

function keyboardActivate(event: ReactKeyboardEvent<SVGGElement>, action: () => void) {
  if (event.key === "Enter" || event.key === " ") {
    event.preventDefault();
    action();
  }
}

function shortLabel(value: string, length = 32): string {
  return value.length <= length ? value : `${value.slice(0, length - 1).trim()}…`;
}

function midpoint(first: TreePoint, second: TreePoint): TreePoint {
  return { x: (first.x + second.x) / 2, y: (first.y + second.y) / 2 };
}

function distance(first: TreePoint, second: TreePoint): number {
  return Math.hypot(second.x - first.x, second.y - first.y);
}

export function KnowledgeForestTree({
  chapters,
  subjectName,
  selectedId,
  initialNodeId,
  onSelectProblemType,
  onClearSelection,
  searchQuery,
  statusFilter,
  onResetFilters,
}: KnowledgeForestTreeProps) {
  const [viewMode, setViewMode] = useState<"galaxy" | "tree">("galaxy");
  const [isCosmicDark, setIsCosmicDark] = useState(true);

  const viewportRef = useRef<HTMLDivElement>(null);
  const pointersRef = useRef(new Map<number, TreePoint>());
  const lastPanPointRef = useRef<TreePoint | null>(null);
  const gestureStartRef = useRef<GestureStart | null>(null);
  const pointerDownPosRef = useRef<TreePoint | null>(null);
  const isDraggingRef = useRef(false);

  // Pre-calculate both layouts
  const galaxyLayout = useMemo(() => buildGalaxyConstellationLayout(chapters), [chapters]);
  const treeLayout = useMemo(() => buildLivingTreeLayout(chapters), [chapters]);

  const [viewport, setViewport] = useState<TreeViewport>({ width: 1, height: 1 });
  const [camera, setCamera] = useState<TreeCamera>(INITIAL_CAMERA);
  const [focusTarget, setFocusTarget] = useState<FocusTarget>(null);
  const [hasCameraReady, setHasCameraReady] = useState(false);

  const cameraRef = useRef(camera);
  useEffect(() => {
    cameraRef.current = camera;
  }, [camera]);

  const viewportStateRef = useRef(viewport);
  useEffect(() => {
    viewportStateRef.current = viewport;
  }, [viewport]);

  const filtered = useMemo(
    () => filterKnowledgeForest({ chapters, concepts: [], searchQuery, statusFilter }),
    [chapters, searchQuery, statusFilter]
  );

  const visibleLeafIds = useMemo(
    () =>
      new Set(
        filtered.filteredChapters.flatMap((chapter) =>
          chapter.topics.flatMap((topic) =>
            topic.problemTypes.map((problemType) => problemType.id)
          )
        )
      ),
    [filtered.filteredChapters]
  );
  const visibleTopicIds = useMemo(
    () =>
      new Set(
        filtered.filteredChapters.flatMap((chapter) =>
          chapter.topics.map((topic) => topic.id)
        )
      ),
    [filtered.filteredChapters]
  );
  const visibleChapterIds = useMemo(
    () => new Set(filtered.filteredChapters.map((chapter) => chapter.id)),
    [filtered.filteredChapters]
  );

  const isFiltered = Boolean(searchQuery.trim()) || statusFilter !== "ALL";
  const lowDetail = camera.scale < 0.45;

  // Fit camera based on active view mode
  const fitCamera = useCallback(() => {
    if (viewport.width <= 1 || viewport.height <= 1) return;
    const padding = viewport.width < 440 ? 16 : viewport.width < 640 ? 24 : 36;
    if (viewMode === "galaxy") {
      setCamera(fitGalaxyCamera(viewport, galaxyLayout.bounds, padding, 0.92));
    } else {
      setCamera(fitTreeCamera(viewport, treeLayout.bounds, padding, 0.92));
    }
    setFocusTarget(null);
  }, [galaxyLayout.bounds, treeLayout.bounds, viewMode, viewport]);

  const focusBounds = useCallback(
    (bounds: TreeRect, maxScale = 1.35) => {
      if (viewport.width <= 1 || viewport.height <= 1) return;
      if (viewMode === "galaxy") {
        setCamera(focusGalaxyCamera(viewport, bounds, viewport.width < 640 ? 48 : 72, maxScale));
      } else {
        setCamera(focusTreeCamera(viewport, bounds, viewport.width < 640 ? 54 : 92, maxScale));
      }
    },
    [viewMode, viewport]
  );

  const writeNodeToHistory = useCallback((nodeId: string | null) => {
    const url = new URL(window.location.href);
    if (nodeId) url.searchParams.set("node", nodeId);
    else url.searchParams.delete("node");
    window.history.pushState(null, "", `${url.pathname}${url.search}${url.hash}`);
  }, []);

  const focusNode = useCallback(
    (nodeId: string | null, updateHistory: boolean, revealLeaf = true) => {
      if (!nodeId) {
        onClearSelection();
        fitCamera();
        if (updateHistory) writeNodeToHistory(null);
        return;
      }

      if (viewMode === "galaxy") {
        for (const core of galaxyLayout.cores) {
          if (core.node.id === nodeId) {
            onClearSelection();
            setFocusTarget({ kind: "chapter", id: nodeId, chapterId: core.node.id });
            focusBounds(core.bounds, 0.95);
            if (updateHistory) writeNodeToHistory(nodeId);
            return;
          }
          for (const planet of core.planets) {
            if (planet.node.id === nodeId) {
              onClearSelection();
              setFocusTarget({ kind: "topic", id: nodeId, chapterId: core.node.id });
              focusBounds(planet.bounds, 1.25);
              if (updateHistory) writeNodeToHistory(nodeId);
              return;
            }
            const star = planet.stars.find((s) => s.node.id === nodeId);
            if (star) {
              if (revealLeaf) onSelectProblemType(star.node);
              setFocusTarget({
                kind: "leaf",
                id: nodeId,
                chapterId: core.node.id,
                topicId: planet.node.id,
              });
              if (updateHistory) writeNodeToHistory(nodeId);
              focusBounds(
                { x: star.center.x - 140, y: star.center.y - 110, width: 280, height: 220 },
                1.55
              );
              return;
            }
          }
        }
      } else {
        // Tree mode focus
        for (const chapter of treeLayout.chapters) {
          if (chapter.node.id === nodeId) {
            onClearSelection();
            setFocusTarget({ kind: "chapter", id: nodeId, chapterId: chapter.node.id });
            focusBounds(chapter.bounds, 0.95);
            if (updateHistory) writeNodeToHistory(nodeId);
            return;
          }
          for (const topic of chapter.topics) {
            if (topic.node.id === nodeId) {
              onClearSelection();
              setFocusTarget({ kind: "topic", id: nodeId, chapterId: chapter.node.id });
              focusBounds(topic.bounds, 1.25);
              if (updateHistory) writeNodeToHistory(nodeId);
              return;
            }
            const leaf = topic.leaves.find((candidate) => candidate.node.id === nodeId);
            if (leaf) {
              if (revealLeaf) onSelectProblemType(leaf.node);
              setFocusTarget({
                kind: "leaf",
                id: nodeId,
                chapterId: chapter.node.id,
                topicId: topic.node.id,
              });
              if (updateHistory) writeNodeToHistory(nodeId);
              focusBounds(
                { x: leaf.center.x - 150, y: leaf.center.y - 115, width: 300, height: 230 },
                1.45
              );
              return;
            }
          }
        }
      }
    },
    [fitCamera, focusBounds, galaxyLayout.cores, onClearSelection, onSelectProblemType, treeLayout.chapters, viewMode, writeNodeToHistory]
  );

  // Resize listener
  useEffect(() => {
    const element = viewportRef.current;
    if (!element) return;
    const updateSize = () => {
      const rect = element.getBoundingClientRect();
      setViewport({ width: Math.max(1, rect.width), height: Math.max(1, rect.height) });
    };
    updateSize();
    const observer = new ResizeObserver(updateSize);
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  // Initial camera placement
  useEffect(() => {
    if (viewport.width <= 1 || viewport.height <= 1 || hasCameraReady) return;
    const padding = viewport.width < 440 ? 16 : viewport.width < 640 ? 24 : 36;
    if (viewMode === "galaxy") {
      setCamera(fitGalaxyCamera(viewport, galaxyLayout.bounds, padding, 0.92));
    } else {
      setCamera(fitTreeCamera(viewport, treeLayout.bounds, padding, 0.92));
    }
    setHasCameraReady(true);
    if (initialNodeId) requestAnimationFrame(() => focusNode(initialNodeId, false));
  }, [focusNode, galaxyLayout.bounds, hasCameraReady, initialNodeId, treeLayout.bounds, viewMode, viewport]);

  // Handle URL history state
  useEffect(() => {
    const handlePopState = () =>
      focusNode(new URL(window.location.href).searchParams.get("node"), false);
    window.addEventListener("popstate", handlePopState);
    return () => window.removeEventListener("popstate", handlePopState);
  }, [focusNode]);

  useEffect(() => {
    if (!selectedId && focusTarget?.kind === "leaf") {
      setFocusTarget(null);
    }
  }, [selectedId, focusTarget]);

  // Search auto-focus
  useEffect(() => {
    if (!searchQuery.trim()) return;
    const firstResult = filtered.filteredChapters
      .flatMap((c) => c.topics)
      .flatMap((t) => t.problemTypes)[0];
    if (!firstResult) return;
    focusNode(firstResult.id, false, false);
  }, [filtered.filteredChapters, focusNode, searchQuery]);

  const zoomBy = (factor: number) => {
    const centerPoint = { x: viewport.width / 2, y: viewport.height / 2 };
    if (viewMode === "galaxy") {
      setCamera((current) => zoomGalaxyCameraAt(current, centerPoint, current.scale * factor));
    } else {
      setCamera((current) => zoomTreeCameraAt(current, centerPoint, current.scale * factor));
    }
  };

  const handleWheel = (event: ReactWheelEvent<SVGSVGElement>) => {
    event.preventDefault();
    const rect = event.currentTarget.getBoundingClientRect();
    const cursor = { x: event.clientX - rect.left, y: event.clientY - rect.top };
    const nextScale = camera.scale * Math.exp(-event.deltaY * 0.0014);
    if (viewMode === "galaxy") {
      setCamera((current) => zoomGalaxyCameraAt(current, cursor, nextScale));
    } else {
      setCamera((current) => zoomTreeCameraAt(current, cursor, nextScale));
    }
  };

  const handlePointerDown = (event: ReactPointerEvent<SVGSVGElement>) => {
    event.currentTarget.setPointerCapture(event.pointerId);
    const nextPoint = { x: event.clientX, y: event.clientY };
    pointersRef.current.set(event.pointerId, nextPoint);
    isDraggingRef.current = false;
    if (pointersRef.current.size === 1) {
      lastPanPointRef.current = nextPoint;
      pointerDownPosRef.current = nextPoint;
    }
    if (pointersRef.current.size === 2) {
      isDraggingRef.current = true;
      const [first, second] = [...pointersRef.current.values()];
      gestureStartRef.current = {
        camera,
        midpoint: midpoint(first, second),
        distance: distance(first, second),
      };
    }
  };

  const handlePointerMove = (event: ReactPointerEvent<SVGSVGElement>) => {
    if (!pointersRef.current.has(event.pointerId)) return;
    const nextPoint = { x: event.clientX, y: event.clientY };
    pointersRef.current.set(event.pointerId, nextPoint);
    if (pointerDownPosRef.current) {
      const dist = Math.hypot(
        nextPoint.x - pointerDownPosRef.current.x,
        nextPoint.y - pointerDownPosRef.current.y
      );
      if (dist > 6) {
        isDraggingRef.current = true;
      }
    }
    if (pointersRef.current.size === 1 && lastPanPointRef.current) {
      const previous = lastPanPointRef.current;
      const delta = { x: nextPoint.x - previous.x, y: nextPoint.y - previous.y };
      if (viewMode === "galaxy") {
        setCamera((current) => panGalaxyCamera(current, delta));
      } else {
        setCamera((current) => panTreeCamera(current, delta));
      }
      lastPanPointRef.current = nextPoint;
    } else if (pointersRef.current.size === 2 && gestureStartRef.current) {
      const [first, second] = [...pointersRef.current.values()];
      const start = gestureStartRef.current;
      const currentMidpoint = midpoint(first, second);
      const distRatio = distance(first, second) / Math.max(1, start.distance);
      const targetScale = start.camera.scale * distRatio;
      const scaled =
        viewMode === "galaxy"
          ? zoomGalaxyCameraAt(start.camera, start.midpoint, targetScale)
          : zoomTreeCameraAt(start.camera, start.midpoint, targetScale);
      setCamera({
        ...scaled,
        x: scaled.x + currentMidpoint.x - start.midpoint.x,
        y: scaled.y + currentMidpoint.y - start.midpoint.y,
      });
    }
  };

  const handlePointerEnd = (event: ReactPointerEvent<SVGSVGElement>) => {
    pointersRef.current.delete(event.pointerId);
    gestureStartRef.current = null;
    lastPanPointRef.current =
      pointersRef.current.size === 1 ? [...pointersRef.current.values()][0] : null;
    if (pointersRef.current.size === 0) {
      pointerDownPosRef.current = null;
    }
  };

  const handleNodeClick = (action: () => void) => {
    if (isDraggingRef.current) return;
    action();
  };

  const handleKeyDown = (event: ReactKeyboardEvent<SVGSVGElement>) => {
    const panDistance = 56;
    if (event.key === "ArrowLeft")
      setCamera((current) => panGalaxyCamera(current, { x: panDistance, y: 0 }));
    else if (event.key === "ArrowRight")
      setCamera((current) => panGalaxyCamera(current, { x: -panDistance, y: 0 }));
    else if (event.key === "ArrowUp")
      setCamera((current) => panGalaxyCamera(current, { x: 0, y: panDistance }));
    else if (event.key === "ArrowDown")
      setCamera((current) => panGalaxyCamera(current, { x: 0, y: -panDistance }));
    else if (event.key === "+" || event.key === "=") zoomBy(1.18);
    else if (event.key === "-") zoomBy(0.85);
    else if (event.key === "0") fitCamera();
    else return;
    event.preventDefault();
  };

  if (chapters.length === 0) {
    return (
      <div className={styles.emptyCard}>
        <TreePine size={38} aria-hidden="true" />
        <h3 className={styles.emptyTitle}>Chưa có cấu trúc cây tri thức</h3>
        <p className={styles.emptyDesc}>
          Môn học này chưa có chapter, topic và dạng bài trong dữ liệu backend.
        </p>
      </div>
    );
  }

  if (filtered.totalMatchedCount === 0 && filtered.isFiltered) {
    return (
      <div className={styles.emptyCard}>
        <h3 className={styles.emptyTitle}>Không tìm thấy lá tri thức phù hợp</h3>
        <p className={styles.emptyDesc}>
          Không có dạng bài nào khớp từ khóa hoặc trạng thái đã chọn.
        </p>
        {onResetFilters ? (
          <button type="button" className={styles.resetFiltersBtn} onClick={onResetFilters}>
            <RotateCcw size={15} /> Xóa bộ lọc
          </button>
        ) : null}
      </div>
    );
  }

  return (
    <section
      className={styles.livingTreeSection}
      aria-label={`Vũ trụ tri thức ${chapters.length} chương`}
    >
      {/* Top Bar Navigation: View Switcher & Quick Navigation */}
      <div className="flex items-center justify-between gap-3 mb-3 flex-wrap">
        <div className={styles.treeQuickNav} aria-label="Chọn nhanh chương">
          <button
            type="button"
            className={`${styles.quickNavButton} ${!focusTarget ? styles.quickNavButtonActive : ""}`}
            onClick={() => focusNode(null, true)}
          >
            <Orbit size={15} /> Toàn cảnh
          </button>
          {chapters.map((chapter, index) => (
            <button
              key={chapter.id}
              type="button"
              className={`${styles.quickNavButton} ${
                focusTarget?.chapterId === chapter.id ? styles.quickNavButtonActive : ""
              }`}
              onClick={() => focusNode(chapter.id, true)}
            >
              {index + 1}. {chapter.name}
            </button>
          ))}
        </div>

        {/* View Switcher & Theme Mode Controls */}
        <div className="flex items-center gap-2">
          <div className={styles.viewModeToggleGroup} role="radiogroup" aria-label="Chế độ hiển thị">
            <button
              type="button"
              role="radio"
              aria-checked={viewMode === "galaxy"}
              className={`${styles.viewModeBtn} ${
                viewMode === "galaxy" ? styles.viewModeBtnActive : ""
              }`}
              onClick={() => {
                setViewMode("galaxy");
                fitCamera();
              }}
            >
              <Sparkles size={14} /> Vũ Trụ Tri Thức
            </button>
            <button
              type="button"
              role="radio"
              aria-checked={viewMode === "tree"}
              className={`${styles.viewModeBtn} ${
                viewMode === "tree" ? styles.viewModeBtnActive : ""
              }`}
              onClick={() => {
                setViewMode("tree");
                fitCamera();
              }}
            >
              <TreePine size={14} /> Cây Sinh Thái
            </button>
          </div>

          {viewMode === "galaxy" ? (
            <button
              type="button"
              className="p-2 rounded-full border border-[var(--border-soft)] hover:bg-[var(--surface-glass)] text-[var(--text-secondary)] transition-all"
              onClick={() => setIsCosmicDark(!isCosmicDark)}
              title={isCosmicDark ? "Chuyển sang nền Tinh Vân Ngà Voi" : "Chuyển sang nền Vũ Trụ Lục Bảo"}
              aria-label="Đổi tông màu vũ trụ"
            >
              {isCosmicDark ? <Sun size={15} /> : <Moon size={15} />}
            </button>
          ) : null}
        </div>
      </div>

      {/* Main Viewport Container */}
      <div
        ref={viewportRef}
        className={`${styles.treeViewport} ${
          viewMode === "galaxy"
            ? isCosmicDark
              ? styles.galaxyNebulaDark
              : styles.galaxyNebulaLight
            : ""
        }`}
        data-testid="living-knowledge-tree"
      >
        <p className={styles.srOnly}>
          Dùng phím mũi tên để di chuyển, dấu cộng hoặc trừ để thu phóng, click vào ngôi sao để mở chi tiết dạng bài.
        </p>

        {/* Camera Controls Overlay */}
        <div className={styles.cameraControls} aria-label="Điều khiển góc nhìn">
          <button type="button" onClick={() => zoomBy(1.22)} aria-label="Phóng to">
            <Plus size={18} />
          </button>
          <button type="button" onClick={() => zoomBy(0.82)} aria-label="Thu nhỏ">
            <Minus size={18} />
          </button>
          <button type="button" onClick={fitCamera} aria-label="Xem toàn cảnh">
            <Maximize2 size={18} />
          </button>
        </div>

        <div className={styles.zoomReadout} aria-live="polite">
          {Math.round(camera.scale * 100)}%
        </div>

        {/* SVG Visualization Canvas */}
        <svg
          className={styles.treeCanvas}
          width="100%"
          height="100%"
          role="group"
          tabIndex={0}
          aria-label={`Bản đồ tri thức ${chapters.length} chương. Di chuyển bằng phím mũi tên.`}
          onKeyDown={handleKeyDown}
          onWheel={handleWheel}
          onPointerDown={handlePointerDown}
          onPointerMove={handlePointerMove}
          onPointerUp={handlePointerEnd}
          onPointerCancel={handlePointerEnd}
          onLostPointerCapture={handlePointerEnd}
        >
          <defs>
            {/* SVG Filters for glowing cosmic starlight */}
            <filter id="glowEffect" x="-50%" y="-50%" width="200%" height="200%">
              <feGaussianBlur in="SourceGraphic" stdDeviation="4.5" result="blur" />
              <feMerge>
                <feMergeNode in="blur" />
                <feMergeNode in="SourceGraphic" />
              </feMerge>
            </filter>
            <filter id="intenseGlow" x="-80%" y="-80%" width="260%" height="260%">
              <feGaussianBlur in="SourceGraphic" stdDeviation="10" result="blur1" />
              <feGaussianBlur in="SourceGraphic" stdDeviation="3.5" result="blur2" />
              <feMerge>
                <feMergeNode in="blur1" />
                <feMergeNode in="blur2" />
                <feMergeNode in="SourceGraphic" />
              </feMerge>
            </filter>

            {/* Galaxy Core radial gradients */}
            <radialGradient id="galaxy-core-mint" cx="50%" cy="50%" r="50%">
              <stop offset="0%" stopColor="#63c99a" stopOpacity="1" />
              <stop offset="45%" stopColor="#286955" stopOpacity="0.75" />
              <stop offset="100%" stopColor="#102e26" stopOpacity="0" />
            </radialGradient>
            <radialGradient id="galaxy-core-sky" cx="50%" cy="50%" r="50%">
              <stop offset="0%" stopColor="#5ca9d6" stopOpacity="1" />
              <stop offset="45%" stopColor="#205344" stopOpacity="0.75" />
              <stop offset="100%" stopColor="#102e26" stopOpacity="0" />
            </radialGradient>
            <radialGradient id="galaxy-core-violet" cx="50%" cy="50%" r="50%">
              <stop offset="0%" stopColor="#8578cf" stopOpacity="1" />
              <stop offset="45%" stopColor="#286955" stopOpacity="0.75" />
              <stop offset="100%" stopColor="#102e26" stopOpacity="0" />
            </radialGradient>

            {/* Tree mode legacy gradients */}
            <linearGradient id="living-trunk" x1="0" y1="0" x2="1" y2="0">
              <stop offset="0%" stopColor="#73543b" />
              <stop offset="0.48" stopColor="#a87950" />
              <stop offset="1" stopColor="#5a4232" />
            </linearGradient>
            <filter id="tree-shadow" x="-30%" y="-30%" width="160%" height="160%">
              <feDropShadow dx="0" dy="10" stdDeviation="10" floodColor="#173d30" floodOpacity="0.18" />
            </filter>
            <filter id="leaf-glow" x="-80%" y="-80%" width="260%" height="260%">
              <feDropShadow dx="0" dy="0" stdDeviation="5" floodColor="#a9e6c3" floodOpacity="0.62" />
            </filter>
          </defs>

          <g transform={`translate(${camera.x} ${camera.y}) scale(${camera.scale})`}>
            {viewMode === "galaxy" ? (
              /* ==============================================================
                 1. GALAXY CONSTELLATION RENDERING LAYER
                 ============================================================== */
              <g id="galaxyConstellationGroup">
                {/* 1.1 Prerequisite Starlight Beams Layer */}
                <g id="prerequisiteBeamsGroup">
                  {galaxyLayout.prerequisiteBeams.map((beam, index) => {
                    const isBeamDimmed = Boolean(
                      focusTarget &&
                        focusTarget.id !== beam.fromNodeId &&
                        focusTarget.id !== beam.toNodeId
                    );
                    return (
                      <path
                        key={`beam-${index}`}
                        d={beam.path}
                        fill="none"
                        stroke="#3bb9b0"
                        strokeWidth="2.2"
                        strokeOpacity={isBeamDimmed ? "0.15" : "0.75"}
                        className={styles.beamLine}
                        filter="url(#glowEffect)"
                      />
                    );
                  })}
                </g>

                {/* 1.2 Chapters (Galaxy Cores) Layer */}
                {galaxyLayout.cores.map((core, coreIndex) => {
                  const coreFocused = focusTarget?.chapterId === core.node.id;
                  const coreDimmed = Boolean(focusTarget && !coreFocused);
                  const coreFiltered = isFiltered && !visibleChapterIds.has(core.node.id);

                  const gradientId =
                    coreIndex % 3 === 0
                      ? "galaxy-core-mint"
                      : coreIndex % 3 === 1
                      ? "galaxy-core-sky"
                      : "galaxy-core-violet";

                  return (
                    <g
                      key={core.node.id}
                      className={`${coreDimmed || coreFiltered ? styles.treeDimmed : ""}`}
                    >
                      {/* Orbital dashed track around Core */}
                      <circle
                        cx={core.center.x}
                        cy={core.center.y}
                        r={core.orbitRadius}
                        fill="none"
                        stroke={isCosmicDark ? "rgba(255, 255, 255, 0.08)" : "rgba(29, 75, 61, 0.12)"}
                        strokeDasharray="4 8"
                      />

                      {/* Rotating galaxy dust halo */}
                      <ellipse
                        cx={core.center.x}
                        cy={core.center.y}
                        rx={core.radius * 2.8}
                        ry={core.radius * 1.5}
                        fill={`url(#${gradientId})`}
                        className={`${styles.galaxyCoreHalo} pointer-events-none`}
                        transform={`rotate(${coreIndex * 35} ${core.center.x} ${core.center.y})`}
                      />

                      {/* Galaxy Core Body */}
                      <circle
                        cx={core.center.x}
                        cy={core.center.y}
                        r={core.radius}
                        fill={isCosmicDark ? "#102e26" : "#fbfaf4"}
                        stroke={core.color}
                        strokeWidth="3.5"
                        filter="url(#glowEffect)"
                        className={styles.galaxyCoreNode}
                        role="button"
                        tabIndex={0}
                        aria-label={`Chương ${coreIndex + 1}: ${core.node.name}`}
                        onClick={() => handleNodeClick(() => focusNode(core.node.id, true))}
                        onKeyDown={(event) => keyboardActivate(event, () => focusNode(core.node.id, true))}
                      />

                      {/* Core Code Label */}
                      <text
                        x={core.center.x}
                        y={core.center.y + 5}
                        className={`${styles.galaxyLabel} ${styles.galaxyCoreLabelText}`}
                        style={{ fill: isCosmicDark ? "#ffffff" : "#173f34" }}
                      >
                        {core.node.code || `CH${coreIndex + 1}`}
                      </text>

                      {/* Core Title (Always horizontal, crisp typography) */}
                      <g
                        transform={`translate(${core.center.x} ${core.center.y + core.radius + 16})`}
                        className="cursor-pointer"
                        onClick={() => handleNodeClick(() => focusNode(core.node.id, true))}
                      >
                        <rect
                          x="-95"
                          y="0"
                          width="190"
                          height="36"
                          rx="18"
                          fill={isCosmicDark ? "rgba(16, 46, 38, 0.85)" : "rgba(255, 255, 255, 0.92)"}
                          stroke={core.color}
                          strokeWidth="1.2"
                          strokeOpacity="0.4"
                        />
                        <text
                          x="0"
                          y="18"
                          className={`${styles.galaxyLabel}`}
                          style={{
                            fill: isCosmicDark ? "#eef7f1" : "#173f34",
                            fontSize: "11px",
                            fontWeight: 700,
                          }}
                        >
                          {shortLabel(core.node.name, 24)}
                        </text>
                        <text
                          x="0"
                          y="29"
                          className={`${styles.galaxyLabel}`}
                          style={{
                            fill: isCosmicDark ? "#8dc8ae" : "#52675d",
                            fontSize: "9px",
                          }}
                        >
                          {core.planets.length} chủ đề &bull; {core.node.problemTypeCount} dạng bài
                        </text>
                      </g>

                      {/* 1.3 Topics (Planets) Layer */}
                      {core.planets.map((planet) => {
                        const planetFocused = focusTarget?.id === planet.node.id;
                        const planetInPath =
                          focusTarget?.kind === "leaf" && focusTarget.topicId === planet.node.id;
                        const planetDimmed = Boolean(
                          focusTarget && coreFocused && !planetFocused && !planetInPath
                        );
                        const planetFiltered = isFiltered && !visibleTopicIds.has(planet.node.id);

                        return (
                          <g
                            key={planet.node.id}
                            className={`${planetDimmed || planetFiltered ? styles.treeDimmed : ""}`}
                          >
                            {/* Radial connector arm from Core to Planet */}
                            <path
                              d={planet.connectorPath}
                              stroke={core.color}
                              strokeWidth="1.4"
                              strokeOpacity={isCosmicDark ? "0.3" : "0.22"}
                              fill="none"
                            />

                            {/* Orbit guide around planet */}
                            <circle
                              cx={planet.center.x}
                              cy={planet.center.y}
                              r="48"
                              fill="none"
                              stroke={isCosmicDark ? "rgba(255, 255, 255, 0.05)" : "rgba(29, 75, 61, 0.08)"}
                              strokeDasharray="2 4"
                            />

                            {/* Planet Body */}
                            <circle
                              cx={planet.center.x}
                              cy={planet.center.y}
                              r={planet.radius}
                              fill={isCosmicDark ? "#173f34" : "#f5f3e9"}
                              stroke={core.color}
                              strokeWidth="2.5"
                              filter="url(#glowEffect)"
                              className={styles.galaxyPlanetNode}
                              role="button"
                              tabIndex={0}
                              aria-label={`Chủ đề ${planet.node.name}`}
                              onClick={() => handleNodeClick(() => focusNode(planet.node.id, true))}
                              onKeyDown={(event) =>
                                keyboardActivate(event, () => focusNode(planet.node.id, true))
                              }
                            />

                            {/* Planet Title */}
                            <text
                              x={planet.center.x}
                              y={planet.center.y + planet.radius + 14}
                              className={`${styles.galaxyLabel} ${styles.galaxyPlanetLabelText}`}
                              style={{ fill: isCosmicDark ? "#cbe6f4" : "#205344" }}
                            >
                              {shortLabel(planet.node.name, 22)}
                            </text>

                            {/* 1.4 Problem Types (Stars) Layer */}
                            {planet.stars.map((star) => {
                              const isSelected = selectedId === star.node.id;
                              const starFiltered = isFiltered && !visibleLeafIds.has(star.node.id);
                              const starDimmed = Boolean(focusTarget?.kind === "leaf" && !isSelected);
                              const stateLabel = getMasteryStateLabel(star.node.state);

                              return (
                                <g
                                  key={star.node.id}
                                  className={`${
                                    starDimmed || starFiltered ? styles.treeDimmed : ""
                                  }`}
                                >
                                  {/* Twig line connecting Planet to Star */}
                                  <path
                                    d={star.twigPath}
                                    stroke={core.color}
                                    strokeWidth="1"
                                    strokeOpacity="0.35"
                                    fill="none"
                                  />

                                  {/* Star Body */}
                                  <circle
                                    cx={star.center.x}
                                    cy={star.center.y}
                                    r={star.radius}
                                    fill={star.color}
                                    filter={star.glowFilter}
                                    className={`${styles.galaxyStarNode} ${
                                      isSelected ? styles.galaxyStarSelected : ""
                                    }`}
                                    role="button"
                                    tabIndex={0}
                                    aria-label={`${star.node.name}: ${stateLabel}`}
                                    aria-pressed={isSelected}
                                    onClick={() =>
                                      handleNodeClick(() => focusNode(star.node.id, true))
                                    }
                                    onKeyDown={(event) =>
                                      keyboardActivate(event, () => focusNode(star.node.id, true))
                                    }
                                  >
                                    <title>{`${star.node.name} · ${stateLabel}`}</title>
                                  </circle>

                                  {/* Star Label visible when zoomed in */}
                                  {!lowDetail ? (
                                    <text
                                      x={star.center.x}
                                      y={star.center.y + star.radius + 12}
                                      className={`${styles.galaxyLabel} ${styles.galaxyStarLabelText}`}
                                      style={{ fill: isCosmicDark ? "#dcefe5" : "#173f34" }}
                                    >
                                      {shortLabel(star.node.name, 18)}
                                    </text>
                                  ) : null}
                                </g>
                              );
                            })}
                          </g>
                        );
                      })}
                    </g>
                  );
                })}
              </g>
            ) : (
              /* ==============================================================
                 2. LIVING TREE RENDERING LAYER (LEGACY COMPATIBILITY)
                 ============================================================== */
              <g id="livingTreeGroup">
                <g aria-hidden="true" className={styles.treeAtmosphere}>
                  <ellipse
                    cx={treeLayout.centerX}
                    cy={treeLayout.baseY + 38}
                    rx={Math.min(560, treeLayout.width * 0.3)}
                    ry="62"
                  />
                  <circle cx={treeLayout.centerX - 280} cy="210" r="120" />
                  <circle cx={treeLayout.centerX + 250} cy="180" r="145" />
                </g>
                <g aria-hidden="true" className={styles.rootGroup}>
                  {treeLayout.roots.map((root, index) => (
                    <path key={index} d={root.path} />
                  ))}
                </g>
                <path
                  d={treeLayout.trunkPath}
                  fill="url(#living-trunk)"
                  className={styles.trunk}
                  filter="url(#tree-shadow)"
                />
                <text
                  x={treeLayout.centerX}
                  y={treeLayout.baseY - 34}
                  textAnchor="middle"
                  className={styles.trunkLabel}
                >
                  {shortLabel(subjectName, 24)}
                </text>
                {treeLayout.chapters.map((chapter, chapterIndex) => {
                  const chapterFocused = focusTarget?.chapterId === chapter.node.id;
                  const chapterDimmed = Boolean(focusTarget && !chapterFocused);
                  const chapterFiltered = isFiltered && !visibleChapterIds.has(chapter.node.id);
                  return (
                    <g
                      key={chapter.node.id}
                      className={`${styles.chapterBranchGroup} ${
                        chapterDimmed || chapterFiltered ? styles.treeDimmed : ""
                      }`}
                    >
                      <path
                        d={chapter.branch.path}
                        className={styles.chapterBranchShadow}
                        aria-hidden="true"
                      />
                      <path
                        d={chapter.branch.path}
                        className={`${styles.chapterBranch} ${
                          chapterFocused ? styles.pathHighlighted : ""
                        }`}
                        aria-hidden="true"
                      />
                      <path
                        d={chapter.branch.path}
                        className={styles.branchHitArea}
                        role="button"
                        tabIndex={0}
                        data-tree-node="chapter"
                        data-node-id={chapter.node.id}
                        aria-label={`Tập trung cành chương ${chapter.node.name}`}
                        onClick={() => handleNodeClick(() => focusNode(chapter.node.id, true))}
                        onKeyDown={(event) =>
                          keyboardActivate(event, () => focusNode(chapter.node.id, true))
                        }
                      />
                      <g
                        className={styles.chapterLabel}
                        data-tree-node="chapter"
                        data-node-id={chapter.node.id}
                        transform={`translate(${
                          chapter.labelBounds.x + chapter.labelBounds.width / 2
                        } ${chapter.labelBounds.y + chapter.labelBounds.height / 2})`}
                        role="button"
                        tabIndex={0}
                        aria-label={`Chương ${chapterIndex + 1}: ${chapter.node.name}`}
                        onClick={() => handleNodeClick(() => focusNode(chapter.node.id, true))}
                        onKeyDown={(event) =>
                          keyboardActivate(event, () => focusNode(chapter.node.id, true))
                        }
                      >
                        <text textAnchor="middle">{shortLabel(chapter.node.name, 30)}</text>
                        <text textAnchor="middle" y="20" className={styles.chapterMeta}>
                          {chapter.node.topics.length} chủ đề &bull; {chapter.node.problemTypeCount} lá
                        </text>
                      </g>
                      {chapter.topics.map((topic) => {
                        const topicFocused =
                          focusTarget?.kind === "topic" && focusTarget.id === topic.node.id;
                        const topicInPath =
                          focusTarget?.kind === "leaf" && focusTarget.topicId === topic.node.id;
                        const topicDimmed = Boolean(
                          focusTarget &&
                            chapterFocused &&
                            !topicFocused &&
                            !topicInPath &&
                            focusTarget.kind !== "chapter"
                        );
                        const topicFiltered = isFiltered && !visibleTopicIds.has(topic.node.id);
                        return (
                          <g
                            key={topic.node.id}
                            className={`${styles.topicBranchGroup} ${
                              topicDimmed || topicFiltered ? styles.treeDimmed : ""
                            }`}
                          >
                            <path
                              d={topic.branch.path}
                              className={`${styles.topicBranch} ${
                                topicFocused || topicInPath ? styles.pathHighlighted : ""
                              }`}
                              aria-hidden="true"
                            />
                            <path
                              d={topic.branch.path}
                              className={styles.branchHitArea}
                              role="button"
                              tabIndex={0}
                              data-tree-node="topic"
                              data-node-id={topic.node.id}
                              aria-label={`Tập trung nhánh chủ đề ${topic.node.name}`}
                              onClick={() => handleNodeClick(() => focusNode(topic.node.id, true))}
                              onKeyDown={(event) =>
                                keyboardActivate(event, () => focusNode(topic.node.id, true))
                              }
                            />
                            <g
                              className={styles.topicLabel}
                              data-tree-node="topic"
                              data-node-id={topic.node.id}
                              transform={`translate(${
                                topic.labelBounds.x + topic.labelBounds.width / 2
                              } ${topic.labelBounds.y + topic.labelBounds.height / 2})`}
                              role="button"
                              tabIndex={0}
                              aria-label={`Chủ đề ${topic.node.name}`}
                              onClick={() => handleNodeClick(() => focusNode(topic.node.id, true))}
                              onKeyDown={(event) =>
                                keyboardActivate(event, () => focusNode(topic.node.id, true))
                              }
                            >
                              <text textAnchor="middle">{shortLabel(topic.node.name, 28)}</text>
                              <text textAnchor="middle" y="17" className={styles.topicMeta}>
                                {topic.leaves.length} dạng bài
                              </text>
                            </g>
                            {topic.leaves.map((leaf) => {
                              const selected = selectedId === leaf.node.id;
                              const leafFiltered = isFiltered && !visibleLeafIds.has(leaf.node.id);
                              const leafDimmed = Boolean(focusTarget?.kind === "leaf" && !selected);
                              const stateLabel = getMasteryStateLabel(leaf.node.state);
                              return (
                                <g
                                  key={leaf.node.id}
                                  className={`${styles.semanticLeafGroup} ${
                                    lowDetail ? styles.semanticLeafLowDetail : ""
                                  } ${leafDimmed || leafFiltered ? styles.treeDimmed : ""}`}
                                >
                                  <path
                                    d={leaf.twig.path}
                                    className={`${styles.twig} ${
                                      selected ? styles.pathHighlighted : ""
                                    }`}
                                    aria-hidden="true"
                                  />
                                  <g
                                    transform={`translate(${leaf.center.x} ${leaf.center.y}) rotate(${leaf.rotation})`}
                                    role="button"
                                    tabIndex={0}
                                    data-tree-node="leaf"
                                    data-node-id={leaf.node.id}
                                    aria-label={`${leaf.node.name}: ${stateLabel}${
                                      leaf.node.masteryScore === undefined
                                        ? ", chưa có điểm đo"
                                        : `, ${leaf.node.masteryScore}%`
                                    }`}
                                    aria-pressed={selected}
                                    className={`${styles.semanticLeaf} ${
                                      styles[`leaf_${leaf.node.state}`]
                                    } ${selected ? styles.leafSelected : ""}`}
                                    onClick={() => handleNodeClick(() => focusNode(leaf.node.id, true))}
                                    onKeyDown={(event) =>
                                      keyboardActivate(event, () => focusNode(leaf.node.id, true))
                                    }
                                  >
                                    <title>{`${leaf.node.name} · ${stateLabel}`}</title>
                                    <path
                                      d="M 0 -14 C 20 -15 27 2 0 17 C -27 2 -20 -15 0 -14 Z"
                                      className={styles.leafShape}
                                    />
                                    {leaf.hasFruit ? (
                                      <g
                                        className={styles.masteryFruit}
                                        data-tree-fruit="true"
                                        aria-hidden="true"
                                        transform="translate(15 -14) rotate(-20)"
                                      >
                                        <circle r="8" />
                                      </g>
                                    ) : null}
                                  </g>
                                </g>
                              );
                            })}
                          </g>
                        );
                      })}
                    </g>
                  );
                })}
              </g>
            )}
          </g>
        </svg>
      </div>

      {/* Legend Footer */}
      <div className={styles.treeLegend} aria-label="Chú giải trạng thái kiến thức">
        <span>
          <i
            style={{
              display: "inline-block",
              width: "11px",
              height: "11px",
              borderRadius: "50%",
              background: "#d8a143",
              boxShadow: "0 0 8px #d8a143",
            }}
          />{" "}
          Thành thạo (Mastered)
        </span>
        <span>
          <i
            style={{
              display: "inline-block",
              width: "11px",
              height: "11px",
              borderRadius: "50%",
              background: "#3bb9b0",
              boxShadow: "0 0 8px #3bb9b0",
            }}
          />{" "}
          Đang rèn luyện (In Progress)
        </span>
        <span>
          <i
            style={{
              display: "inline-block",
              width: "11px",
              height: "11px",
              borderRadius: "50%",
              background: "#de7d6b",
              boxShadow: "0 0 8px #de7d6b",
            }}
          />{" "}
          Cần củng cố / Đến hạn ôn
        </span>
        <span>
          <i
            style={{
              display: "inline-block",
              width: "11px",
              height: "11px",
              borderRadius: "50%",
              background: "rgb(156 163 175 / 60%)",
            }}
          />{" "}
          Chưa học (Not Started)
        </span>
      </div>
      <span className={styles.srOnly}>
        Mức zoom từ {GALAXY_DIMENSIONS.minScale * 100}% đến {GALAXY_DIMENSIONS.maxScale * 100}%.
      </span>
    </section>
  );
}
