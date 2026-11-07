"use client";



import { useEffect, useMemo, useRef, useState } from "react";

import type { Markmap } from "markmap-view";

import { MathRenderer } from "@/components/ui/MathRenderer";

import type { TheoryNode } from "./api";

import { scopeTheoryNodes, toMarkmapTree } from "./markmap-tree";

import {

  organizeTheoryNotebook,

  parseExampleBody,

  formatSolutionLines,

} from "./notebook-organizer";

import { Theory3DMapView } from "./Theory3DMapView";

import { TheoryBilateralMindmap } from "./TheoryBilateralMindmap";

import { TheorySourceViewer } from "./TheorySourceViewer";

import { TheoryLessonSource } from "./TheoryLessonSource";

import styles from "./TheoryMaps.module.css";



type RenderedNode = NonNullable<Markmap["state"]["data"]>;



function findRenderedNode(root: RenderedNode | undefined, id: string): RenderedNode | undefined {

  if (!root) return undefined;

  if (root.payload?.nodeId === id) return root;

  for (const child of root.children) {

    const found = findRenderedNode(child, id);

    if (found) return found;

  }

  return undefined;

}



function isValidLearningStep(st: { instruction: string; latex?: string | null }): boolean {

  const clean = st.instruction.replace(/^Bước\s*\d+[\:\.]\s*/i, "").trim();

  if (!clean || clean.includes("□")) return false;

  if (!st.latex && clean.split(/\s+/).length <= 2 && clean.length < 12) return false;

  return true;

}



function getKindBadgeLabel(kind: string, title: string): string {
  if (/^Dạng\s+/i.test(title)) return "🎯 Dạng bài toán";
  if (/^Định nghĩa\b/i.test(title)) return "📖 Định nghĩa";
  if (/^Định l[ýí]/i.test(title)) return "📖 Định lý";
  if (/^(Nhận xét|Chú ý|Lưu ý|⚠️)/i.test(title)) return "⚠️ Chú ý & Bẫy sai lầm";
  if (/^(Mẹo|Công thức giải nhanh|Tính chất đặc biệt|⚡)/i.test(title)) return "⚡ Mẹo giải nhanh";

  switch (kind) {
    case "CHAPTER":
      return "📚 Chương bài học";
    case "SECTION":
      return "📌 Phần bài học";
    case "CONCEPT":
      return "📖 Khái niệm & Định lý";
    case "FORMULA":
      return "📐 Công thức trọng tâm";
    case "METHOD":
      return "📝 Dạng toán & Phương pháp";
    case "EXAMPLE":
      return "💡 Ví dụ mẫu";
    case "NOTE":
      return "⚠️ Chú ý & Bẫy sai lầm";
    case "QUICK_TRICK":
      return "⚡ Mẹo giải nhanh";
    default:
      return "🌿 Mục học";
  }
}



export interface TheoryMapViewProps {

  nodes: TheoryNode[];

  selectedNodeId?: string;

  onSelectNode?: (id: string) => void;

  sourceUrl?: string;

  sourceTitle?: string;

  sourcePageCount?: number;

  initialSourcePage?: number;

  onEditNode?: (id: string) => void;

  onAddChildNode?: (parentId: string) => void;

  onDeleteNode?: (id: string) => void;

  isTeacher?: boolean;

  onOpenNotebook?: (page: number) => void;

  onOpenSource?: (page: number) => void;

}



