"use client";

import { useMemo, useState, useRef, useEffect, useCallback } from "react";
import type { TheoryNode } from "./api";
import { latexToReadable } from "./markmap-tree";

export interface TheoryBilateralMindmapProps {
  nodes: TheoryNode[];
  selectedNodeId?: string | null;
  scopeId?: string;
  onSelectNode?: (id: string) => void;
  onEditNode?: (id: string) => void;
}

interface LayoutItem {
  node: TheoryNode;
  x: number;
  y: number;
  width: number;
  height: number;
  depth: number;
  direction: 1 | -1; // 1 = right, -1 = left
  color: string;
  hasChildren: boolean;
  isCollapsed: boolean;
  childCount: number;
}

interface LinkItem {
  id: string;
  sourceX: number;
  sourceY: number;
  targetX: number;
  targetY: number;
  color: string;
  direction: 1 | -1;
  depth: number;
}

const SECTION_PALETTE = [
  "#059669", // Emerald
  "#0284c7", // Sky blue
  "#7c3aed", // Violet
  "#d97706", // Amber
  "#e11d48", // Rose
  "#2563eb", // Royal blue
  "#0d9488", // Teal
  "#9333ea", // Purple
];

interface NodePreviewData {
  subtitle?: string;
  formula?: string;
  badge?: string;
}

function getNodePreview(node: TheoryNode): NodePreviewData {
  if (node.latex && node.latex.trim()) {
    const readable = latexToReadable(node.latex);
    return { formula: readable || node.latex.trim() };
  }
  if (node.learning_steps && node.learning_steps.length > 0) {
    return { badge: `📝 ${node.learning_steps.length} bước giải` };
  }
  if (node.body && node.body.trim()) {
    const clean = node.body.replace(/[\n\r]+/g, " ").replace(/\s+/g, " ").trim();
    if (clean.length > 0 && clean !== node.title) {
      const truncated = clean.length > 48 ? clean.slice(0, 45) + "..." : clean;
      return { subtitle: truncated };
    }
  }
  return {};
}

function getNodeDimensions(node: TheoryNode, isRoot: boolean): { width: number; height: number } {
  if (isRoot) {
    return { width: 320, height: 60 };
  }
  const preview = getNodePreview(node);
  const hasExtra = Boolean(preview.formula || preview.subtitle || preview.badge);
  const isSection = node.kind === "SECTION" || !node.parent_id;
  const isConceptOrMethod =
    node.kind === "CONCEPT" || node.kind === "METHOD" || /^Dạng\s+/i.test(node.title);

  if (isSection) {
    return { width: 290, height: hasExtra ? 64 : 50 };
  }
  if (isConceptOrMethod) {
    return { width: 295, height: hasExtra ? 68 : 52 };
  }
  // Formula, Example, Note, Leaves
  return { width: 285, height: hasExtra ? 64 : 46 };
}

