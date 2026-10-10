"use client";

import { Maximize2, Minus, Plus, RotateCcw, TreePine } from "lucide-react";
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
import type { KnowledgeChapterNode, KnowledgeProblemTypeNode, KnowledgeStatusFilter } from "../types";
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

interface GestureStart { camera: TreeCamera; midpoint: TreePoint; distance: number }
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
  const viewportRef = useRef<HTMLDivElement>(null);
  const pointersRef = useRef(new Map<number, TreePoint>());
  const lastPanPointRef = useRef<TreePoint | null>(null);
  const gestureStartRef = useRef<GestureStart | null>(null);
  const pointerDownPosRef = useRef<TreePoint | null>(null);
  const isDraggingRef = useRef(false);
  const layout = useMemo(() => buildLivingTreeLayout(chapters), [chapters]);
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
    () => new Set(filtered.filteredChapters.flatMap((chapter) => chapter.topics.flatMap((topic) => topic.problemTypes.map((problemType) => problemType.id)))),
    [filtered.filteredChapters]
  );
  const visibleTopicIds = useMemo(
    () => new Set(filtered.filteredChapters.flatMap((chapter) => chapter.topics.map((topic) => topic.id))),
    [filtered.filteredChapters]
  );
  const visibleChapterIds = useMemo(
    () => new Set(filtered.filteredChapters.map((chapter) => chapter.id)),
    [filtered.filteredChapters]
  );
  const isFiltered = Boolean(searchQuery.trim()) || statusFilter !== "ALL";
  const lowDetail = camera.scale < 0.4;

  const fitTree = useCallback(() => {
    if (viewport.width <= 1 || viewport.height <= 1) return;
    const padding = viewport.width < 440 ? 16 : viewport.width < 640 ? 24 : 34;
    setCamera(fitTreeCamera(viewport, layout.bounds, padding, 0.92));
    setFocusTarget(null);
  }, [layout.bounds, viewport]);

  const focusBounds = useCallback((bounds: TreeRect, maxScale = 1.25) => {
    if (viewport.width <= 1 || viewport.height <= 1) return;
    setCamera(focusTreeCamera(viewport, bounds, viewport.width < 640 ? 54 : 92, maxScale));
  }, [viewport]);

  const writeNodeToHistory = useCallback((nodeId: string | null) => {
    const url = new URL(window.location.href);
    if (nodeId) url.searchParams.set("node", nodeId);
    else url.searchParams.delete("node");
    window.history.pushState(null, "", `${url.pathname}${url.search}${url.hash}`);
  }, []);

  const focusNode = useCallback((nodeId: string | null, updateHistory: boolean, revealLeaf = true) => {
    if (!nodeId) {
      onClearSelection();
      fitTree();
      if (updateHistory) writeNodeToHistory(null);
      return;
    }
    for (const chapter of layout.chapters) {
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
          setFocusTarget({ kind: "leaf", id: nodeId, chapterId: chapter.node.id, topicId: topic.node.id });
          if (updateHistory) writeNodeToHistory(nodeId);

          const currentCamera = cameraRef.current;
          const currentViewport = viewportStateRef.current;
          const screenX = currentCamera.x + leaf.center.x * currentCamera.scale;
          const screenY = currentCamera.y + leaf.center.y * currentCamera.scale;
          const isAlreadyVisible =
            currentCamera.scale >= 0.75 &&
            screenX >= 60 &&
            screenX <= currentViewport.width - 60 &&
            screenY >= 60 &&
            screenY <= currentViewport.height - 60;

          if (!isAlreadyVisible) {
            focusBounds({ x: leaf.center.x - 150, y: leaf.center.y - 115, width: 300, height: 230 }, 1.45);
          }
          return;
        }
      }
    }
  }, [fitTree, focusBounds, layout.chapters, onClearSelection, onSelectProblemType, writeNodeToHistory]);

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

  useEffect(() => {
    if (viewport.width <= 1 || viewport.height <= 1 || hasCameraReady) return;
    const padding = viewport.width < 440 ? 16 : viewport.width < 640 ? 24 : 34;
    setCamera(fitTreeCamera(viewport, layout.bounds, padding, 0.92));
    setHasCameraReady(true);
    if (initialNodeId) requestAnimationFrame(() => focusNode(initialNodeId, false));
  }, [focusNode, hasCameraReady, initialNodeId, layout.bounds, viewport]);

  useEffect(() => {
    const handlePopState = () => focusNode(new URL(window.location.href).searchParams.get("node"), false);
    window.addEventListener("popstate", handlePopState);
    return () => window.removeEventListener("popstate", handlePopState);
  }, [focusNode]);

  useEffect(() => {
    if (!selectedId && focusTarget?.kind === "leaf") {
      setFocusTarget(null);
    }
  }, [selectedId, focusTarget]);

  useEffect(() => {
    if (!searchQuery.trim()) return;
    const firstResult = filtered.filteredChapters.flatMap((chapter) => chapter.topics).flatMap((topic) => topic.problemTypes)[0];
    if (!firstResult) return;
    for (const chapter of layout.chapters) {
      for (const topic of chapter.topics) {
        const leaf = topic.leaves.find((candidate) => candidate.node.id === firstResult.id);
        if (leaf) {
          focusBounds({ x: leaf.center.x - 150, y: leaf.center.y - 115, width: 300, height: 230 }, 1.25);
          return;
        }
      }
    }
  }, [filtered.filteredChapters, focusBounds, layout.chapters, searchQuery]);

  const zoomBy = (factor: number) => {
    setCamera((current) => zoomTreeCameraAt(current, { x: viewport.width / 2, y: viewport.height / 2 }, current.scale * factor));
  };

  const handleWheel = (event: ReactWheelEvent<SVGSVGElement>) => {
    event.preventDefault();
    const rect = event.currentTarget.getBoundingClientRect();
    setCamera((current) => zoomTreeCameraAt(current, { x: event.clientX - rect.left, y: event.clientY - rect.top }, current.scale * Math.exp(-event.deltaY * 0.0014)));
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
      gestureStartRef.current = { camera, midpoint: midpoint(first, second), distance: distance(first, second) };
    }
  };

  const handlePointerMove = (event: ReactPointerEvent<SVGSVGElement>) => {
    if (!pointersRef.current.has(event.pointerId)) return;
    const nextPoint = { x: event.clientX, y: event.clientY };
    pointersRef.current.set(event.pointerId, nextPoint);
    if (pointerDownPosRef.current) {
      const dist = Math.hypot(nextPoint.x - pointerDownPosRef.current.x, nextPoint.y - pointerDownPosRef.current.y);
      if (dist > 6) {
        isDraggingRef.current = true;
      }
    }
    if (pointersRef.current.size === 1 && lastPanPointRef.current) {
      const previous = lastPanPointRef.current;
      setCamera((current) => panTreeCamera(current, { x: nextPoint.x - previous.x, y: nextPoint.y - previous.y }));
      lastPanPointRef.current = nextPoint;
    } else if (pointersRef.current.size === 2 && gestureStartRef.current) {
      const [first, second] = [...pointersRef.current.values()];
      const start = gestureStartRef.current;
      const currentMidpoint = midpoint(first, second);
      const scaled = zoomTreeCameraAt(start.camera, start.midpoint, start.camera.scale * (distance(first, second) / Math.max(1, start.distance)));
      setCamera({ ...scaled, x: scaled.x + currentMidpoint.x - start.midpoint.x, y: scaled.y + currentMidpoint.y - start.midpoint.y });
    }
  };

  const handlePointerEnd = (event: ReactPointerEvent<SVGSVGElement>) => {
    pointersRef.current.delete(event.pointerId);
    gestureStartRef.current = null;
    lastPanPointRef.current = pointersRef.current.size === 1 ? [...pointersRef.current.values()][0] : null;
    if (pointersRef.current.size === 0) {
      pointerDownPosRef.current = null;
    }
  };

  const handleNodeClick = (action: () => void) => {
    if (isDraggingRef.current) return;
    action();
  };

  const handleTreeKeyDown = (event: ReactKeyboardEvent<SVGSVGElement>) => {
    const panDistance = 52;
    if (event.key === "ArrowLeft") setCamera((current) => panTreeCamera(current, { x: panDistance, y: 0 }));
    else if (event.key === "ArrowRight") setCamera((current) => panTreeCamera(current, { x: -panDistance, y: 0 }));
    else if (event.key === "ArrowUp") setCamera((current) => panTreeCamera(current, { x: 0, y: panDistance }));
    else if (event.key === "ArrowDown") setCamera((current) => panTreeCamera(current, { x: 0, y: -panDistance }));
    else if (event.key === "+" || event.key === "=") zoomBy(1.16);
    else if (event.key === "-") zoomBy(0.86);
    else if (event.key === "0") fitTree();
    else return;
    event.preventDefault();
  };

  if (chapters.length === 0) {
    return <div className={styles.emptyCard}><TreePine size={38} aria-hidden="true" /><h3 className={styles.emptyTitle}>Chưa có cấu trúc cây tri thức</h3><p className={styles.emptyDesc}>Môn học này chưa có chapter, topic và dạng bài trong dữ liệu backend.</p></div>;
  }
  if (filtered.totalMatchedCount === 0 && filtered.isFiltered) {
    return <div className={styles.emptyCard}><h3 className={styles.emptyTitle}>Không tìm thấy lá tri thức phù hợp</h3><p className={styles.emptyDesc}>Không có dạng bài nào khớp từ khóa hoặc trạng thái đã chọn.</p>{onResetFilters ? <button type="button" className={styles.resetFiltersBtn} onClick={onResetFilters}><RotateCcw size={15} /> Xóa bộ lọc</button> : null}</div>;
  }

  return (
    <section className={styles.livingTreeSection} aria-label={`Cây tri thức ${chapters.length} chương`}>
      <div className={styles.treeQuickNav} aria-label="Chọn nhanh chương">
        <button type="button" className={styles.quickNavButton} onClick={() => focusNode(null, true)}><TreePine size={15} /> Toàn cây</button>
        {layout.chapters.map((chapter, index) => <button key={chapter.node.id} type="button" className={`${styles.quickNavButton} ${focusTarget?.chapterId === chapter.node.id ? styles.quickNavButtonActive : ""}`} onClick={() => focusNode(chapter.node.id, true)}>{index + 1}. {chapter.node.name}</button>)}
      </div>
      <div ref={viewportRef} className={styles.treeViewport} data-testid="living-knowledge-tree">
        <p className={styles.srOnly}>Dùng Tab để đi qua cành và lá. Nhấn Enter để tập trung. Dùng các nút camera để điều khiển cây.</p>
        <div className={styles.cameraControls} aria-label="Điều khiển cây tri thức">
          <button type="button" onClick={() => zoomBy(1.22)} aria-label="Phóng to"><Plus size={18} /></button>
          <button type="button" onClick={() => zoomBy(0.82)} aria-label="Thu nhỏ"><Minus size={18} /></button>
          <button type="button" onClick={fitTree} aria-label="Hiển thị toàn cây"><Maximize2 size={18} /></button>
        </div>
        <div className={styles.zoomReadout} aria-live="polite">{Math.round(camera.scale * 100)}%</div>
        <svg className={styles.treeCanvas} width="100%" height="100%" role="group" tabIndex={0} aria-label={`Cây cổ thụ tri thức ${chapters.length} cành chương và ${layout.leaves.length} lá dạng bài. Dùng các phím mũi tên để di chuyển, dấu cộng hoặc trừ để thu phóng.`} onKeyDown={handleTreeKeyDown} onWheel={handleWheel} onPointerDown={handlePointerDown} onPointerMove={handlePointerMove} onPointerUp={handlePointerEnd} onPointerCancel={handlePointerEnd} onLostPointerCapture={handlePointerEnd}>
          <defs>
            <linearGradient id="living-trunk" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stopColor="#73543b" /><stop offset="0.48" stopColor="#a87950" /><stop offset="1" stopColor="#5a4232" /></linearGradient>
            <linearGradient id="living-branch" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stopColor="#79573d" /><stop offset="1" stopColor="#9d744e" /></linearGradient>
            <filter id="tree-shadow" x="-30%" y="-30%" width="160%" height="160%"><feDropShadow dx="0" dy="10" stdDeviation="10" floodColor="#173d30" floodOpacity="0.18" /></filter>
            <filter id="leaf-glow" x="-80%" y="-80%" width="260%" height="260%"><feDropShadow dx="0" dy="0" stdDeviation="5" floodColor="#a9e6c3" floodOpacity="0.62" /></filter>
          </defs>
          <g transform={`translate(${camera.x} ${camera.y}) scale(${camera.scale})`}>
            <g aria-hidden="true" className={styles.treeAtmosphere}><ellipse cx={layout.centerX} cy={layout.baseY + 38} rx={Math.min(560, layout.width * 0.3)} ry="62" /><circle cx={layout.centerX - 280} cy="210" r="120" /><circle cx={layout.centerX + 250} cy="180" r="145" /></g>
            <g aria-hidden="true" className={styles.rootGroup}>{layout.roots.map((root, index) => <path key={index} d={root.path} />)}</g>
            <path d={layout.trunkPath} fill="url(#living-trunk)" className={styles.trunk} filter="url(#tree-shadow)" />
            <text x={layout.centerX} y={layout.baseY - 34} textAnchor="middle" className={styles.trunkLabel}>{shortLabel(subjectName, 24)}</text>
            {layout.chapters.map((chapter, chapterIndex) => {
              const chapterFocused = focusTarget?.chapterId === chapter.node.id;
              const chapterDimmed = Boolean(focusTarget && !chapterFocused);
              const chapterFiltered = isFiltered && !visibleChapterIds.has(chapter.node.id);
              return <g key={chapter.node.id} className={`${styles.chapterBranchGroup} ${chapterDimmed || chapterFiltered ? styles.treeDimmed : ""}`}>
                <path d={chapter.branch.path} className={styles.chapterBranchShadow} aria-hidden="true" />
                <path d={chapter.branch.path} className={`${styles.chapterBranch} ${chapterFocused ? styles.pathHighlighted : ""}`} aria-hidden="true" />
                <path d={chapter.branch.path} className={styles.branchHitArea} role="button" tabIndex={0} data-tree-node="chapter" data-node-id={chapter.node.id} aria-label={`Tập trung cành chương ${chapter.node.name}`} onClick={() => handleNodeClick(() => focusNode(chapter.node.id, true))} onKeyDown={(event) => keyboardActivate(event, () => focusNode(chapter.node.id, true))} />
                <g className={styles.chapterLabel} data-tree-node="chapter" data-node-id={chapter.node.id} transform={`translate(${chapter.labelBounds.x + chapter.labelBounds.width / 2} ${chapter.labelBounds.y + chapter.labelBounds.height / 2})`} role="button" tabIndex={0} aria-label={`Chương ${chapterIndex + 1}: ${chapter.node.name}`} onClick={() => handleNodeClick(() => focusNode(chapter.node.id, true))} onKeyDown={(event) => keyboardActivate(event, () => focusNode(chapter.node.id, true))}>
                  <text textAnchor="middle">{shortLabel(chapter.node.name, 30)}</text>
                  <text textAnchor="middle" y="20" className={styles.chapterMeta}>{chapter.node.topics.length} chủ đề · {chapter.node.problemTypeCount} lá</text>
                </g>
                {chapter.topics.map((topic) => {
                  const topicFocused = focusTarget?.kind === "topic" && focusTarget.id === topic.node.id;
                  const topicInPath = focusTarget?.kind === "leaf" && focusTarget.topicId === topic.node.id;
                  const topicDimmed = Boolean(focusTarget && chapterFocused && !topicFocused && !topicInPath && focusTarget.kind !== "chapter");
                  const topicFiltered = isFiltered && !visibleTopicIds.has(topic.node.id);
                  const canopyScale = Math.max(0.72, Math.sqrt(Math.max(1, topic.leaves.length)) * 0.5);
                  return <g key={topic.node.id} className={`${styles.topicBranchGroup} ${topicDimmed || topicFiltered ? styles.treeDimmed : ""}`}>
                    <path d={topic.branch.path} className={`${styles.topicBranch} ${topicFocused || topicInPath ? styles.pathHighlighted : ""}`} aria-hidden="true" />
                    <path d={topic.branch.path} className={styles.branchHitArea} role="button" tabIndex={0} data-tree-node="topic" data-node-id={topic.node.id} aria-label={`Tập trung nhánh chủ đề ${topic.node.name}`} onClick={() => handleNodeClick(() => focusNode(topic.node.id, true))} onKeyDown={(event) => keyboardActivate(event, () => focusNode(topic.node.id, true))} />
                    <g className={styles.topicCanopy} data-tree-node="topic-canopy" data-node-id={topic.node.id} transform={`translate(${topic.center.x} ${topic.center.y - 18})`} role="button" tabIndex={0} aria-label={`Nhánh chủ đề ${topic.node.name}, ${topic.leaves.length} dạng bài. Nhấn để phóng to xem lá.`} onClick={() => handleNodeClick(() => focusNode(topic.node.id, true))} onKeyDown={(event) => keyboardActivate(event, () => focusNode(topic.node.id, true))}>
                      <g className={styles.decorativeFoliage} aria-hidden="true" transform={`scale(${canopyScale})`}>
                        <path className={styles.canopyMass} d="M -82 7 C -83 -30 -49 -55 -15 -36 C 4 -72 55 -57 62 -20 C 96 -9 96 34 62 45 C 36 65 7 55 -7 42 C -42 59 -83 41 -82 7 Z" />
                        <path className={styles.decorativeLeaf} d="M -52 -10 C -35 -34 -10 -24 -18 6 C -38 22 -57 11 -52 -10 Z" />
                        <path className={styles.decorativeLeaf} d="M -8 -29 C 12 -52 37 -31 23 -5 C 1 8 -17 -8 -8 -29 Z" />
                        <path className={styles.decorativeLeaf} d="M 35 4 C 55 -20 79 -2 65 24 C 43 35 27 23 35 4 Z" />
                        <path className={styles.decorativeLeaf} d="M -19 24 C 1 3 24 19 12 43 C -9 54 -28 43 -19 24 Z" />
                      </g>
                    </g>
                    <g className={styles.topicLabel} data-tree-node="topic" data-node-id={topic.node.id} transform={`translate(${topic.labelBounds.x + topic.labelBounds.width / 2} ${topic.labelBounds.y + topic.labelBounds.height / 2})`} role="button" tabIndex={0} aria-label={`Chủ đề ${topic.node.name}`} onClick={() => handleNodeClick(() => focusNode(topic.node.id, true))} onKeyDown={(event) => keyboardActivate(event, () => focusNode(topic.node.id, true))}>
                      <text textAnchor="middle">{shortLabel(topic.node.name, 28)}</text><text textAnchor="middle" y="17" className={styles.topicMeta}>{topic.leaves.length} dạng bài</text>
                    </g>
                    {topic.leaves.map((leaf) => {
                      const selected = selectedId === leaf.node.id;
                      const leafFiltered = isFiltered && !visibleLeafIds.has(leaf.node.id);
                      const leafDimmed = Boolean(focusTarget?.kind === "leaf" && !selected);
                      const stateLabel = getMasteryStateLabel(leaf.node.state);
                      return <g key={leaf.node.id} className={`${styles.semanticLeafGroup} ${lowDetail ? styles.semanticLeafLowDetail : ""} ${leafDimmed || leafFiltered ? styles.treeDimmed : ""}`}>
                        <path d={leaf.twig.path} className={`${styles.twig} ${selected ? styles.pathHighlighted : ""}`} aria-hidden="true" />
                        <g transform={`translate(${leaf.center.x} ${leaf.center.y}) rotate(${leaf.rotation})`} role="button" tabIndex={0} data-tree-node="leaf" data-node-id={leaf.node.id} aria-label={`${leaf.node.name}: ${stateLabel}${leaf.node.masteryScore === undefined ? ", chưa có điểm đo" : `, ${leaf.node.masteryScore}%`}`} aria-pressed={selected} className={`${styles.semanticLeaf} ${styles[`leaf_${leaf.node.state}`]} ${selected ? styles.leafSelected : ""}`} onClick={() => handleNodeClick(() => focusNode(leaf.node.id, true))} onKeyDown={(event) => keyboardActivate(event, () => focusNode(leaf.node.id, true))}>
                          <title>{`${leaf.node.name} · ${stateLabel}`}</title><path d="M 0 -14 C 20 -15 27 2 0 17 C -27 2 -20 -15 0 -14 Z" className={styles.leafShape} /><path d="M -14 5 C -5 2 5 -2 15 -8" className={styles.leafVein} aria-hidden="true" />
                          {leaf.hasFruit ? <g className={styles.masteryFruit} data-tree-fruit="true" aria-hidden="true" transform="translate(15 -14) rotate(-20)"><circle r="8" /><path d="M 0 -8 Q 4 -15 10 -13" /></g> : null}
                          {leaf.node.state === "REVIEW_DUE" ? <circle className={styles.reviewDew} cx="-14" cy="-8" r="4" aria-hidden="true" /> : null}
                          <g className={styles.leafTooltip} transform={`rotate(${-leaf.rotation}) translate(0 -40)`} aria-hidden="true"><rect x="-95" y="-27" width="190" height="42" rx="15" /><text textAnchor="middle" y="-8">{shortLabel(leaf.node.name, 30)}</text><text textAnchor="middle" y="7" className={styles.tooltipMeta}>{stateLabel}</text></g>
                        </g>
                      </g>;
                    })}
                  </g>;
                })}
              </g>;
            })}
          </g>
        </svg>
      </div>
      <div className={styles.treeLegend} aria-label="Chú giải trạng thái lá">
        <span><i className={styles.legendMastered} /> Thành thạo · có trái</span><span><i className={styles.legendLearning} /> Đang phát triển</span><span><i className={styles.legendWeak} /> Cần cải thiện</span><span><i className={styles.legendReview} /> Đến hạn ôn</span><span><i className={styles.legendNotStarted} /> Lá non · chưa học</span>
      </div>
      <span className={styles.srOnly}>Mức zoom từ {LIVING_TREE_DIMENSIONS.minScale * 100}% đến {LIVING_TREE_DIMENSIONS.maxScale * 100}%.</span>
    </section>
  );
}
