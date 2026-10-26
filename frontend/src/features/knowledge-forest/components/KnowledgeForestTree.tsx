"use client";

import {
  ArrowLeft,
  ArrowRight,
  BookOpen,
  CheckCircle2,
  Compass,
  Layers,
  Orbit,
  RotateCcw,
  Sparkles,
  Target,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import { getMasteryStateLabel } from "../copy";
import { filterKnowledgeForest } from "../filter";
import type {
  KnowledgeChapterNode,
  KnowledgeProblemTypeNode,
  KnowledgeStatusFilter,
} from "../types";
import styles from "../KnowledgeForest.module.css";
import {
  getMathChapterType,
  MathChapterIllustration,
} from "./MathChapterIllustration";

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

const CHAPTER_THEMES = [
  { color: "#10b981", glow: "rgba(16, 185, 129, 0.22)", tag: "Khảo sát hàm số" },
  { color: "#0284c7", glow: "rgba(2, 132, 199, 0.22)", tag: "Mũ & Logarit" },
  { color: "#7c3aed", glow: "rgba(124, 58, 237, 0.22)", tag: "Vectơ Oxyz" },
  { color: "#d97706", glow: "rgba(217, 119, 6, 0.22)", tag: "Thống kê" },
  { color: "#e11d48", glow: "rgba(225, 29, 72, 0.22)", tag: "Tích phân" },
  { color: "#0d9488", glow: "rgba(13, 148, 136, 0.22)", tag: "Tọa độ không gian" },
  { color: "#059669", glow: "rgba(5, 150, 105, 0.22)", tag: "Xác suất" },
];

function shortLabel(value: string, length = 26): string {
  return value.length <= length ? value : `${value.slice(0, length - 1).trim()}…`;
}

function CircularMasteryRing({
  percent,
  color,
  size = 56,
}: {
  percent: number;
  color: string;
  size?: number;
}) {
  const strokeWidth = 4.5;
  const radius = (size - strokeWidth) / 2;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference - (Math.min(100, Math.max(0, percent)) / 100) * circumference;

  return (
    <div
      style={{
        position: "relative",
        width: size,
        height: size,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        flexShrink: 0,
      }}
    >
      <svg width={size} height={size} style={{ transform: "rotate(-90deg)" }}>
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke="rgba(16, 46, 38, 0.08)"
          strokeWidth={strokeWidth}
        />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke={color}
          strokeWidth={strokeWidth}
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          strokeLinecap="round"
          style={{ transition: "stroke-dashoffset 0.8s cubic-bezier(0.16, 1, 0.3, 1)" }}
        />
      </svg>
      <span
        style={{
          position: "absolute",
          fontSize: "0.74rem",
          fontWeight: 800,
          color: "#102e26",
        }}
      >
        {percent}%
      </span>
    </div>
  );
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
  // Resolve initial node target
  const initialChapterId = useMemo(() => {
    if (!initialNodeId) return null;
    for (const ch of chapters) {
      if (ch.id === initialNodeId) return ch.id;
      for (const t of ch.topics) {
        if (t.id === initialNodeId) return ch.id;
        if (t.problemTypes.some((pt) => pt.id === initialNodeId)) return ch.id;
      }
    }
    return null;
  }, [chapters, initialNodeId]);

  const [activeChapterId, setActiveChapterId] = useState<string | null>(initialChapterId);

  // Filtered chapters according to search and status filter
  const filtered = useMemo(
    () => filterKnowledgeForest({ chapters, concepts: [], searchQuery, statusFilter }),
    [chapters, searchQuery, statusFilter]
  );

  const writeNodeToHistory = useCallback((nodeId: string | null) => {
    const url = new URL(window.location.href);
    if (nodeId) url.searchParams.set("node", nodeId);
    else url.searchParams.delete("node");
    window.history.pushState(null, "", `${url.pathname}${url.search}${url.hash}`);
  }, []);

  const handleSelectChapter = (chapterId: string | null) => {
    setActiveChapterId(chapterId);
    writeNodeToHistory(chapterId);
    if (!chapterId) {
      onClearSelection();
    }
  };

  const handleSelectProblemTypeAndRecord = (pt: KnowledgeProblemTypeNode) => {
    onSelectProblemType(pt);
    writeNodeToHistory(pt.id);
  };

  // Synchronize URL popstate
  useEffect(() => {
    const handlePopState = () => {
      const nodeParam = new URL(window.location.href).searchParams.get("node");
      if (!nodeParam) {
        setActiveChapterId(null);
        return;
      }
      for (const ch of chapters) {
        if (ch.id === nodeParam) {
          setActiveChapterId(ch.id);
          return;
        }
        for (const t of ch.topics) {
          if (t.id === nodeParam || t.problemTypes.some((p) => p.id === nodeParam)) {
            setActiveChapterId(ch.id);
            return;
          }
        }
      }
    };
    window.addEventListener("popstate", handlePopState);
    return () => window.removeEventListener("popstate", handlePopState);
  }, [chapters]);

  // Initial selection trigger if initialNodeId is a leaf
  useEffect(() => {
    if (!initialNodeId) return;
    for (const ch of chapters) {
      for (const t of ch.topics) {
        const foundPt = t.problemTypes.find((p) => p.id === initialNodeId);
        if (foundPt) {
          onSelectProblemType(foundPt);
          return;
        }
      }
    }
  }, [chapters, initialNodeId, onSelectProblemType]);

  // Find active chapter object if in focused station mode
  const activeChapter = useMemo(
    () => chapters.find((c) => c.id === activeChapterId) || null,
    [activeChapterId, chapters]
  );

  const activeChapterIndex = useMemo(
    () => (activeChapter ? chapters.findIndex((c) => c.id === activeChapter.id) : 0),
    [activeChapter, chapters]
  );

  if (chapters.length === 0) {
    return (
      <div className={styles.emptyCard}>
        <Compass size={40} style={{ color: "#10b981", margin: "0 auto 12px" }} />
        <h3 className={styles.emptyTitle}>Chưa có cấu trúc Vũ trụ tri thức</h3>
        <p className={styles.emptyDesc}>
          Môn học này chưa có chương, chủ đề và dạng bài trong dữ liệu backend.
        </p>
      </div>
    );
  }

  if (filtered.totalMatchedCount === 0 && filtered.isFiltered) {
    return (
      <div className={styles.emptyCard}>
        <h3 className={styles.emptyTitle}>Không tìm thấy chòm sao tri thức phù hợp</h3>
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
      aria-label={`Vũ trụ tri thức môn ${subjectName}`}
    >
      {/* ====================================================================
          CELESTIAL FLOATING NAVIGATION BAR (LIGHT, AIRY & INTUITIVE)
          ==================================================================== */}
      <div className={styles.cosmicNavWrap}>
        <div className={styles.cosmicNavPills} role="tablist" aria-label="Điều hướng chòm sao">
          {/* Overview button */}
          <button
            type="button"
            className={`${styles.cosmicNavBtn} ${activeChapterId === null ? styles.cosmicNavBtnActive : ""}`}
            onClick={() => handleSelectChapter(null)}
            role="tab"
            aria-selected={activeChapterId === null}
          >
            <Orbit size={15} style={{ color: activeChapterId === null ? "#6ee7b7" : "#047857" }} />
            <span>Toàn cảnh Vũ Trụ ({chapters.length} chòm sao)</span>
          </button>

          {/* Chapter Quick Tabs */}
          {chapters.map((chapter, index) => {
            const theme = CHAPTER_THEMES[index % CHAPTER_THEMES.length];
            const isActive = activeChapterId === chapter.id;

            return (
              <button
                key={chapter.id}
                type="button"
                className={`${styles.cosmicNavBtn} ${isActive ? styles.cosmicNavBtnActive : ""}`}
                onClick={() => handleSelectChapter(chapter.id)}
                role="tab"
                aria-selected={isActive}
              >
                <span
                  style={{
                    width: "8px",
                    height: "8px",
                    borderRadius: "50%",
                    background: theme.color,
                    boxShadow: isActive ? `0 0 8px ${theme.color}` : "none",
                  }}
                />
                <span>
                  {index + 1}. {shortLabel(chapter.name, 18)}
                </span>
              </button>
            );
          })}
        </div>
      </div>

      {/* ====================================================================
          MAIN LUMINOUS COSMIC CANVAS (LIGHT PALETTE, REFINED & BREATHTAKING)
          ==================================================================== */}
      <div className={styles.luminousCosmicCanvas}>
        {/* Subtle Constellation Stardust Watermark */}
        <div
          style={{
            position: "absolute",
            top: 20,
            right: 30,
            fontSize: "12px",
            color: "rgba(16, 46, 38, 0.25)",
            fontFamily: "monospace",
            fontWeight: 700,
            pointerEvents: "none",
            userSelect: "none",
          }}
        >
          ✦ GALAXY MAP · {subjectName.toUpperCase()}
        </div>

        {/* ==================================================================
            MODE 1: TOÀN CẢNH HÀNH TRÌNH (ALL-CHAPTER CONSTELLATION ODYSSEY)
            ================================================================== */}
        {activeChapterId === null ? (
          <div>
            <div style={{ marginBottom: "22px" }}>
              <span
                style={{
                  display: "inline-flex",
                  alignItems: "center",
                  gap: "6px",
                  fontSize: "0.75rem",
                  fontWeight: 800,
                  textTransform: "uppercase",
                  letterSpacing: "0.08em",
                  color: "#047857",
                  background: "rgba(16, 185, 129, 0.12)",
                  padding: "4px 12px",
                  borderRadius: "999px",
                  marginBottom: "8px",
                }}
              >
                <Sparkles size={12} />
                Toàn Cảnh Hành Trình Tri Thức
              </span>
              <h2
                style={{
                  fontSize: "clamp(1.25rem, 2.5vw, 1.65rem)",
                  fontWeight: 800,
                  color: "#102e26",
                  margin: 0,
                  lineHeight: 1.3,
                }}
              >
                Khám phá 7 miền tri thức toán học qua các tinh cầu trực quan
              </h2>
            </div>

            <div className={styles.constellationJourneyGrid}>
              {filtered.filteredChapters.map((chapter, index) => {
                const mathType = getMathChapterType(chapter.name, index);
                const theme = CHAPTER_THEMES[mathType % CHAPTER_THEMES.length];
                const progress = chapter.masteryScore ?? 0;
                const totalPts = chapter.topics.reduce(
                  (sum, t) => sum + t.problemTypes.length,
                  0
                );

                return (
                  <div
                    key={chapter.id}
                    className={styles.constellationIslandCard}
                    onClick={() => handleSelectChapter(chapter.id)}
                    role="button"
                    tabIndex={0}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" || e.key === " ") {
                        handleSelectChapter(chapter.id);
                      }
                    }}
                  >
                    {/* Ambient Aura Glow in Corner */}
                    <span
                      className={styles.islandAuraGlow}
                      style={{ background: theme.glow }}
                      aria-hidden="true"
                    />

                    <div>
                      {/* Header Row: Chapter Pill + Circular Mastery Ring */}
                      <div
                        style={{
                          display: "flex",
                          alignItems: "center",
                          justifyContent: "space-between",
                          marginBottom: "14px",
                        }}
                      >
                        <span
                          style={{
                            display: "inline-flex",
                            alignItems: "center",
                            gap: "6px",
                            padding: "4px 12px",
                            borderRadius: "999px",
                            fontSize: "0.72rem",
                            fontWeight: 800,
                            textTransform: "uppercase",
                            letterSpacing: "0.06em",
                            background: `${theme.color}15`,
                            color: theme.color,
                            border: `1px solid ${theme.color}35`,
                          }}
                        >
                          <Sparkles size={11} />
                          Chương 0{index + 1}
                        </span>

                        <CircularMasteryRing
                          percent={progress}
                          color={theme.color}
                          size={50}
                        />
                      </div>

                      {/* Mathematical Problem-Type Visual Illustration */}
                      <div className={styles.islandIllustBox}>
                        <MathChapterIllustration
                          type={mathType}
                          index={index}
                          className={styles.topicIllustSvg}
                        />
                      </div>

                      {/* Chapter Title */}
                      <h3 className={styles.islandTitle} title={chapter.name}>
                        {chapter.name}
                      </h3>

                      {/* Topics Preview Badges */}
                      <div className={styles.islandTopicPills}>
                        {chapter.topics.slice(0, 3).map((topic) => (
                          <span key={topic.id} className={styles.islandTopicPillItem}>
                            <BookOpen size={11} style={{ color: theme.color }} />
                            {shortLabel(topic.name, 18)}
                          </span>
                        ))}
                        {chapter.topics.length > 3 ? (
                          <span
                            className={styles.islandTopicPillItem}
                            style={{ color: "#047857", fontWeight: 800 }}
                          >
                            +{chapter.topics.length - 3} chủ đề nữa
                          </span>
                        ) : null}
                      </div>
                    </div>

                    {/* Footer Row */}
                    <div className={styles.islandFooter}>
                      <span style={{ fontSize: "0.75rem", color: "#52675d", fontWeight: 700 }}>
                        {chapter.topics.length} chủ đề · {totalPts} dạng bài
                      </span>

                      <div className={styles.islandArrowBtn}>
                        <ArrowRight size={15} />
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        ) : (
          /* ==================================================================
              MODE 2: TRẠM VŨ TRỤ CHI TIẾT (FOCUSED CHAPTER CONSTELLATION STAGE)
              ================================================================== */
          <div className={styles.stationContainer}>
            {/* Left Column: Hero Planetary Station Card */}
            {activeChapter ? (
              <div className={styles.stationHeroCard}>
                <button
                  type="button"
                  className={styles.stationHeroBackBtn}
                  onClick={() => handleSelectChapter(null)}
                >
                  <ArrowLeft size={14} />
                  <span>Quay lại Toàn cảnh Vũ Trụ</span>
                </button>

                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "space-between",
                    gap: "10px",
                    marginBottom: "12px",
                  }}
                >
                  <span
                    style={{
                      display: "inline-flex",
                      alignItems: "center",
                      gap: "6px",
                      padding: "4px 12px",
                      borderRadius: "999px",
                      fontSize: "0.72rem",
                      fontWeight: 800,
                      textTransform: "uppercase",
                      letterSpacing: "0.06em",
                      background: `${CHAPTER_THEMES[activeChapterIndex % CHAPTER_THEMES.length].color}18`,
                      color: CHAPTER_THEMES[activeChapterIndex % CHAPTER_THEMES.length].color,
                      border: `1px solid ${CHAPTER_THEMES[activeChapterIndex % CHAPTER_THEMES.length].color}38`,
                    }}
                  >
                    <Sparkles size={11} />
                    Chương 0{activeChapterIndex + 1}
                  </span>

                  <span
                    style={{
                      fontSize: "0.72rem",
                      fontWeight: 700,
                      color: CHAPTER_THEMES[activeChapterIndex % CHAPTER_THEMES.length].color,
                      background: `${CHAPTER_THEMES[activeChapterIndex % CHAPTER_THEMES.length].color}14`,
                      padding: "3px 10px",
                      borderRadius: "999px",
                    }}
                  >
                    {getMasteryStateLabel(activeChapter.state)}
                  </span>
                </div>

                <h3
                  style={{
                    fontSize: "1.28rem",
                    fontWeight: 800,
                    color: "#102e26",
                    lineHeight: 1.35,
                    margin: "0 0 14px",
                  }}
                >
                  {activeChapter.name}
                </h3>

                {/* Mathematical Visual Illustration */}
                <div className={styles.stationHeroIllustBox}>
                  <MathChapterIllustration
                    type={getMathChapterType(activeChapter.name, activeChapterIndex)}
                    index={activeChapterIndex}
                    className={styles.topicIllustSvg}
                  />
                </div>

                {/* Circular Mastery Dial & Status Breakdown */}
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: "18px",
                    background: "rgba(16, 46, 38, 0.03)",
                    padding: "16px 18px",
                    borderRadius: "20px",
                    border: "1px solid rgba(16, 46, 38, 0.06)",
                  }}
                >
                  <CircularMasteryRing
                    percent={activeChapter.masteryScore ?? 0}
                    color={CHAPTER_THEMES[activeChapterIndex % CHAPTER_THEMES.length].color}
                    size={64}
                  />
                  <div>
                    <h4 style={{ margin: 0, fontSize: "0.92rem", fontWeight: 800, color: "#102e26" }}>
                      Độ thành thạo chuyên đề
                    </h4>
                    <p style={{ margin: "2px 0 0", fontSize: "0.78rem", color: "#52675d" }}>
                      {activeChapter.attemptCount > 0
                        ? `Đã luyện tập ${activeChapter.attemptCount} lượt giải bài`
                        : "Chưa có lượt giải nào"}
                    </p>
                  </div>
                </div>

                {/* Chapter Stats Grid */}
                <div className={styles.stationStatsGrid}>
                  <div className={styles.stationStatItem}>
                    <p className={styles.stationStatNum}>{activeChapter.topics.length}</p>
                    <p className={styles.stationStatLabel}>Chủ đề trọng tâm</p>
                  </div>
                  <div className={styles.stationStatItem}>
                    <p className={styles.stationStatNum}>
                      {activeChapter.topics.reduce((sum, t) => sum + t.problemTypes.length, 0)}
                    </p>
                    <p className={styles.stationStatLabel}>Dạng bài thi chuẩn</p>
                  </div>
                </div>
              </div>
            ) : null}

            {/* Right Column: Satellites Topics & Problem Types */}
            {activeChapter ? (
              <div className={styles.stationSatellitesList}>
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "space-between",
                    padding: "4px 8px",
                  }}
                >
                  <h4 style={{ fontSize: "1.05rem", fontWeight: 800, color: "#102e26", margin: 0 }}>
                    Các trạm Chủ đề & Dạng bài luyện tập
                  </h4>
                  <span style={{ fontSize: "0.78rem", color: "#52675d", fontWeight: 600 }}>
                    Click vào bất kỳ dạng bài nào để xem chi tiết
                  </span>
                </div>

                {activeChapter.topics.map((topic, topicIdx) => (
                  <div key={topic.id} className={styles.satelliteTopicCard}>
                    <div
                      style={{
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "space-between",
                        marginBottom: "12px",
                      }}
                    >
                      <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
                        <span
                          style={{
                            width: "28px",
                            height: "28px",
                            borderRadius: "10px",
                            display: "flex",
                            alignItems: "center",
                            justifyContent: "center",
                            fontSize: "0.78rem",
                            fontWeight: 800,
                            background: "rgba(16, 185, 129, 0.12)",
                            color: "#047857",
                          }}
                        >
                          {topicIdx + 1}
                        </span>
                        <h4
                          style={{
                            margin: 0,
                            fontSize: "0.95rem",
                            fontWeight: 750,
                            color: "#102e26",
                          }}
                        >
                          {topic.name}
                        </h4>
                      </div>

                      <span
                        style={{
                          fontSize: "0.72rem",
                          fontWeight: 700,
                          color: "#52675d",
                          background: "rgba(16, 46, 38, 0.05)",
                          padding: "3px 9px",
                          borderRadius: "8px",
                        }}
                      >
                        {topic.problemTypes.length} dạng bài
                      </span>
                    </div>

                    {/* Interactive Problem Type Star Chips */}
                    <div style={{ display: "flex", flexWrap: "wrap", gap: "8px" }}>
                      {topic.problemTypes.map((pt) => {
                        const isSelected = selectedId === pt.id;
                        let stateClass = styles.ptStarNotStarted;
                        if (pt.state === "MASTERED") stateClass = styles.ptStarMastered;
                        else if (pt.state === "LEARNING" || pt.state === "PRACTICING")
                          stateClass = styles.ptStarLearning;
                        else if (pt.state === "WEAK" || pt.state === "REVIEW_DUE")
                          stateClass = styles.ptStarReview;

                        return (
                          <button
                            key={pt.id}
                            type="button"
                            onClick={() => handleSelectProblemTypeAndRecord(pt)}
                            className={`${styles.problemTypeStarChip} ${stateClass}`}
                            style={
                              isSelected
                                ? { outline: "2px solid #10b981", outlineOffset: "1.5px" }
                                : undefined
                            }
                            title={`${pt.name} (${getMasteryStateLabel(pt.state)})`}
                          >
                            <span>{pt.name}</span>
                            {pt.masteryScore !== undefined && pt.attemptCount > 0 ? (
                              <span
                                style={{
                                  fontSize: "0.68rem",
                                  fontWeight: 800,
                                  opacity: 0.9,
                                }}
                              >
                                {pt.masteryScore}%
                              </span>
                            ) : null}
                          </button>
                        );
                      })}
                    </div>
                  </div>
                ))}
              </div>
            ) : null}
          </div>
        )}
      </div>

      {/* ====================================================================
          LEGEND FOOTER (LIGHT, REFINED & INFORMATIVE)
          ==================================================================== */}
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
          Đã thành thạo (Mastered)
        </span>
        <span>
          <i
            style={{
              display: "inline-block",
              width: "11px",
              height: "11px",
              borderRadius: "50%",
              background: "#0d9488",
              boxShadow: "0 0 8px #0d9488",
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
              background: "#e11d48",
              boxShadow: "0 0 8px #e11d48",
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
    </section>
  );
}