export function TheoryBilateralMindmap({
  nodes,
  selectedNodeId,
  scopeId,
  onSelectNode,
}: TheoryBilateralMindmapProps) {
  const containerRef = useRef<HTMLDivElement>(null);

  // Layout Mode: "bilateral" (Tỏa 2 bên) or "tree" (Cây Trái -> Phải)
  const [layoutMode, setLayoutMode] = useState<"bilateral" | "tree">("bilateral");

  // Pan & Zoom state
  const [transform, setTransform] = useState({ x: 0, y: 0, scale: 0.82 });
  const [isPanning, setIsPanning] = useState(false);
  const dragStartRef = useRef({ x: 0, y: 0, tx: 0, ty: 0 });
  const isPointerDownRef = useRef(false);
  const hasMovedRef = useRef(false);

  // Map children by parent_id
  const byParent = useMemo(() => {
    const map = new Map<string, TheoryNode[]>();
    nodes.forEach((n) => {
      if (n.parent_id !== null) {
        const list = map.get(n.parent_id) || [];
        list.push(n);
        map.set(n.parent_id, list);
      }
    });
    return map;
  }, [nodes]);

  // Determine root: either global root or scoped chapter node
  const root = useMemo(() => {
    if (scopeId) {
      const scoped = nodes.find((n) => n.id === scopeId);
      if (scoped) return scoped;
    }
    return nodes.find((n) => n.parent_id === null) ?? nodes[0];
  }, [nodes, scopeId]);

  // Initial collapse state: collapse leaves under CONCEPTs by default
  const [collapsedIds, setCollapsedIds] = useState<Set<string>>(() => {
    const initialSet = new Set<string>();
    nodes.forEach((n) => {
      if (n.kind === "CONCEPT" || /^Dạng\s+/i.test(n.title)) {
        initialSet.add(n.id);
      }
    });
    return initialSet;
  });

  // Auto uncollapse ancestors when selectedNodeId is chosen
  useEffect(() => {
    if (!selectedNodeId) return;
    const ancestors = new Set<string>();
    let curr = nodes.find((n) => n.id === selectedNodeId);
    while (curr && curr.parent_id) {
      ancestors.add(curr.parent_id);
      curr = nodes.find((n) => n.id === curr!.parent_id);
    }
    if (ancestors.size > 0) {
      setCollapsedIds((prev) => {
        let changed = false;
        const next = new Set(prev);
        ancestors.forEach((ancId) => {
          if (next.has(ancId)) {
            next.delete(ancId);
            changed = true;
          }
        });
        return changed ? next : prev;
      });
    }
  }, [selectedNodeId, nodes]);

  // Toggle node collapse
  const toggleCollapse = useCallback((nodeId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    setCollapsedIds((prev) => {
      const next = new Set(prev);
      if (next.has(nodeId)) {
        next.delete(nodeId);
      } else {
        next.add(nodeId);
      }
      return next;
    });
  }, []);

  // Quick toolbar expansion presets
  const handleExpandAll = useCallback(() => {
    setCollapsedIds(new Set());
  }, []);

  const handleExpandToConcepts = useCallback(() => {
    const concepts = nodes.filter((n) => n.kind === "CONCEPT" || /^Dạng\s+/i.test(n.title));
    setCollapsedIds(new Set(concepts.map((c) => c.id)));
  }, [nodes]);

  const handleCollapseToSections = useCallback(() => {
    const sections = nodes.filter((n) => n.kind === "SECTION" || n.parent_id === root?.id);
    setCollapsedIds(new Set(sections.map((s) => s.id)));
  }, [nodes, root?.id]);

  // Layout Calculation (Bilateral or Tree L->R)
  const { layoutItems, links } = useMemo(() => {
    if (!nodes.length || !root) return { layoutItems: [], links: [] };

    const items: LayoutItem[] = [];
    const linkItems: LinkItem[] = [];

    const rootDims = getNodeDimensions(root, true);
    const directChildren = byParent.get(root.id) || [];

    const GAP_Y = 16;
    const DEPTH_GAP_1 = 370;
    const DEPTH_GAP_2 = 330;
    const DEPTH_GAP_3 = 310;

    // Subtree height calculation
    function measureSubtree(node: TheoryNode): number {
      const isCol = collapsedIds.has(node.id);
      const children = byParent.get(node.id) || [];
      const dims = getNodeDimensions(node, false);
      if (children.length === 0 || isCol) {
        return dims.height;
      }
      let sum = 0;
      children.forEach((c) => {
        sum += measureSubtree(c);
      });
      return Math.max(dims.height, sum + (children.length - 1) * GAP_Y);
    }

    // Recursive positioning
    function positionSubtree(
      node: TheoryNode,
      x: number,
      startY: number,
      direction: 1 | -1,
      depth: number,
      sectionColor: string
    ) {
      const h = measureSubtree(node);
      const y = startY + h / 2;
      const isCol = collapsedIds.has(node.id);
      const children = byParent.get(node.id) || [];
      const dims = getNodeDimensions(node, false);

      items.push({
        node,
        x,
        y,
        width: dims.width,
        height: dims.height,
        depth,
        direction,
        color: sectionColor,
        hasChildren: children.length > 0,
        isCollapsed: isCol,
        childCount: children.length,
      });

      if (!isCol && children.length > 0) {
        let childStartY = startY;
        const nextGap = depth === 1 ? DEPTH_GAP_2 : DEPTH_GAP_3;
        const childX = x + direction * nextGap;

        children.forEach((child) => {
          const chH = measureSubtree(child);
          const childY = childStartY + chH / 2;
          const childDims = getNodeDimensions(child, false);

          const sourceX = direction === 1 ? x + dims.width / 2 : x - dims.width / 2;
          const targetX =
            direction === 1 ? childX - childDims.width / 2 : childX + childDims.width / 2;

          linkItems.push({
            id: `${node.id}->${child.id}`,
            sourceX,
            sourceY: y,
            targetX,
            targetY: childY,
            color: sectionColor,
            direction,
            depth,
          });

          positionSubtree(child, childX, childStartY, direction, depth + 1, sectionColor);
          childStartY += chH + GAP_Y;
        });
      }
    }

    if (layoutMode === "tree") {
      // Tree Mode: Root at (0, 0), all branches fan out to the right (direction = 1)
      items.push({
        node: root,
        x: 0,
        y: 0,
        width: rootDims.width,
        height: rootDims.height,
        depth: 0,
        direction: 1,
        color: "#064e3b",
        hasChildren: directChildren.length > 0,
        isCollapsed: false,
        childCount: directChildren.length,
      });

      let totalH = 0;
      directChildren.forEach((child) => {
        totalH += measureSubtree(child);
      });
      totalH += Math.max(0, directChildren.length - 1) * (GAP_Y * 2);

      let startY = -totalH / 2;
      directChildren.forEach((child, idx) => {
        const cH = measureSubtree(child);
        const cY = startY + cH / 2;
        const col = SECTION_PALETTE[idx % SECTION_PALETTE.length];
        const childDims = getNodeDimensions(child, false);

        linkItems.push({
          id: `root->${child.id}`,
          sourceX: rootDims.width / 2,
          sourceY: 0,
          targetX: DEPTH_GAP_1 - childDims.width / 2,
          targetY: cY,
          color: col,
          direction: 1,
          depth: 0,
        });

        positionSubtree(child, DEPTH_GAP_1, startY, 1, 1, col);
        startY += cH + GAP_Y * 2;
      });
    } else {
      // Bilateral Mode: Root placed at center (0, 0)
      items.push({
        node: root,
        x: 0,
        y: 0,
        width: rootDims.width,
        height: rootDims.height,
        depth: 0,
        direction: 1,
        color: "#064e3b",
        hasChildren: directChildren.length > 0,
        isCollapsed: false,
        childCount: directChildren.length,
      });

      // Balanced height partition: greedy 2-partition across Right and Left
      const childrenWithHeights = directChildren.map((c) => ({
        node: c,
        height: measureSubtree(c),
      }));

      // Sort descending by height to optimize greedy 2-partition
      const sorted = [...childrenWithHeights].sort((a, b) => b.height - a.height);
      let rightH = 0;
      let leftH = 0;
      const rightChildrenSet = new Set<string>();

      for (const item of sorted) {
        if (rightH <= leftH) {
          rightChildrenSet.add(item.node.id);
          rightH += item.height;
        } else {
          leftH += item.height;
        }
      }

      // Preserve original relative order in each group
      const rightChildren = directChildren.filter((c) => rightChildrenSet.has(c.id));
      const leftChildren = directChildren.filter((c) => !rightChildrenSet.has(c.id));

      // Right Side Layout
      let rightTotalH = 0;
      rightChildren.forEach((child) => {
        rightTotalH += measureSubtree(child);
      });
      rightTotalH += Math.max(0, rightChildren.length - 1) * (GAP_Y * 2);

      let rightStartY = -rightTotalH / 2;
      rightChildren.forEach((child, idx) => {
        const cH = measureSubtree(child);
        const cY = rightStartY + cH / 2;
        const col = SECTION_PALETTE[idx % SECTION_PALETTE.length];
        const childDims = getNodeDimensions(child, false);

        linkItems.push({
          id: `root->${child.id}`,
          sourceX: rootDims.width / 2,
          sourceY: 0,
          targetX: DEPTH_GAP_1 - childDims.width / 2,
          targetY: cY,
          color: col,
          direction: 1,
          depth: 0,
        });

        positionSubtree(child, DEPTH_GAP_1, rightStartY, 1, 1, col);
        rightStartY += cH + GAP_Y * 2;
      });

      // Left Side Layout
      let leftTotalH = 0;
      leftChildren.forEach((child) => {
        leftTotalH += measureSubtree(child);
      });
      leftTotalH += Math.max(0, leftChildren.length - 1) * (GAP_Y * 2);

      let leftStartY = -leftTotalH / 2;
      leftChildren.forEach((child, idx) => {
        const cH = measureSubtree(child);
        const cY = leftStartY + cH / 2;
        const col = SECTION_PALETTE[(rightChildren.length + idx) % SECTION_PALETTE.length];
        const childDims = getNodeDimensions(child, false);

        linkItems.push({
          id: `root->${child.id}`,
          sourceX: -rootDims.width / 2,
          sourceY: 0,
          targetX: -DEPTH_GAP_1 + childDims.width / 2,
          targetY: cY,
          color: col,
          direction: -1,
          depth: 0,
        });

        positionSubtree(child, -DEPTH_GAP_1, leftStartY, -1, 1, col);
        leftStartY += cH + GAP_Y * 2;
      });
    }

    return { layoutItems: items, links: linkItems };
  }, [nodes, root, collapsedIds, byParent, layoutMode]);

  // Fit whole diagram neatly into viewport bounding box
  const fitToView = useCallback(
    (padding = 70) => {
      if (!containerRef.current || layoutItems.length === 0) return;
      const { clientWidth, clientHeight } = containerRef.current;
      if (clientWidth === 0 || clientHeight === 0) return;

      let minX = Infinity;
      let maxX = -Infinity;
      let minY = Infinity;
      let maxY = -Infinity;

      for (const item of layoutItems) {
        const hw = item.width / 2;
        const hh = item.height / 2;
        minX = Math.min(minX, item.x - hw);
        maxX = Math.max(maxX, item.x + hw);
        minY = Math.min(minY, item.y - hh);
        maxY = Math.max(maxY, item.y + hh);
      }

      const contentW = Math.max(100, maxX - minX + padding * 2);
      const contentH = Math.max(100, maxY - minY + padding * 2);
      const contentCenterX = (minX + maxX) / 2;
      const contentCenterY = (minY + maxY) / 2;

      const scaleX = clientWidth / contentW;
      const scaleY = clientHeight / contentH;
      const optimalScale = Math.min(1.15, Math.max(0.32, Math.min(scaleX, scaleY)));

      setTransform({
        x: clientWidth / 2 - contentCenterX * optimalScale,
        y: clientHeight / 2 - contentCenterY * optimalScale,
        scale: optimalScale,
      });
    },
    [layoutItems]
  );

  // Auto fit on mount, scope change, or layout mode toggle
  useEffect(() => {
    const timer = setTimeout(() => {
      fitToView(70);
    }, 50);
    return () => clearTimeout(timer);
  }, [root?.id, scopeId, layoutMode, fitToView]);

  // Smooth Pointer Dragging with Threshold (so clicks are not swallowed)
  const handlePointerDown = (e: React.PointerEvent) => {
    if (e.button !== 0) return;
    isPointerDownRef.current = true;
    hasMovedRef.current = false;
    dragStartRef.current = {
      x: e.clientX,
      y: e.clientY,
      tx: transform.x,
      ty: transform.y,
    };
  };

  const handlePointerMove = (e: React.PointerEvent) => {
    if (!isPointerDownRef.current) return;
    const dx = e.clientX - dragStartRef.current.x;
    const dy = e.clientY - dragStartRef.current.y;
    if (!hasMovedRef.current) {
      if (Math.hypot(dx, dy) > 4) {
        hasMovedRef.current = true;
        setIsPanning(true);
      }
    }
    if (hasMovedRef.current) {
      setTransform((prev) => ({
        ...prev,
        x: dragStartRef.current.tx + dx,
        y: dragStartRef.current.ty + dy,
      }));
    }
  };

  const handlePointerUp = () => {
    isPointerDownRef.current = false;
    setIsPanning(false);
  };

  // Zoom-to-Cursor via Mouse Wheel
  const handleWheel = (e: React.WheelEvent) => {
    e.preventDefault();
    if (!containerRef.current) return;
    const rect = containerRef.current.getBoundingClientRect();
    const mouseX = e.clientX - rect.left;
    const mouseY = e.clientY - rect.top;

    const zoomFactor = e.deltaY < 0 ? 1.12 : 0.88;
    setTransform((prev) => {
      const newScale = Math.min(2.4, Math.max(0.25, prev.scale * zoomFactor));
      const canvasX = (mouseX - prev.x) / prev.scale;
      const canvasY = (mouseY - prev.y) / prev.scale;
      return {
        x: mouseX - canvasX * newScale,
        y: mouseY - canvasY * newScale,
        scale: newScale,
      };
    });
  };

  const zoomIn = () => {
    if (!containerRef.current) return;
    const { clientWidth, clientHeight } = containerRef.current;
    const mouseX = clientWidth / 2;
    const mouseY = clientHeight / 2;
    setTransform((prev) => {
      const newScale = Math.min(2.4, prev.scale * 1.2);
      const canvasX = (mouseX - prev.x) / prev.scale;
      const canvasY = (mouseY - prev.y) / prev.scale;
      return {
        x: mouseX - canvasX * newScale,
        y: mouseY - canvasY * newScale,
        scale: newScale,
      };
    });
  };

  const zoomOut = () => {
    if (!containerRef.current) return;
    const { clientWidth, clientHeight } = containerRef.current;
    const mouseX = clientWidth / 2;
    const mouseY = clientHeight / 2;
    setTransform((prev) => {
      const newScale = Math.max(0.25, prev.scale * 0.8);
      const canvasX = (mouseX - prev.x) / prev.scale;
      const canvasY = (mouseY - prev.y) / prev.scale;
      return {
        x: mouseX - canvasX * newScale,
        y: mouseY - canvasY * newScale,
        scale: newScale,
      };
    });
  };

  return (
    <div
      ref={containerRef}
      style={{
        position: "relative",
        width: "100%",
        height: "clamp(540px, 72vh, 820px)",
        background: "radial-gradient(circle at center, #ffffff 0%, #f4f8f5 100%)",
        overflow: "hidden",
        cursor: isPanning ? "grabbing" : "grab",
        userSelect: "none",
        borderRadius: "16px",
      }}
      onPointerDown={handlePointerDown}
      onPointerMove={handlePointerMove}
      onPointerUp={handlePointerUp}
      onWheel={handleWheel}
      aria-label="Sơ đồ tư duy tương tác"
    >
      {/* Top Floating Controls */}
      <div
        style={{
          position: "absolute",
          top: "12px",
          right: "14px",
          display: "flex",
          alignItems: "center",
          gap: "6px",
          background: "rgba(255, 255, 255, 0.95)",
          backdropFilter: "blur(12px)",
          padding: "5px 8px",
          borderRadius: "12px",
          border: "1px solid #bce0cc",
          boxShadow: "0 6px 20px rgba(10, 40, 25, 0.09)",
          zIndex: 10,
        }}
      >
        {/* Layout Switcher: Bilateral vs Tree L->R */}
        <button
          type="button"
          onClick={() => setLayoutMode((m) => (m === "bilateral" ? "tree" : "bilateral"))}
          title={
            layoutMode === "bilateral"
              ? "Chuyển sang Cây Trái → Phải (chuẩn đọc tài liệu)"
              : "Chuyển sang Sơ đồ Tỏa 2 bên đối xứng"
          }
          style={{
            padding: "5px 11px",
            background: layoutMode === "tree" ? "#eef6f1" : "#ffffff",
            border: "1px solid #b2d6c1",
            borderRadius: "7px",
            fontSize: "0.78rem",
            fontWeight: 750,
            color: "#16593e",
            cursor: "pointer",
            display: "inline-flex",
            alignItems: "center",
            gap: "5px",
          }}
        >
          {layoutMode === "bilateral" ? "🌟 Tỏa 2 bên" : "🌲 Cây Trái → Phải"}
        </button>

        <div style={{ width: "1px", height: "18px", background: "#d1e3d7", margin: "0 2px" }} />

        {/* Level Presets */}
        <button
          type="button"
          onClick={handleCollapseToSections}
          title="Thu gọn chỉ giữ các chủ đề quanh tâm"
          style={{
            padding: "5px 9px",
            background: "#ffffff",
            border: "1px solid #cbe0d3",
            borderRadius: "7px",
            fontSize: "0.77rem",
            fontWeight: 700,
            color: "#16593e",
            cursor: "pointer",
          }}
        >
          Chủ đề
        </button>
        <button
          type="button"
          onClick={handleExpandToConcepts}
          title="Hiển thị rõ các chủ đề và dạng bài"
          style={{
            padding: "5px 9px",
            background: "#ffffff",
            border: "1px solid #cbe0d3",
            borderRadius: "7px",
            fontSize: "0.77rem",
            fontWeight: 700,
            color: "#16593e",
            cursor: "pointer",
          }}
        >
          Dạng bài
        </button>
        <button
          type="button"
          onClick={handleExpandAll}
          title="Mở rộng tất cả các cành nhánh"
          style={{
            padding: "5px 9px",
            background: "#ffffff",
            border: "1px solid #cbe0d3",
            borderRadius: "7px",
            fontSize: "0.77rem",
            fontWeight: 700,
            color: "#16593e",
            cursor: "pointer",
          }}
        >
          Mở tất cả
        </button>

        <div style={{ width: "1px", height: "18px", background: "#d1e3d7", margin: "0 2px" }} />

        {/* Zoom & Fit */}
        <button
          type="button"
          onClick={zoomIn}
          title="Phóng to"
          style={{
            width: "28px",
            height: "28px",
            background: "#ffffff",
            border: "1px solid #cbe0d3",
            borderRadius: "7px",
            fontWeight: 800,
            color: "#16593e",
            cursor: "pointer",
          }}
        >
          ＋
        </button>
        <button
          type="button"
          onClick={zoomOut}
          title="Thu nhỏ"
          style={{
            width: "28px",
            height: "28px",
            background: "#ffffff",
            border: "1px solid #cbe0d3",
            borderRadius: "7px",
            fontWeight: 800,
            color: "#16593e",
            cursor: "pointer",
          }}
        >
          －
        </button>
        <button
          type="button"
          onClick={() => fitToView(70)}
          title="Căn vừa khung hình thông minh"
          style={{
            padding: "5px 11px",
            background: "linear-gradient(135deg, #186b4c, #13553d)",
            border: "none",
            borderRadius: "7px",
            fontSize: "0.77rem",
            fontWeight: 750,
            color: "#ffffff",
            cursor: "pointer",
            boxShadow: "0 2px 6px rgba(24, 107, 76, 0.2)",
          }}
        >
          🎯 Vừa khung
        </button>
      </div>

      {/* Main SVG Render Canvas */}
      <svg
        style={{
          width: "100%",
          height: "100%",
          display: "block",
        }}
      >
        <defs>
          <filter id="mindmap-shadow" x="-20%" y="-20%" width="140%" height="140%">
            <feDropShadow dx="0" dy="4" stdDeviation="6" floodColor="#0f3d28" floodOpacity="0.08" />
          </filter>
          <filter id="root-glow" x="-30%" y="-30%" width="160%" height="160%">
            <feDropShadow dx="0" dy="6" stdDeviation="12" floodColor="#059669" floodOpacity="0.25" />
          </filter>
          <filter id="node-selected-glow" x="-30%" y="-30%" width="160%" height="160%">
            <feDropShadow dx="0" dy="0" stdDeviation="8" floodColor="#2563eb" floodOpacity="0.5" />
          </filter>
        </defs>

        <g transform={`translate(${transform.x}, ${transform.y}) scale(${transform.scale})`}>
          {/* 1. Curved Connecting Links */}
          {links.map((link) => {
            const dx = Math.abs(link.targetX - link.sourceX) * 0.52;
            const c1x = link.direction === 1 ? link.sourceX + dx : link.sourceX - dx;
            const c2x = link.direction === 1 ? link.targetX - dx : link.targetX + dx;
            const pathData = `M ${link.sourceX} ${link.sourceY} C ${c1x} ${link.sourceY}, ${c2x} ${link.targetY}, ${link.targetX} ${link.targetY}`;
            const strokeWidth = link.depth === 0 ? 3.5 : link.depth === 1 ? 2.4 : 1.8;

            return (
              <path
                key={link.id}
                d={pathData}
                fill="none"
                stroke={link.color}
                strokeWidth={strokeWidth}
                strokeOpacity={0.78}
                strokeLinecap="round"
              />
            );
          })}

          {/* 2. Interactive Mindmap Nodes */}
          {layoutItems.map((item) => {
            const isSelected = selectedNodeId === item.node.id;
            const isRoot = item.depth === 0;
            const isSection = item.node.kind === "SECTION";
            const isMethod =
              item.node.title.includes("Phương pháp") ||
              item.node.title.includes("📝") ||
              /^Dạng\s+/i.test(item.node.title);
            const isExample =
              item.node.kind === "EXAMPLE" ||
              item.node.title.includes("Ví dụ") ||
              item.node.title.includes("💡");
            const isFormula =
              item.node.kind === "FORMULA" ||
              item.node.title.includes("Công thức") ||
              item.node.title.includes("📐") ||
              Boolean(item.node.latex);
            const isNote =
              item.node.kind === "NOTE" ||
              item.node.title.includes("Bẫy") ||
              item.node.title.includes("⚠️") ||
              item.node.title.includes("Nhận xét");

            const preview = getNodePreview(item.node);

            // Background & text color
            let bgFill = "#ffffff";
            let borderStroke = item.color;
            let textFill = "#102a1e";
            let borderWidth = 1.6;

            if (isRoot) {
              bgFill = "#064e3b";
              borderStroke = "#10b981";
              textFill = "#ffffff";
              borderWidth = 2.5;
            } else if (isSection) {
              bgFill = "#f0fdf4";
              borderStroke = item.color;
              textFill = "#0c3322";
              borderWidth = 2;
            } else if (isMethod) {
              bgFill = "#f0f9ff";
              borderStroke = "#38bdf8";
              textFill = "#0369a1";
            } else if (isExample) {
              bgFill = "#fffbeb";
              borderStroke = "#f59e0b";
              textFill = "#b45309";
            } else if (isFormula) {
              bgFill = "#ecfdf5";
              borderStroke = "#10b981";
              textFill = "#047857";
            } else if (isNote) {
              bgFill = "#fff1f2";
              borderStroke = "#f43f5e";
              textFill = "#be123c";
            }

            if (isSelected) {
              borderStroke = "#2563eb";
              borderWidth = 3;
            }

            // Node bounding box
            const rectX = item.x - item.width / 2;
            const rectY = item.y - item.height / 2;

            return (
              <g
                key={item.node.id}
                onClick={(e) => {
                  e.stopPropagation();
                  onSelectNode?.(item.node.id);
                }}
                onPointerDown={(e) => e.stopPropagation()}
                style={{ cursor: "pointer" }}
                filter={
                  isSelected
                    ? "url(#node-selected-glow)"
                    : isRoot
                    ? "url(#root-glow)"
                    : "url(#mindmap-shadow)"
                }
              >
                {/* Node Card Rectangle */}
                <rect
                  x={rectX}
                  y={rectY}
                  width={item.width}
                  height={item.height}
                  rx={isRoot ? 24 : isSection ? 14 : 10}
                  fill={bgFill}
                  stroke={borderStroke}
                  strokeWidth={borderWidth}
                />

                {/* Accent Color Bar (Symmetrical by direction) */}
                {!isRoot && (
                  <rect
                    x={item.direction === 1 ? rectX : rectX + item.width - 5}
                    y={rectY}
                    width={5}
                    height={item.height}
                    rx={2.5}
                    fill={item.color}
                  />
                )}

                {/* Node Text & Rich Content Preview */}
                <foreignObject
                  x={
                    isRoot
                      ? rectX + 14
                      : item.direction === 1
                      ? rectX + 12
                      : rectX + (item.hasChildren ? 22 : 12)
                  }
                  y={rectY + 4}
                  width={item.width - (isRoot ? 28 : item.hasChildren ? 38 : 20)}
                  height={item.height - 8}
                >
                  <div
                    style={{
                      width: "100%",
                      height: "100%",
                      display: "flex",
                      flexDirection: "column",
                      justifyContent: "center",
                      fontFamily: "system-ui, -apple-system, sans-serif",
                      pointerEvents: "none",
                    }}
                  >
                    {/* Title with 2-line wrap protection */}
                    <div
                      style={{
                        color: textFill,
                        fontSize: isRoot ? "0.94rem" : isSection ? "0.85rem" : "0.79rem",
                        fontWeight: isRoot || isSection ? 800 : 650,
                        lineHeight: 1.28,
                        display: "-webkit-box",
                        WebkitLineClamp: preview.formula || preview.subtitle ? 1 : 2,
                        WebkitBoxOrient: "vertical",
                        overflow: "hidden",
                        textOverflow: "ellipsis",
                      }}
                      title={item.node.title}
                    >
                      {isRoot && <span style={{ marginRight: "6px" }}>⚡</span>}
                      {item.node.title}
                    </div>

                    {/* Subtitle / Formula Preview */}
                    {(preview.formula || preview.subtitle || preview.badge) && (
                      <div
                        style={{
                          marginTop: "3px",
                          display: "flex",
                          alignItems: "center",
                          gap: "5px",
                          fontSize: "0.72rem",
                          color: preview.formula
                            ? "#047857"
                            : preview.badge
                            ? "#2563eb"
                            : isRoot
                            ? "#a7f3d0"
                            : "#475569",
                          fontWeight: preview.formula ? 600 : 500,
                          whiteSpace: "nowrap",
                          overflow: "hidden",
                          textOverflow: "ellipsis",
                        }}
                      >
                        {preview.formula && (
                          <span
                            style={{
                              fontFamily: "KaTeX_Math, Cambria Math, serif",
                              fontSize: "0.74rem",
                            }}
                          >
                            📐 {preview.formula}
                          </span>
                        )}
                        {preview.subtitle && !preview.formula && <span>{preview.subtitle}</span>}
                        {preview.badge && (
                          <span
                            style={{
                              padding: "1px 6px",
                              borderRadius: "4px",
                              background: "rgba(37, 99, 235, 0.1)",
                              fontSize: "0.68rem",
                              fontWeight: 700,
                            }}
                          >
                            {preview.badge}
                          </span>
                        )}
                      </div>
                    )}
                  </div>
                </foreignObject>

                {/* Symmetrical Expand / Collapse Button (+ / −) with large hit area */}
                {item.hasChildren && !isRoot && (
                  <g
                    transform={`translate(${
                      item.direction === 1 ? rectX + item.width : rectX
                    }, ${item.y})`}
                    onClick={(e) => toggleCollapse(item.node.id, e)}
                    onPointerDown={(e) => e.stopPropagation()}
                    style={{ cursor: "pointer" }}
                  >
                    {/* Transparent generous hit area (36px diameter) */}
                    <circle r={18} fill="transparent" />
                    {/* Visual button circle (26px diameter) */}
                    <circle
                      r={13}
                      fill="#ffffff"
                      stroke={item.color}
                      strokeWidth={2}
                      filter="url(#mindmap-shadow)"
                    />
                    <text
                      textAnchor="middle"
                      dy="4"
                      fontSize={item.isCollapsed && item.childCount > 9 ? "10" : "12"}
                      fontWeight="800"
                      fill={item.color}
                      style={{ userSelect: "none" }}
                    >
                      {item.isCollapsed ? `+${item.childCount > 0 ? item.childCount : ""}` : "−"}
                    </text>
                  </g>
                )}
              </g>
            );
          })}
        </g>
      </svg>

      {/* Bottom Hint Overlay */}
      <div
        style={{
          position: "absolute",
          bottom: "10px",
          left: "14px",
          right: "14px",
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          fontSize: "0.77rem",
          color: "#4d6b5b",
          pointerEvents: "none",
        }}
      >
        <span>
          💡 <strong>Kéo chuột</strong> để lướt sơ đồ • <strong>Cuộn chuột</strong> để zoom theo con
          trỏ • <strong>Bấm nút + / −</strong> mở nhánh • <strong>Bấm vào thẻ bất kỳ</strong> để xem
          công thức &amp; các bước giải!
        </span>
        <span
          style={{
            background: "rgba(255, 255, 255, 0.8)",
            padding: "2px 8px",
            borderRadius: "6px",
            fontWeight: 700,
            border: "1px solid #d5e5db",
          }}
        >
          {layoutItems.length}/{nodes.length} nhánh
        </span>
      </div>
    </div>
  );
}
