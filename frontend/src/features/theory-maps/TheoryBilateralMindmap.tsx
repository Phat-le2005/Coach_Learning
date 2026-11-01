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
  "#059669", // Emerald (Chủ đề 1)
  "#0284c7", // Sky blue (Chủ đề 2)
  "#7c3aed", // Violet (Chủ đề 3)
  "#d97706", // Amber (Chủ đề 4)
  "#e11d48", // Rose (Chủ đề 5)
  "#2563eb", // Royal blue (Chủ đề 6)
  "#0d9488", // Teal
  "#9333ea", // Purple
];

function getNodeDimensions(node: TheoryNode, isRoot: boolean) {
  if (isRoot) return { width: 290, height: 56 };
  if (node.kind === "SECTION") return { width: 250, height: 48 };
  if (node.kind === "CONCEPT") return { width: 260, height: 44 };
  return { width: 240, height: 38 };
}

export function TheoryBilateralMindmap({
  nodes,
  selectedNodeId,
  scopeId,
  onSelectNode,
}: TheoryBilateralMindmapProps) {
  const containerRef = useRef<HTMLDivElement>(null);

  // Pan & Zoom state
  const [transform, setTransform] = useState({ x: 0, y: 0, scale: 0.82 });
  const [isPanning, setIsPanning] = useState(false);
  const dragStartRef = useRef({ x: 0, y: 0, tx: 0, ty: 0 });

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

  // Initial collapse state: collapse leaves under CONCEPTs by default so
  // all 6 chapters & 33 dạng bài are balanced and clearly visible at a glance!
  const [collapsedIds, setCollapsedIds] = useState<Set<string>>(() => {
    const initialSet = new Set<string>();
    nodes.forEach((n) => {
      if (n.kind === "CONCEPT" || /^Dạng\s+/i.test(n.title)) {
        initialSet.add(n.id);
      }
    });
    return initialSet;
  });

  // Center canvas on mount or when root/scope changes
  const centerCanvas = useCallback(() => {
    if (!containerRef.current) return;
    const { clientWidth, clientHeight } = containerRef.current;
    setTransform({
      x: clientWidth / 2,
      y: clientHeight / 2,
      scale: clientWidth < 900 ? 0.65 : 0.82,
    });
  }, []);

  useEffect(() => {
    centerCanvas();
  }, [centerCanvas, root.id]);

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
    const sections = nodes.filter((n) => n.kind === "SECTION" || n.parent_id === root.id);
    setCollapsedIds(new Set(sections.map((s) => s.id)));
  }, [nodes, root.id]);

  // Bilateral Layout Calculation
  const { layoutItems, links } = useMemo(() => {
    if (!nodes.length || !root) return { layoutItems: [], links: [] };

    const items: LayoutItem[] = [];
    const linkItems: LinkItem[] = [];

    const rootDims = getNodeDimensions(root, true);

    // 1. Root Node placed at center (0, 0)
    const directChildren = byParent.get(root.id) || [];
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

    // 2. Partition direct children into Right and Left halves
    const mid = Math.ceil(directChildren.length / 2);
    const rightChildren = directChildren.slice(0, mid);
    const leftChildren = directChildren.slice(mid);

    const GAP_Y = 14;
    const DEPTH_GAP_1 = 350;
    const DEPTH_GAP_2 = 300;
    const DEPTH_GAP_3 = 280;

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

          // Bilateral cubic bezier coordinates
          const sourceX = direction === 1 ? x + dims.width / 2 : x - dims.width / 2;
          const targetX = direction === 1 ? childX - childDims.width / 2 : childX + childDims.width / 2;

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

    // Right Side Layout (Chủ đề 01, 02, 03... or half of chapter dạngs)
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

      const targetX = DEPTH_GAP_1 - childDims.width / 2;
      linkItems.push({
        id: `root->${child.id}`,
        sourceX: rootDims.width / 2,
        sourceY: 0,
        targetX,
        targetY: cY,
        color: col,
        direction: 1,
        depth: 0,
      });

      positionSubtree(child, DEPTH_GAP_1, rightStartY, 1, 1, col);
      rightStartY += cH + GAP_Y * 2;
    });

    // Left Side Layout (Chủ đề 04, 05, 06... or other half of chapter dạngs)
    let leftTotalH = 0;
    leftChildren.forEach((child) => {
      leftTotalH += measureSubtree(child);
    });
    leftTotalH += Math.max(0, leftChildren.length - 1) * (GAP_Y * 2);

    let leftStartY = -leftTotalH / 2;
    leftChildren.forEach((child, idx) => {
      const cH = measureSubtree(child);
      const cY = leftStartY + cH / 2;
      const col = SECTION_PALETTE[(mid + idx) % SECTION_PALETTE.length];
      const childDims = getNodeDimensions(child, false);

      const targetX = -DEPTH_GAP_1 + childDims.width / 2;
      linkItems.push({
        id: `root->${child.id}`,
        sourceX: -rootDims.width / 2,
        sourceY: 0,
        targetX,
        targetY: cY,
        color: col,
        direction: -1,
        depth: 0,
      });

      positionSubtree(child, -DEPTH_GAP_1, leftStartY, -1, 1, col);
      leftStartY += cH + GAP_Y * 2;
    });

    return { layoutItems: items, links: linkItems };
  }, [nodes, root, collapsedIds, byParent]);

  // Pointer Dragging / Panning
  const handlePointerDown = (e: React.PointerEvent) => {
    if (e.button !== 0) return;
    setIsPanning(true);
    dragStartRef.current = {
      x: e.clientX,
      y: e.clientY,
      tx: transform.x,
      ty: transform.y,
    };
    (e.target as HTMLElement).setPointerCapture?.(e.pointerId);
  };

  const handlePointerMove = (e: React.PointerEvent) => {
    if (!isPanning) return;
    const dx = e.clientX - dragStartRef.current.x;
    const dy = e.clientY - dragStartRef.current.y;
    setTransform((prev) => ({
      ...prev,
      x: dragStartRef.current.tx + dx,
      y: dragStartRef.current.ty + dy,
    }));
  };

  const handlePointerUp = (e: React.PointerEvent) => {
    if (isPanning) {
      setIsPanning(false);
      (e.target as HTMLElement).releasePointerCapture?.(e.pointerId);
    }
  };

  // Mouse Wheel Zoom
  const handleWheel = (e: React.WheelEvent) => {
    e.preventDefault();
    const zoomFactor = e.deltaY < 0 ? 1.12 : 0.88;
    setTransform((prev) => {
      const newScale = Math.min(2.5, Math.max(0.25, prev.scale * zoomFactor));
      return { ...prev, scale: newScale };
    });
  };

  const zoomIn = () => setTransform((prev) => ({ ...prev, scale: Math.min(2.5, prev.scale * 1.2) }));
  const zoomOut = () => setTransform((prev) => ({ ...prev, scale: Math.max(0.25, prev.scale * 0.8) }));

  return (
    <div
      ref={containerRef}
      style={{
        position: "relative",
        width: "100%",
        height: "calc(100vh - 128px)",
        minHeight: "640px",
        background: "radial-gradient(circle at center, #ffffff 0%, #f4f8f5 100%)",
        overflow: "hidden",
        cursor: isPanning ? "grabbing" : "grab",
        userSelect: "none",
      }}
      onPointerDown={handlePointerDown}
      onPointerMove={handlePointerMove}
      onPointerUp={handlePointerUp}
      onWheel={handleWheel}
      aria-label="Sơ đồ tư duy tỏa từ tâm ra xung quanh"
    >
      {/* Top Floating Controls */}
      <div
        style={{
          position: "absolute",
          top: "12px",
          right: "14px",
          display: "flex",
          alignItems: "center",
          gap: "5px",
          background: "rgba(255, 255, 255, 0.94)",
          backdropFilter: "blur(10px)",
          padding: "5px 8px",
          borderRadius: "10px",
          border: "1px solid #bce0cc",
          boxShadow: "0 4px 16px rgba(10, 40, 25, 0.08)",
          zIndex: 10,
        }}
      >
        <button
          type="button"
          onClick={handleExpandAll}
          title="Mở rộng tất cả các cành nhánh"
          style={{
            padding: "5px 10px",
            background: "#ffffff",
            border: "1px solid #cbe0d3",
            borderRadius: "6px",
            fontSize: "0.78rem",
            fontWeight: 700,
            color: "#16593e",
            cursor: "pointer",
          }}
        >
          Mở rộng tất cả
        </button>
        <button
          type="button"
          onClick={handleExpandToConcepts}
          title="Hiển thị rõ các chủ đề và dạng bài"
          style={{
            padding: "5px 10px",
            background: "#ffffff",
            border: "1px solid #cbe0d3",
            borderRadius: "6px",
            fontSize: "0.78rem",
            fontWeight: 700,
            color: "#16593e",
            cursor: "pointer",
          }}
        >
          Dạng bài
        </button>
        <button
          type="button"
          onClick={handleCollapseToSections}
          title="Thu gọn chỉ giữ các chủ đề quanh tâm"
          style={{
            padding: "5px 10px",
            background: "#ffffff",
            border: "1px solid #cbe0d3",
            borderRadius: "6px",
            fontSize: "0.78rem",
            fontWeight: 700,
            color: "#16593e",
            cursor: "pointer",
          }}
        >
          Chủ đề
        </button>
        <div style={{ width: "1px", height: "18px", background: "#d1e3d7", margin: "0 2px" }} />
        <button
          type="button"
          onClick={zoomIn}
          title="Phóng to"
          style={{
            width: "28px",
            height: "28px",
            background: "#ffffff",
            border: "1px solid #cbe0d3",
            borderRadius: "6px",
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
            borderRadius: "6px",
            fontWeight: 800,
            color: "#16593e",
            cursor: "pointer",
          }}
        >
          －
        </button>
        <button
          type="button"
          onClick={centerCanvas}
          title="Căn giữa màn hình"
          style={{
            padding: "5px 10px",
            background: "#ffffff",
            border: "1px solid #cbe0d3",
            borderRadius: "6px",
            fontSize: "0.78rem",
            fontWeight: 700,
            color: "#16593e",
            cursor: "pointer",
          }}
        >
          🎯 Căn giữa
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
        </defs>

        <g transform={`translate(${transform.x}, ${transform.y}) scale(${transform.scale})`}>
          {/* 1. Curved Connecting Links */}
          {links.map((link) => {
            const dx = Math.abs(link.targetX - link.sourceX) * 0.5;
            const c1x = link.direction === 1 ? link.sourceX + dx : link.sourceX - dx;
            const c2x = link.direction === 1 ? link.targetX - dx : link.targetX + dx;
            const pathData = `M ${link.sourceX} ${link.sourceY} C ${c1x} ${link.sourceY}, ${c2x} ${link.targetY}, ${link.targetX} ${link.targetY}`;
            const strokeWidth = link.depth === 0 ? 3.5 : link.depth === 1 ? 2.2 : 1.6;

            return (
              <path
                key={link.id}
                d={pathData}
                fill="none"
                stroke={link.color}
                strokeWidth={strokeWidth}
                strokeOpacity={0.75}
                strokeLinecap="round"
              />
            );
          })}

          {/* 2. Interactive Mindmap Nodes */}
          {layoutItems.map((item) => {
            const isSelected = selectedNodeId === item.node.id;
            const isRoot = item.depth === 0;
            const isSection = item.node.kind === "SECTION";
            const isConcept = item.node.kind === "CONCEPT";
            const isMethod = item.node.title.includes("Phương pháp") || item.node.title.includes("📝");
            const isExample = item.node.kind === "EXAMPLE" || item.node.title.includes("Ví dụ") || item.node.title.includes("💡");
            const isFormula = item.node.kind === "FORMULA" || item.node.title.includes("Công thức") || item.node.title.includes("📐");
            const isNote = item.node.kind === "NOTE" || item.node.title.includes("Bẫy") || item.node.title.includes("⚠️");

            // Background & text color
            let bgFill = "#ffffff";
            let borderStroke = item.color;
            let textFill = "#1a382b";
            let borderWidth = 1.6;

            if (isRoot) {
              bgFill = "#064e3b";
              borderStroke = "#10b981";
              textFill = "#ffffff";
              borderWidth = 2.5;
            } else if (isSection) {
              bgFill = "#f0fdf4";
              borderStroke = item.color;
              textFill = "#0f3d28";
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

            // Clean title with formula text if appropriate
            const readableFormula = item.node.latex ? latexToReadable(item.node.latex) : "";
            let displayTitle = item.node.title;
            if (isFormula && readableFormula && !displayTitle.includes(readableFormula)) {
              displayTitle = `${displayTitle}: ${readableFormula}`;
            }

            return (
              <g
                key={item.node.id}
                onClick={(e) => {
                  e.stopPropagation();
                  onSelectNode?.(item.node.id);
                }}
                style={{ cursor: "pointer" }}
                filter={isRoot ? "url(#root-glow)" : "url(#mindmap-shadow)"}
              >
                {/* Node Card Rectangle */}
                <rect
                  x={rectX}
                  y={rectY}
                  width={item.width}
                  height={item.height}
                  rx={isRoot ? 28 : isSection ? 12 : 8}
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
                    rx={2}
                    fill={item.color}
                  />
                )}

                {/* Node Text & Icon */}
                <foreignObject
                  x={
                    isRoot
                      ? rectX + 14
                      : item.direction === 1
                      ? rectX + 12
                      : rectX + (item.hasChildren ? 20 : 12)
                  }
                  y={rectY + 3}
                  width={item.width - (isRoot ? 28 : item.hasChildren ? 34 : 20)}
                  height={item.height - 6}
                >
                  <div
                    style={{
                      width: "100%",
                      height: "100%",
                      display: "flex",
                      alignItems: "center",
                      color: textFill,
                      fontSize: isRoot ? "0.95rem" : isSection ? "0.86rem" : "0.78rem",
                      fontWeight: isRoot || isSection ? 800 : 600,
                      whiteSpace: "nowrap",
                      overflow: "hidden",
                      textOverflow: "ellipsis",
                      fontFamily: "system-ui, -apple-system, sans-serif",
                    }}
                    title={displayTitle}
                  >
                    {isRoot && <span style={{ marginRight: "6px" }}>🌿</span>}
                    {displayTitle}
                  </div>
                </foreignObject>

                {/* Symmetrical Expand / Collapse Button (+ / −) at branch junction */}
                {item.hasChildren && !isRoot && (
                  <g
                    transform={`translate(${
                      item.direction === 1 ? rectX + item.width : rectX
                    }, ${item.y})`}
                    onClick={(e) => toggleCollapse(item.node.id, e)}
                    style={{ cursor: "pointer" }}
                  >
                    <circle
                      r={11}
                      fill="#ffffff"
                      stroke={item.color}
                      strokeWidth={1.8}
                    />
                    <text
                      textAnchor="middle"
                      dy="3.5"
                      fontSize={item.isCollapsed ? "11" : "13"}
                      fontWeight="bold"
                      fill={item.color}
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
          bottom: "12px",
          left: "16px",
          right: "16px",
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          fontSize: "0.78rem",
          color: "#4d6b5b",
          pointerEvents: "none",
        }}
      >
        <span>
          💡 <strong>Kéo chuột</strong> để di chuyển • <strong>Cuộn chuột</strong> để zoom • <strong>Bấm nút + / −</strong> để mở/thu gọn nhánh • <strong>Bấm vào thẻ bất kỳ</strong> để mở bảng công thức &amp; ví dụ giải chi tiết!
        </span>
      </div>
    </div>
  );
}