export function TheoryMapView({

  nodes,

  selectedNodeId,

  onSelectNode,

  sourceUrl,

  sourceTitle,

  sourcePageCount,

  initialSourcePage,

  onEditNode,

  isTeacher = false,

  onOpenNotebook,

  onOpenSource,

}: TheoryMapViewProps) {

  // View Modes: "bilateral" (Sơ đồ tỏa từ tâm - Default), "markmap" (Nhánh ngang), "3d" (Không gian 3D), "source" (PDF gốc)

  const [viewMode, setViewMode] = useState<"bilateral" | "markmap" | "3d" | "source">("bilateral");



  // Search & Branch Selection

  const [searchQuery, setSearchQuery] = useState("");

  const [searchResults, setSearchResults] = useState<TheoryNode[]>([]);



  // Floating detail modal / drawer state

  const [floatingDetailNodeId, setFloatingDetailNodeId] = useState<string | null>(selectedNodeId ?? null);

  const [isFullscreen, setIsFullscreen] = useState(false);

  const [copiedLatexId, setCopiedLatexId] = useState<string | null>(null);



  // Markmap Canvas Refs

  const markmapContainerRef = useRef<HTMLDivElement>(null);

  const svgRef = useRef<SVGSVGElement>(null);

  const mapRef = useRef<Markmap | null>(null);

  const lastScopeRef = useRef("");

  const [markmapReady, setMarkmapReady] = useState(false);



  // Hierarchy

  const root = useMemo(() => nodes.find((n) => n.parent_id === null), [nodes]);

  const branches = useMemo(() => (root ? nodes.filter((n) => n.parent_id === root.id) : []), [nodes, root]);

  const [scopeId, setScopeId] = useState(() =>

    nodes.length > 25 && branches.length > 1 ? branches[0].id : root?.id ?? ""

  );



  const visibleMarkmapNodes = useMemo(() => scopeTheoryNodes(nodes, scopeId), [nodes, scopeId]);

  const markmapTreeData = useMemo(() => toMarkmapTree(visibleMarkmapNodes), [visibleMarkmapNodes]);



  // Structured Notebook Organization (Sections, Topics, Formulas, Methods, Examples, Traps)

  const { sections } = useMemo(() => organizeTheoryNotebook(nodes), [nodes]);



  // Overall Statistics Counter

  const stats = useMemo(() => {

    let topics = 0;

    let formulas = 0;

    let examples = 0;

    for (const sec of sections) {

      topics += sec.topics.length;

      for (const t of sec.topics) {

        formulas += t.formulas.length + (t.concept.latex ? 1 : 0);

        examples += t.examples.length;

      }

    }

    return {

      sectionsCount: sections.length,

      topicsCount: topics,

      formulasCount: formulas,

      examplesCount: examples,

    };

  }, [sections]);



  // Sync external selectedNodeId

  useEffect(() => {

    if (selectedNodeId && nodes.some((n) => n.id === selectedNodeId)) {

      setFloatingDetailNodeId(selectedNodeId);

      // Auto-center node in Markmap

      if (mapRef.current) {

        const rendered = findRenderedNode(mapRef.current.state.data, selectedNodeId);

        if (rendered) void mapRef.current.centerNode(rendered);

      }

    }

  }, [selectedNodeId, nodes]);



  // Search logic

  useEffect(() => {

    if (!searchQuery.trim()) {

      setSearchResults([]);

      return;

    }

    const q = searchQuery.toLowerCase();

    const hits = nodes.filter(

      (n) =>

        n.title.toLowerCase().includes(q) ||

        n.body.toLowerCase().includes(q) ||

        (n.latex && n.latex.toLowerCase().includes(q))

    ).slice(0, 6);

    setSearchResults(hits);

  }, [searchQuery, nodes]);



  // Markmap initialization

  useEffect(() => {

    if (viewMode !== "markmap" || !svgRef.current) return;

    let disposed = false;

    let instance: Markmap | undefined;

    const svg = svgRef.current;

    void import("markmap-view").then(({ Markmap }) => {

      if (disposed) return;

      const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

      instance = new Markmap(svg, {

        autoFit: false,

        duration: reduced ? 0 : 200,

        maxWidth: 360,

        pan: true,

        zoom: true,

        fitRatio: 0.92,

        color: (node) => (node.state.depth === 0 ? "#14593e" : node.state.depth === 1 ? "#2a7f5a" : "#8c7e3e"),

      });

      mapRef.current = instance;

      setMarkmapReady(true);

    }).catch(() => {});

    return () => {

      disposed = true;

      if (mapRef.current === instance) mapRef.current = null;

      instance?.destroy();

    };

  }, [viewMode]);



  // Markmap data update

  useEffect(() => {

    const instance = mapRef.current;

    if (viewMode !== "markmap" || !markmapReady || !instance || !markmapTreeData) return;

    let cancelled = false;

    const timer = window.setTimeout(() => {

      void instance.setData(markmapTreeData).then(async () => {

        if (cancelled) return;

        instance.g.selectAll("g.markmap-node").on("click.theory", (_event: MouseEvent, data: unknown) => {

          const id = (data as RenderedNode).payload?.nodeId;

          if (typeof id === "string") {

            setFloatingDetailNodeId(id);

            onSelectNode?.(id);

          }

        });

        if (lastScopeRef.current !== scopeId) {

          lastScopeRef.current = scopeId;

          await instance.fit();

        }

      });

    }, 100);

    return () => {

      cancelled = true;

      window.clearTimeout(timer);

    };

  }, [viewMode, markmapReady, markmapTreeData, scopeId, onSelectNode]);



  function handleZoom(direction: "in" | "out" | "fit") {

    if (!mapRef.current) return;

    if (direction === "in") void mapRef.current.rescale(1.25);

    else if (direction === "out") void mapRef.current.rescale(0.8);

    else void mapRef.current.fit();

  }



  function toggleFullscreen() {

    if (!markmapContainerRef.current) return;

    if (!document.fullscreenElement) {

      void markmapContainerRef.current.requestFullscreen().then(() => setIsFullscreen(true)).catch(() => {});

    } else {

      void document.exitFullscreen().then(() => setIsFullscreen(false)).catch(() => {});

    }

  }



  function handleSelectNodeById(id: string) {

    setFloatingDetailNodeId(id);

    onSelectNode?.(id);

    setSearchQuery("");

    setSearchResults([]);

    if (mapRef.current) {

      const rendered = findRenderedNode(mapRef.current.state.data, id);

      if (rendered) void mapRef.current.centerNode(rendered);

    }

  }



  // Copy LaTeX

  function handleCopyLatex(latex: string, id: string) {

    if (!navigator.clipboard) return;

    navigator.clipboard.writeText(latex).then(() => {

      setCopiedLatexId(id);

      setTimeout(() => setCopiedLatexId(null), 2000);

    }).catch(() => {});

  }



  // Pedagogical data for the Floating Detail Drawer

  const floatingDetailData = useMemo(() => {

    if (!floatingDetailNodeId) return null;

    const foundNode = nodes.find((n) => n.id === floatingDetailNodeId);

    if (!foundNode) return null;



    // Search in structured sections & topics

    for (const sec of sections) {

      for (const top of sec.topics) {

        if (

          top.concept.id === foundNode.id ||

          top.formulas.some((f) => f.id === foundNode.id) ||

          top.methods.some((m) => m.id === foundNode.id) ||

          top.examples.some((ex) => ex.id === foundNode.id) ||

          top.notes.some((no) => no.id === foundNode.id)

        ) {

          return { section: sec.section, topic: top, targetNode: foundNode };

        }

      }

    }

    return { section: null, topic: null, targetNode: foundNode };

  }, [floatingDetailNodeId, nodes, sections]);



  // Floating detail drawer content renderer

  const renderFloatingDrawer = () => {

    if (!floatingDetailData) return null;

    const target = floatingDetailData.targetNode;



    // Check availability of clean, pedagogical details

    const topicMethods = (floatingDetailData.topic?.methods || [])

      .map((m) => ({

        ...m,

        learning_steps: m.learning_steps.filter(isValidLearningStep),

      }))

      .filter((m) => m.learning_steps.length > 0 || Boolean(m.latex) || Boolean(m.body));



    const standaloneSteps = (target.learning_steps || []).filter(isValidLearningStep);



    const hasTopicDetails = Boolean(

      floatingDetailData.topic?.concept.id === target.id && (

        floatingDetailData.topic.concept.body ||

        floatingDetailData.topic.formulas.length > 0 ||

        topicMethods.length > 0 ||

        floatingDetailData.topic.examples.length > 0 ||

        floatingDetailData.topic.notes.length > 0

      )

    );



    const hasStandaloneDetails = Boolean(

      target.body || target.latex || standaloneSteps.length > 0

    );



    const hasAnyContent = hasTopicDetails || hasStandaloneDetails;



    return (

      <div className={styles.floatingDrawerOverlay} role="region" aria-label={`Nội dung ${target.title}`}>

        {/* Drawer Header */}

        <div className={styles.drawerHeaderRow}>

          <div>

            <span className={styles.inlineTopicBadge}>

              {getKindBadgeLabel(target.kind, target.title)} &bull; Trang {target.source_page}

            </span>

            <h4 className={styles.inlineTopicTitle} style={{ marginTop: "6px" }}>

              {target.title}

            </h4>

            <div style={{ display: "flex", gap: "8px", flexWrap: "wrap", marginTop: "10px" }}>

              {onOpenNotebook && !sourceUrl && (

                <button

                  type="button"

                  className={styles.drawerPrimaryActionBtn}

                  onClick={() => onOpenNotebook(target.source_page)}

                  title="Mở nội dung trong Sổ tay bài học"

                >

                  📖 Mở Sổ tay bài học

                </button>

              )}

              {onOpenSource && (

                <button

                  type="button"

                  className={styles.drawerSecondaryActionBtn}

                  onClick={() => onOpenSource(target.source_page)}

                  title="Xem trang gốc trong tài liệu PDF"

                >

                  📄 Mở PDF gốc trang {target.source_page}

                </button>

              )}
              <a
                href={`/student/practice?topic=${encodeURIComponent(target.title)}`}
                className={styles.drawerPrimaryActionBtn}
                style={{
                  background: "linear-gradient(135deg, #23a67a, #10b981)",
                  color: "#ffffff",
                  textDecoration: "none",
                  display: "inline-flex",
                  alignItems: "center",
                  gap: "6px",
                  padding: "6px 12px",
                  borderRadius: "8px",
                  fontWeight: 650,
                  fontSize: "0.82rem",
                  boxShadow: "0 2px 8px rgba(35, 166, 122, 0.3)",
                }}
                title="Luyện giải bài tập dạng này trên giấy số"
              >
                ✍️ Luyện bài tập dạng này
              </a>

            </div>

          </div>

          <button

            type="button"

            className={styles.drawerCloseButton}

            onClick={() => setFloatingDetailNodeId(null)}

            aria-label="Đóng bảng chi tiết"

          >

            ✕

          </button>

        </div>



        {sourceUrl && <TheoryLessonSource node={target} sourceUrl={sourceUrl} />}

        {!sourceUrl && !hasAnyContent && (

          <p className={styles.lessonSourceNotice}>Mục này chưa có nội dung đã trích xuất và tài liệu gốc chưa được chia sẻ.</p>

        )}



        {/* Pedagogical Details (From Structured Topic) */}

        {floatingDetailData.topic && hasTopicDetails && (

          <div style={{ display: "flex", flexDirection: "column", gap: "14px" }}>

            {/* Bản chất lý thuyết */}

            {floatingDetailData.topic.concept.body && (

              <div className={styles.inlineConceptCallout}>

                <div style={{ fontWeight: 800, color: "#14593e", marginBottom: "4px", fontSize: ".85rem" }}>

                  📖 Bản chất lý thuyết &amp; Nhận diện

                </div>

                <MathRenderer content={floatingDetailData.topic.concept.body} />

              </div>

            )}



            {/* Bảng công thức trọng tâm */}

            {floatingDetailData.topic.formulas.length > 0 && (

              <div className={styles.inlineFormulaBlock}>

                <div className={styles.inlineFormulaHeading}>

                  <span>📐</span>

                  <span>Công thức trọng tâm</span>

                </div>

                {floatingDetailData.topic.formulas.map((fNode) => (

                  <div key={fNode.id} style={{ display: "flex", flexDirection: "column", gap: "6px" }}>

                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>

                      <strong style={{ fontSize: ".88rem", color: "#145236" }}>

                        {fNode.title === floatingDetailData.topic.concept.title ? "\u0043\u00F4ng th\u1EE9c tr\u1ECDng t\u00E2m" : fNode.title.replace(/^[\uD83D\uDCD0]?\s*(?:C\u00F4ng th\u1EE9c:\s*)?/i, "")}

                      </strong>

                      {fNode.latex && (

                        <button

                          type="button"

                          className={styles.copyLatexBtn}

                          onClick={() => handleCopyLatex(fNode.latex!, fNode.id)}

                          title="Sao chép công thức KaTeX"

                        >

                          {copiedLatexId === fNode.id ? "✓ Đã copy!" : "📋 Copy LaTeX"}

                        </button>

                      )}

                    </div>

                    {fNode.latex && (

                      <div className={styles.katexFormulaDisplay}>

                        <MathRenderer content={fNode.latex} inline={false} />

                      </div>

                    )}

                    {fNode.body && fNode.body !== floatingDetailData.topic.concept.body && (

                      <div className={styles.formulaConditionText}>

                        <MathRenderer content={fNode.body} />

                      </div>

                    )}

                  </div>

                ))}

              </div>

            )}



            {/* Quy trình các bước giải (Chỉ render các bước hợp lệ, không chứa ký tự lỗi) */}

            {topicMethods.length > 0 && (

              <div className={styles.inlineMethodBlock}>

                <div className={styles.inlineMethodHeading}>

                  <span>📝</span>

                  <span>Quy trình giải từng bước</span>

                </div>

                {topicMethods.map((mNode) => (

                  <div key={mNode.id} style={{ display: "flex", flexDirection: "column", gap: "8px" }}>

                    {mNode.body && (

                      <div style={{ fontSize: ".88rem", color: "#2d3748" }}>

                        <MathRenderer content={mNode.body} />

                      </div>

                    )}

                    {mNode.learning_steps.length > 0 && (

                      <ol className={styles.inlineStepList}>

                        {mNode.learning_steps.map((st, sIdx) => (

                          <li key={sIdx} className={styles.inlineStepItem}>

                            <span className={styles.stepBadgeNumber}>Bước {sIdx + 1}</span>

                            <div className={styles.stepInstructionContent}>

                              <MathRenderer content={st.instruction.replace(/^Bước\s*\d+[\:\.]\s*/i, "")} />

                              {st.latex && (

                                <div className={styles.stepLatexCard}>

                                  <MathRenderer content={`$$${st.latex}$$`} />

                                </div>

                              )}

                            </div>

                          </li>

                        ))}

                      </ol>

                    )}

                    {mNode.latex && (

                      <div className={styles.stepLatexCard}>

                        <MathRenderer content={`$$${mNode.latex}$$`} />

                      </div>

                    )}

                  </div>

                ))}

              </div>

            )}



            {/* Ví dụ minh họa thực chiến */}

            {floatingDetailData.topic.examples.length > 0 && (

              <div className={styles.inlineExampleBlock}>

                <div className={styles.inlineExampleHeading}>

                  <span>💡</span>

                  <span>Ví dụ minh họa &amp; Hướng dẫn giải</span>

                </div>

                {floatingDetailData.topic.examples.map((exNode) => {

                  const { question, solution } = parseExampleBody(exNode.body);

                  const solutionLines = formatSolutionLines(solution);

                  return (

                    <div key={exNode.id} className={styles.inlineExampleCard}>

                      <div className={styles.inlineExampleHeaderRow}>

                        <span className={styles.exampleTitleText}>

                          {exNode.title.replace(/^💡\s*(?:Ví dụ:\s*)?/i, "")}

                        </span>

                        <small style={{ color: "#78531a" }}>Trang {exNode.source_page}</small>

                      </div>

                      {question && (

                        <div className={styles.exampleQuestionBox}>

                          <div style={{ fontWeight: 800, fontSize: ".8rem", marginBottom: "4px" }}>Đề bài:</div>

                          <MathRenderer content={question} />

                        </div>

                      )}

                      {solution && (

                        <div className={styles.exampleSolutionBox}>

                          <div style={{ fontWeight: 800, color: "#195c3e", fontSize: ".8rem" }}>Lời giải chi tiết:</div>

                          {solutionLines.map((line, lIdx) => (

                            <div key={lIdx} className={styles.solutionLineItem}>

                              <MathRenderer content={line} />

                            </div>

                          ))}

                        </div>

                      )}

                      {exNode.latex && (

                        <div className={styles.inlineResultBox}>

                          <span className={styles.inlineResultLabel}>Đáp số:</span>

                          <MathRenderer content={`$$${exNode.latex}$$`} />

                        </div>

                      )}

                    </div>

                  );

                })}

              </div>

            )}



            {/* Bẫy sai lầm & Phòng tránh */}

            {floatingDetailData.topic.notes.length > 0 && (

              <div className={styles.inlineTrapBlock}>

                <div className={styles.inlineTrapHeading}>

                  <span>⚠️</span>

                  <span>Bẫy sai lầm &amp; Mẹo phòng tránh</span>

                </div>

                {floatingDetailData.topic.notes.map((nNode) => (

                  <div key={nNode.id} className={styles.inlineTrapItem}>

                    <strong style={{ display: "block", marginBottom: "4px", color: "#991b1b" }}>

                      {nNode.title.replace(/^⚠️\s*(?:Bẫy sai lầm:\s*)?/i, "")}

                    </strong>

                    {nNode.latex && (

                      <div style={{ margin: "6px 0" }}>

                        <MathRenderer content={`$$${nNode.latex}$$`} />

                      </div>

                    )}

                    {nNode.body && <MathRenderer content={nNode.body} />}

                  </div>

                ))}

              </div>

            )}

          </div>

        )}



        {/* Standalone node detail (when no topic wrapper, but node has standalone content) */}

        {(!floatingDetailData.topic || floatingDetailData.topic.concept.id !== target.id) && hasStandaloneDetails && (

          <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>

            {target.body && (

              <div className={styles.inlineConceptCallout}>

                <MathRenderer content={target.body} />

              </div>

            )}

            {target.latex && (

              <div className={styles.inlineFormulaBlock}>

                <div className={styles.katexFormulaDisplay}>

                  <MathRenderer content={target.latex} inline={false} />

                </div>

              </div>

            )}

            {standaloneSteps.length > 0 && (

              <div className={styles.inlineMethodBlock}>

                <div className={styles.inlineMethodHeading}>

                  <span>📝</span>

                  <span>Quy trình thực hiện</span>

                </div>

                <ol className={styles.inlineStepList}>

                  {standaloneSteps.map((st, sIdx) => (

                    <li key={sIdx} className={styles.inlineStepItem}>

                      <span className={styles.stepBadgeNumber}>Bước {sIdx + 1}</span>

                      <div className={styles.stepInstructionContent}>

                        <MathRenderer content={st.instruction.replace(/^Bước\s*\d+[\:\.]\s*/i, "")} />

                        {st.latex && (

                          <div className={styles.stepLatexCard}>

                            <MathRenderer content={`$$${st.latex}$$`} />

                          </div>

                        )}

                      </div>

                    </li>

                  ))}

                </ol>

              </div>

            )}

          </div>

        )}



        {/* Teacher In-place Edit Button (Only visible for teachers) */}

        {isTeacher && onEditNode && (

          <button

            type="button"

            className={styles.topicActionBtn}

            style={{ alignSelf: "flex-start", marginTop: "4px" }}

            onClick={() => {

              onEditNode(target.id);

              const el = document.getElementById("theory-node-editor");

              if (el) el.scrollIntoView({ behavior: "smooth", block: "start" });

            }}

          >

            ✏️ Chỉnh sửa nhánh này trong biểu mẫu

          </button>

        )}



        {/* Source PDF Link Footer (Safely padded from bottom watermark) */}

        {sourceUrl && (

          <div className={styles.inlineCitationFooter}>

            <span>Trang {target.source_page} &bull; Tài liệu gốc</span>

            {onOpenSource ? (

              <button

                type="button"

                className={styles.pdfCitationLink}

                style={{ background: "transparent", border: 0, cursor: "pointer", font: "inherit", padding: 0 }}

                onClick={() => onOpenSource(target.source_page)}

              >

                📄 Mở trang {target.source_page} trong PDF ↗

              </button>

            ) : (

              <a

                className={styles.pdfCitationLink}

                href={`${sourceUrl}#page=${target.source_page}`}

                target="_blank"

                rel="noopener noreferrer"

              >

                📄 Mở trang {target.source_page} trong PDF ↗

              </a>

            )}

          </div>

        )}

      </div>

    );

  };



  if (!nodes || nodes.length === 0) {

    return (

      <div className={styles.notice}>

        <p>Chưa có dữ liệu sơ đồ để hiển thị.</p>

      </div>

    );

  }



  return (

    <div className={styles.unifiedMapLayout}>

      {/* 1. TOP CONTROL BAR: View Mode Switcher, Branch Scope, Search, Stats */}

      <div className={styles.mindmapControlBar}>

        {/* View Mode Tabs */}

        <div className={styles.viewModeGroup} role="tablist" aria-label="Chế độ hiển thị sơ đồ">

          <button

            type="button"

            className={`${styles.viewModeBtn} ${viewMode === "bilateral" ? styles.viewModeBtnActive : ""}`}

            onClick={() => setViewMode("bilateral")}

            role="tab"

            aria-selected={viewMode === "bilateral"}

          >

            🌟 Tỏa từ tâm (Xung quanh)

          </button>

          <button

            type="button"

            className={`${styles.viewModeBtn} ${viewMode === "markmap" ? styles.viewModeBtnActive : ""}`}

            onClick={() => setViewMode("markmap")}

            role="tab"

            aria-selected={viewMode === "markmap"}

          >

            ➡️ Nhánh ngang 1 chiều

          </button>

          <button

            type="button"

            className={`${styles.viewModeBtn} ${viewMode === "3d" ? styles.viewModeBtnActive : ""}`}

            onClick={() => setViewMode("3d")}

            role="tab"

            aria-selected={viewMode === "3d"}

          >

            🌐 Không gian 3D

          </button>

          {sourceUrl && isTeacher && (

            <button

              type="button"

              className={`${styles.viewModeBtn} ${viewMode === "source" ? styles.viewModeBtnActive : ""}`}

              onClick={() => setViewMode("source")}

              role="tab"

              aria-selected={viewMode === "source"}

            >

              📄 Tài liệu PDF gốc

            </button>

          )}

        </div>



        {/* Global Stats Badge (Shown for teacher cockpit) */}

        {isTeacher && (

          <div className={styles.statBadgeCounter}>

            <span>📚 {stats.sectionsCount} bài học</span>

            <span>&bull;</span>

            <span>🎯 {stats.topicsCount} dạng bài</span>

            <span>&bull;</span>

            <span>📐 {stats.formulasCount} công thức</span>

            <span>&bull;</span>

            <span>💡 {stats.examplesCount} ví dụ</span>

          </div>

        )}



        {/* Scope and Search */}

        <div className={styles.controlActionsGroup}>

          <div className={styles.mapSearchBox}>

            <span aria-hidden="true">🔍</span>

            <input

              type="search"

              placeholder="Tìm công thức, dạng bài..."

              value={searchQuery}

              onChange={(e) => setSearchQuery(e.target.value)}

              className={styles.mapSearchInput}

            />

            {searchQuery && (

              <button

                type="button"

                onClick={() => setSearchQuery("")}

                className={styles.mapSearchClear}

                aria-label="Xóa tìm kiếm"

              >

                ✕

              </button>

            )}



            {/* Live Search Suggestions Dropdown */}

            {searchResults.length > 0 && (

              <div className={styles.searchSuggestions}>

                {searchResults.map((item) => (

                  <button

                    key={item.id}

                    type="button"

                    className={styles.searchSuggestionItem}

                    onClick={() => handleSelectNodeById(item.id)}

                  >

                    <span>{item.title}</span>

                    <small>Trang {item.source_page}</small>

                  </button>

                ))}

              </div>

            )}

          </div>



          <label className={styles.scopeControl}>

            Xem bài:

            <select

              value={scopeId}

              onChange={(e) => {

                const id = e.target.value;

                setScopeId(id);

                setFloatingDetailNodeId(id);

                onSelectNode?.(id);

              }}

            >

              <option value={root?.id ?? ""}>Toàn bộ sơ đồ</option>

              {branches.map((b) => (

                <option key={b.id} value={b.id}>

                  {b.title}

                </option>

              ))}

            </select>

          </label>

        </div>

      </div>



      {/* 2. MODE: BILATERAL (SƠ ĐỒ TƯ DUY TỎA TỪ TÂM RA XUNG QUANH - DEFAULT) */}

      {viewMode === "bilateral" && (

        <div className={styles.fullMarkmapWrapper}>

          <TheoryBilateralMindmap

            nodes={nodes}

            selectedNodeId={floatingDetailNodeId ?? selectedNodeId}

            scopeId={scopeId}

            onSelectNode={handleSelectNodeById}

            onEditNode={onEditNode}

          />

          {renderFloatingDrawer()}

        </div>

      )}



      {/* 3. MODE: MARKMAP (SƠ ĐỒ TƯ DUY 1 CHIỀU - TRÁI SANG PHẢI) */}

      {viewMode === "markmap" && (

        <div className={styles.fullMarkmapWrapper} ref={markmapContainerRef}>

          {/* Zoom and Fullscreen Toolbar */}

          <div className={styles.mapToolbar}>

            <span className={styles.eyebrow} style={{ fontSize: ".8rem" }}>

              🌿 Sơ đồ tư duy 1 chiều (Trái sang Phải)

            </span>



            <div className={styles.mapZoomControls}>

              <button

                type="button"

                className={styles.zoomBtn}

                onClick={() => handleZoom("in")}

                title="Phóng to sơ đồ"

              >

                ＋

              </button>

              <button

                type="button"

                className={styles.zoomBtn}

                onClick={() => handleZoom("out")}

                title="Thu nhỏ sơ đồ"

              >

                －

              </button>

              <button

                type="button"

                className={styles.fitBtn}

                onClick={() => handleZoom("fit")}

                title="Căn vừa khung hình"

              >

                🎯 Vừa khung

              </button>

              <button

                type="button"

                className={styles.fullscreenBtn}

                onClick={toggleFullscreen}

                title={isFullscreen ? "Thu nhỏ" : "Toàn màn hình"}

              >

                {isFullscreen ? "🗗 Thu nhỏ" : "🔲 Toàn màn hình"}

              </button>

            </div>

          </div>



          {/* Markmap SVG Canvas - Takes 100% full width */}

          <svg ref={svgRef} className={styles.mapSvg} aria-label="Sơ đồ tư duy tương tác toàn màn hình" />



          {/* User Operation Hint Bar */}

          <div className={styles.mapHintBar}>

            <span>

              💡 <strong>Thao tác trực tiếp:</strong> Kéo chuột để di chuyển canvas • Cuộn chuột để phóng to/thu nhỏ • Bấm nút tròn để mở/gập cành nhánh • <strong>Bấm vào tên nhánh bất kỳ</strong> để mở bảng công thức &amp; ví dụ giải chi tiết ngay trên sơ đồ!

            </span>

          </div>



          {renderFloatingDrawer()}

        </div>

      )}



      {/* 3. MODE: 3D (KHÔNG GIAN TRI THỨC 3D TOÀN MÀN HÌNH) */}

      {viewMode === "3d" && (

        <Theory3DMapView

          nodes={nodes}

          selectedNodeId={floatingDetailNodeId ?? selectedNodeId}

          onSelectNode={(id) => {

            setFloatingDetailNodeId(id);

            onSelectNode?.(id);

          }}

          sourceUrl={sourceUrl}

        />

      )}



      {/* 4. MODE: SOURCE (XEM TÀI LIỆU PDF GỐC) */}

      {viewMode === "source" && sourceUrl && (

        <TheorySourceViewer

          url={sourceUrl}

          title={sourceTitle ?? "Tài liệu PDF gốc"}

          pageCount={sourcePageCount ?? 1}

          page={initialSourcePage ?? 1}

        />

      )}

    </div>

  );

}

