"use client";

import React, { useRef, useEffect, useCallback, useState } from "react";
import type { DrawingTool, InkPoint, InkStroke, PaperGrid } from "../types";
import { A4_WIDTH, A4_HEIGHT } from "../types";
import {
  generateUuid,
  normalizeCoordinate,
  denormalizeCoordinate,
  strokeIntersectsPoint,
} from "../utils/ink-math";
import styles from "../MathWorkspace.module.css";

interface MathCanvasProps {
  strokes: InkStroke[];
  onStrokesChange: (strokes: InkStroke[]) => void;
  currentTool: DrawingTool;
  penColor: string;
  penWidth: number;
  highlighterWidth: number;
  paperGrid: PaperGrid;
  zoomLevel: number;
  isReadOnly?: boolean;
}

export function MathCanvas({
  strokes,
  onStrokesChange,
  currentTool,
  penColor,
  penWidth,
  highlighterWidth,
  paperGrid,
  zoomLevel,
  isReadOnly = false,
}: MathCanvasProps) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const activeStrokeRef = useRef<InkStroke | null>(null);
  const isPointerDownRef = useRef(false);
  const [isDrawing, setIsDrawing] = useState(false);

  // Redraw all strokes on canvas
  const redrawAllStrokes = useCallback(
    (targetCanvas: HTMLCanvasElement, strokeList: InkStroke[]) => {
      const ctx = targetCanvas.getContext("2d");
      if (!ctx) return;

      const dpr = window.devicePixelRatio || 1;
      const w = A4_WIDTH;
      const h = A4_HEIGHT;

      ctx.save();
      ctx.setTransform(1, 0, 0, 1, 0, 0);
      ctx.clearRect(0, 0, targetCanvas.width, targetCanvas.height);
      ctx.scale(dpr, dpr);

      // Render highlighters first (so pen ink stays on top)
      const highlighters = strokeList.filter((s) => s.tool === "HIGHLIGHTER");
      const pens = strokeList.filter((s) => s.tool !== "HIGHLIGHTER");

      const drawStroke = (s: InkStroke) => {
        if (!s.points || s.points.length === 0) return;

        ctx.save();
        ctx.beginPath();
        ctx.lineCap = "round";
        ctx.lineJoin = "round";

        if (s.tool === "HIGHLIGHTER") {
          ctx.strokeStyle = s.color || "#fef08a";
          ctx.globalAlpha = 0.35;
          ctx.lineWidth = s.width || 14;
        } else {
          ctx.strokeStyle = s.color || "#0f172a";
          ctx.globalAlpha = 1.0;
          ctx.lineWidth = s.width || 2;
        }

        const startX = denormalizeCoordinate(s.points[0].x, w);
        const startY = denormalizeCoordinate(s.points[0].y, h);

        if (s.points.length === 1) {
          ctx.arc(startX, startY, (s.width || 2) / 2, 0, Math.PI * 2);
          ctx.fillStyle = ctx.strokeStyle;
          ctx.fill();
        } else {
          ctx.moveTo(startX, startY);
          for (let i = 1; i < s.points.length; i++) {
            const p = s.points[i];
            const px = denormalizeCoordinate(p.x, w);
            const py = denormalizeCoordinate(p.y, h);
            ctx.lineTo(px, py);
          }
          ctx.stroke();
        }

        ctx.restore();
      };

      for (const hStroke of highlighters) {
        drawStroke(hStroke);
      }
      for (const pStroke of pens) {
        drawStroke(pStroke);
      }

      ctx.restore();
    },
    [],
  );

  // Setup High-DPI canvas resolution
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const dpr = window.devicePixelRatio || 1;
    canvas.width = A4_WIDTH * dpr;
    canvas.height = A4_HEIGHT * dpr;

    redrawAllStrokes(canvas, strokes);
  }, [strokes, redrawAllStrokes]);

  // Pointer event handlers
  const handlePointerDown = (e: React.PointerEvent<HTMLCanvasElement>) => {
    if (isReadOnly) return;
    const canvas = canvasRef.current;
    if (!canvas) return;

    canvas.setPointerCapture(e.pointerId);
    isPointerDownRef.current = true;
    setIsDrawing(true);

    const rect = canvas.getBoundingClientRect();
    const clientX = e.clientX - rect.left;
    const clientY = e.clientY - rect.top;

    const normX = normalizeCoordinate(clientX, rect.width);
    const normY = normalizeCoordinate(clientY, rect.height);
    const pressure = e.pressure && e.pressure > 0 ? e.pressure : 0.5;

    if (currentTool === "eraser") {
      // Stroke eraser: detect and delete any stroke near cursor
      const threshold = 14 / rect.width;
      const updated = strokes.filter(
        (s) => !strokeIntersectsPoint(s, normX, normY, threshold),
      );
      if (updated.length !== strokes.length) {
        onStrokesChange(updated);
      }
      return;
    }

    // Pen or Highlighter: Start new stroke
    const toolType = currentTool === "highlighter" ? "HIGHLIGHTER" : "PEN";
    const width = currentTool === "highlighter" ? highlighterWidth : penWidth;
    const color = currentTool === "highlighter" ? "#facc15" : penColor;

    const firstPoint: InkPoint = { x: normX, y: normY, pressure };
    const newStroke: InkStroke = {
      id: generateUuid(),
      tool: toolType,
      color,
      width,
      points: [firstPoint],
    };

    activeStrokeRef.current = newStroke;

    // Draw initial point on canvas
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    const dpr = window.devicePixelRatio || 1;
    ctx.save();
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.scale(dpr, dpr);
    ctx.beginPath();
    ctx.arc(
      denormalizeCoordinate(normX, A4_WIDTH),
      denormalizeCoordinate(normY, A4_HEIGHT),
      width / 2,
      0,
      Math.PI * 2,
    );
    ctx.fillStyle = color;
    ctx.globalAlpha = toolType === "HIGHLIGHTER" ? 0.35 : 1.0;
    ctx.fill();
    ctx.restore();
  };

  const handlePointerMove = (e: React.PointerEvent<HTMLCanvasElement>) => {
    if (!isPointerDownRef.current) return;
    const canvas = canvasRef.current;
    if (!canvas) return;

    const rect = canvas.getBoundingClientRect();
    const clientX = e.clientX - rect.left;
    const clientY = e.clientY - rect.top;
    const normX = normalizeCoordinate(clientX, rect.width);
    const normY = normalizeCoordinate(clientY, rect.height);

    if (currentTool === "eraser") {
      const threshold = 16 / rect.width;
      const updated = strokes.filter(
        (s) => !strokeIntersectsPoint(s, normX, normY, threshold),
      );
      if (updated.length !== strokes.length) {
        onStrokesChange(updated);
      }
      return;
    }

    const activeStroke = activeStrokeRef.current;
    if (!activeStroke) return;

    const pressure = e.pressure && e.pressure > 0 ? e.pressure : 0.5;
    const prevPoint = activeStroke.points[activeStroke.points.length - 1];
    const newPoint: InkPoint = { x: normX, y: normY, pressure };

    activeStroke.points.push(newPoint);

    // Incremental draw: only draw line segment from prev to current
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    const dpr = window.devicePixelRatio || 1;

    ctx.save();
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.scale(dpr, dpr);
    ctx.beginPath();
    ctx.lineCap = "round";
    ctx.lineJoin = "round";
    ctx.lineWidth = activeStroke.width;
    ctx.strokeStyle = activeStroke.color;
    ctx.globalAlpha = activeStroke.tool === "HIGHLIGHTER" ? 0.35 : 1.0;

    ctx.moveTo(
      denormalizeCoordinate(prevPoint.x, A4_WIDTH),
      denormalizeCoordinate(prevPoint.y, A4_HEIGHT),
    );
    ctx.lineTo(
      denormalizeCoordinate(newPoint.x, A4_WIDTH),
      denormalizeCoordinate(newPoint.y, A4_HEIGHT),
    );
    ctx.stroke();
    ctx.restore();
  };

  const handlePointerUp = (e: React.PointerEvent<HTMLCanvasElement>) => {
    if (!isPointerDownRef.current) return;
    isPointerDownRef.current = false;
    setIsDrawing(false);

    const canvas = canvasRef.current;
    if (canvas && canvas.hasPointerCapture(e.pointerId)) {
      canvas.releasePointerCapture(e.pointerId);
    }

    const completed = activeStrokeRef.current;
    activeStrokeRef.current = null;

    if (completed && completed.points.length > 0) {
      onStrokesChange([...strokes, completed]);
    }
  };

  const getGridClassName = () => {
    switch (paperGrid) {
      case "grid":
        return styles.gridCaro;
      case "lines":
        return styles.gridRuled;
      default:
        return styles.gridPlain;
    }
  };

  return (
    <div
      className={styles.canvasViewport}
      style={{
        transform: `scale(${zoomLevel})`,
        transformOrigin: "top center",
      }}
    >
      <div className={`${styles.a4Sheet} ${getGridClassName()}`}>
        <canvas
          ref={canvasRef}
          className={`${styles.drawingCanvas} ${currentTool === "eraser" ? styles.eraserCursor : styles.penCursor}`}
          style={{
            width: `${A4_WIDTH}px`,
            height: `${A4_HEIGHT}px`,
            touchAction: "none",
          }}
          onPointerDown={handlePointerDown}
          onPointerMove={handlePointerMove}
          onPointerUp={handlePointerUp}
          onPointerCancel={handlePointerUp}
        />
      </div>
    </div>
  );
}
