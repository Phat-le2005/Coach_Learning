"use client";

import { useMemo, useState } from "react";
import { MathRenderer } from "@/components/ui/MathRenderer";
import type { TheoryNode } from "./api";
import {
  organizeTheoryNotebook,
  parseExampleBody,
  formatSolutionLines,
  type ParsedSection,
  type ParsedTopic,
} from "./notebook-organizer";
import styles from "./TheoryMaps.module.css";

interface TheoryStudyNotebookProps {
  nodes: TheoryNode[];
  selectedNodeId?: string;
  onSelectNode?: (id: string) => void;
  onOpenInMindmap?: (id: string) => void;
  onEditNode?: (nodeId: string) => void;
  sourceUrl?: string;
  isTeacher?: boolean;
}

export function TheoryStudyNotebook({
  nodes,
  selectedNodeId,
  onSelectNode,
  onOpenInMindmap,
  onEditNode,
  sourceUrl,
  isTeacher = false,
}: TheoryStudyNotebookProps) {
  const [searchTerm, setSearchTerm] = useState("");
  const [activeSectionId, setActiveSectionId] = useState<string>("all");
  const [expandedTopics, setExpandedTopics] = useState<Record<string, boolean>>({});

  const { root, sections: parsedSections } = useMemo(() => organizeTheoryNotebook(nodes), [nodes]);

  // Filter sections & topics based on search term and active section tab
  const filteredSections = useMemo(() => {
    let result = parsedSections;

    if (activeSectionId !== "all") {
      result = result.filter((s) => s.section.id === activeSectionId);
    }

    if (searchTerm.trim()) {
      const q = searchTerm.toLowerCase();
      result = result
        .map((s) => {
          const matchingTopics = s.topics.filter(
            (t) =>
              t.concept.title.toLowerCase().includes(q) ||
              t.concept.body.toLowerCase().includes(q) ||
              t.formulas.some((f) => f.title.toLowerCase().includes(q) || (f.latex && f.latex.toLowerCase().includes(q))) ||
              t.methods.some((m) => m.title.toLowerCase().includes(q) || m.learning_steps.some((step) => step.instruction.toLowerCase().includes(q))) ||
              t.examples.some((e) => e.title.toLowerCase().includes(q) || e.body.toLowerCase().includes(q)) ||
              t.notes.some((n) => n.title.toLowerCase().includes(q) || n.body.toLowerCase().includes(q))
          );
          const matchesSection = s.section.title.toLowerCase().includes(q) || s.section.body.toLowerCase().includes(q);
          if (matchesSection || matchingTopics.length > 0) {
            return {
              ...s,
              topics: matchingTopics.length > 0 ? matchingTopics : s.topics,
            };
          }
          return null;
        })
        .filter((s): s is ParsedSection => s !== null);
    }

    return result;
  }, [parsedSections, activeSectionId, searchTerm]);

  function toggleTopic(id: string) {
    setExpandedTopics((old) => ({
      ...old,
      [id]: old[id] === undefined ? false : !old[id],
    }));
  }

  function expandAll() {
    const next: Record<string, boolean> = {};
    parsedSections.forEach((s) => s.topics.forEach((t) => (next[t.concept.id] = true)));
    setExpandedTopics(next);
  }

  function collapseAll() {
    const next: Record<string, boolean> = {};
    parsedSections.forEach((s) => s.topics.forEach((t) => (next[t.concept.id] = false)));
    setExpandedTopics(next);
  }

  if (!nodes.length) {
    return (
      <div className={styles.emptyStateCard}>
        <div className={styles.emptyStateIcon}>📖</div>
        <h3>Chưa có dữ liệu sổ tay học tập</h3>
        <p>Tài liệu chưa được phân tích. Hãy bấm &ldquo;Tạo sơ đồ tư duy bằng AI&rdquo; để khởi tạo sổ tay ghi chép.</p>
      </div>
    );
  }

  return (
    <div className={styles.studyNotebookContainer}>
      {/* Notebook Header Bar */}
      <div className={styles.notebookHeaderBanner}>
        <div className={styles.notebookHeaderInfo}>
          <div className={styles.notebookKickerBadge}>
            📖 SỔ TAY HỌC TẬP &amp; CẨM NANG THỰC CHIẾN
          </div>
          <h2 className={styles.notebookDocTitle}>{root?.title ?? "Sổ tay kiến thức Toán học"}</h2>
          <p className={styles.notebookDocSubtitle}>
            Hệ thống hóa toàn diện: Khái niệm &bull; Bảng công thức tính nhanh &bull; Quy trình giải các bước &bull; Ví dụ mẫu có lời giải chi tiết &bull; Hộp cảnh báo bẫy sai lầm.
          </p>
        </div>

        <div className={styles.notebookSearchAndControls}>
          <div className={styles.notebookSearchBox}>
            <span aria-hidden="true">🔍</span>
            <input
              type="search"
              placeholder="Tìm kiếm công thức, dạng bài, ví dụ mẫu, bẫy sai lầm..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className={styles.notebookSearchInput}
            />
            {searchTerm && (
              <button
                type="button"
                onClick={() => setSearchTerm("")}
                className={styles.notebookSearchClear}
                aria-label="Xóa tìm kiếm"
              >
                ✕
              </button>
            )}
          </div>

          <div className={styles.notebookActionButtons}>
            <button type="button" onClick={expandAll} className={styles.notebookToolButton}>
              Mở rộng tất cả
            </button>
            <button type="button" onClick={collapseAll} className={styles.notebookToolButton}>
              Thu gọn
            </button>
            {root && onOpenInMindmap && (
              <button
                type="button"
                onClick={() => onOpenInMindmap(root.id)}
                className={styles.notebookMindmapButton}
              >
                🧠 Xem trên Sơ đồ tư duy
              </button>
            )}
          </div>
        </div>
      </div>

      {/* Quick Section Jump Pills */}
      <nav className={styles.notebookSectionPills} aria-label="Mục lục chuyên đề">
        <button
          type="button"
          className={activeSectionId === "all" ? styles.sectionPillActive : styles.sectionPill}
          onClick={() => setActiveSectionId("all")}
        >
          Tất cả chuyên đề ({parsedSections.length})
        </button>
        {parsedSections.map((s, idx) => (
          <button
            key={s.section.id}
            type="button"
            className={activeSectionId === s.section.id ? styles.sectionPillActive : styles.sectionPill}
            onClick={() => setActiveSectionId(s.section.id)}
          >
            <span>{idx + 1}.</span> {s.section.title.replace(/^\d+[\.\s]*/, "")}
            <small className={styles.pillCount}>({s.topics.length} dạng)</small>
          </button>
        ))}
      </nav>

      {/* Main Content: List of Sections & Topic Cards */}
      <div className={styles.notebookSectionsList}>
        {filteredSections.map((secData, sIdx) => {
          const { section, topics, standaloneItems } = secData;
          return (
            <article key={section.id} id={`sec-${section.id}`} className={styles.notebookSectionCard}>
              {/* Section Banner */}
              <header className={styles.sectionBanner}>
                <div className={styles.sectionBannerTop}>
                  <span className={styles.sectionIndexBadge}>CHUYÊN ĐỀ {sIdx + 1}</span>
                  <div className={styles.sectionMeta}>
                    <span>Trang {section.source_page}</span>
                    {sourceUrl && (
                      <a
                        href={`${sourceUrl}#page=${section.source_page}`}
                        target="_blank"
                        rel="noopener noreferrer"
                        className={styles.sourceDocLink}
                      >
                        📄 Đối chiếu PDF ↗
                      </a>
                    )}
                  </div>
                </div>

                <h3 className={styles.sectionTitle}>{section.title}</h3>

                {section.body && (
                  <div className={styles.sectionSummary}>
                    <MathRenderer content={section.body} />
                  </div>
                )}

                {section.latex && (
                  <div className={styles.sectionFormulaHighlight}>
                    <span className={styles.highlightBadge}>Định lý cốt lõi:</span>
                    <MathRenderer content={`$$${section.latex}$$`} />
                  </div>
                )}
              </header>

              {/* Topics / Dạng bài tập inside this section */}
              <div className={styles.topicCardsGrid}>
                {topics.map((topicData, tIdx) => {
                  const { concept, formulas, methods, examples, notes } = topicData;
                  const isExpanded = expandedTopics[concept.id] !== false; // default expanded
                  const isSelected = selectedNodeId === concept.id;

                  return (
                    <div
                      key={concept.id}
                      id={`topic-${concept.id}`}
                      className={`${styles.topicNoteCard} ${isSelected ? styles.topicNoteCardSelected : ""}`}
                    >
                      {/* Topic Card Header */}
                      <div className={styles.topicCardHeader}>
                        <div
                          className={styles.topicTitleRow}
                          onClick={() => toggleTopic(concept.id)}
                          role="button"
                          tabIndex={0}
                          onKeyDown={(e) => {
                            if (e.key === "Enter" || e.key === " ") toggleTopic(concept.id);
                          }}
                        >
                          <span className={styles.topicChevron} aria-hidden="true">
                            {isExpanded ? "▼" : "▶"}
                          </span>
                          <span className={styles.topicBadge}>Dạng {sIdx + 1}.{tIdx + 1}</span>
                          <h4 className={styles.topicTitle}>{concept.title.replace(/^Dạng\s*[\d\.\:]*\s*/i, "")}</h4>
                        </div>

                        <div className={styles.topicHeaderActions}>
                          {onOpenInMindmap && (
                            <button
                              type="button"
                              className={styles.jumpMindmapBtn}
                              onClick={() => {
                                onSelectNode?.(concept.id);
                                onOpenInMindmap(concept.id);
                              }}
                              title="Xem nhánh này trên Sơ đồ tư duy"
                            >
                              🧠 Sơ đồ
                            </button>
                          )}
                          {isTeacher && onEditNode && (
                            <button
                              type="button"
                              className={styles.topicEditBtn}
                              onClick={() => onEditNode(concept.id)}
                              title="Chỉnh sửa nội dung nhánh này"
                            >
                              ✏️ Sửa
                            </button>
                          )}
                        </div>
                      </div>

                      {/* Topic Card Body (collapsible) */}
                      {isExpanded && (
                        <div className={styles.topicCardContent}>
                          {/* 1. Core Concept / Foundation */}
                          {concept.body && (
                            <div className={styles.noteBlockConcept}>
                              <div className={styles.blockHeading}>
                                <span className={styles.blockIcon}>📌</span>
                                <h5>Bản chất lý thuyết &amp; Định nghĩa trọng tâm</h5>
                              </div>
                              <div className={styles.blockBody}>
                                <MathRenderer content={concept.body} />
                              </div>
                            </div>
                          )}

                          {/* 2. Formulas Sheet (Công thức & Điều kiện) */}
                          {(formulas.length > 0 || concept.latex) && (
                            <div className={styles.noteBlockFormula}>
                              <div className={styles.blockHeading}>
                                <span className={styles.blockIcon}>📐</span>
                                <h5>Bảng công thức tính nhanh &amp; Điều kiện áp dụng</h5>
                              </div>

                              <div className={styles.formulaCardsList}>
                                {formulas.map((fNode) => (
                                  <div key={fNode.id} className={styles.formulaItemCard}>
                                    <div className={styles.formulaItemHeader}>
                                      <strong>{fNode.title.replace(/^📐\s*(?:Công thức:\s*)?/i, "")}</strong>
                                      <small>Trang {fNode.source_page}</small>
                                    </div>
                                    {fNode.latex && (
                                      <div className={styles.katexDisplayWrap}>
                                        <MathRenderer content={`$$${fNode.latex}$$`} />
                                      </div>
                                    )}
                                    {fNode.body && (
                                      <div className={styles.formulaCondition}>
                                        <MathRenderer content={fNode.body} />
                                      </div>
                                    )}
                                  </div>
                                ))}

                                {!formulas.length && concept.latex && (
                                  <div className={styles.formulaItemCard}>
                                    <div className={styles.katexDisplayWrap}>
                                      <MathRenderer content={`$$${concept.latex}$$`} />
                                    </div>
                                  </div>
                                )}
                              </div>
                            </div>
                          )}

                          {/* 3. Method & Step-by-step Procedures (Phương pháp giải) */}
                          {(methods.length > 0 || concept.learning_steps.length > 0) && (
                            <div className={styles.noteBlockMethod}>
                              <div className={styles.blockHeading}>
                                <span className={styles.blockIcon}>📝</span>
                                <h5>Phương pháp giải &amp; Cách trình bày từng bước</h5>
                              </div>

                              {methods.map((mNode) => (
                                <div key={mNode.id} className={styles.methodItemBox}>
                                  <div className={styles.methodItemTitle}>
                                    <strong>{mNode.title.replace(/^📝\s*(?:Phương pháp:\s*)?/i, "")}</strong>
                                  </div>
                                  {mNode.body && (
                                    <div className={styles.methodIntro}>
                                      <MathRenderer content={mNode.body} />
                                    </div>
                                  )}
                                  {mNode.learning_steps.length > 0 && (
                                    <ol className={styles.stepRecipeList}>
                                      {mNode.learning_steps.map((step, sIdx) => (
                                        <li key={sIdx} className={styles.stepRecipeItem}>
                                          <div className={styles.stepRecipeHeader}>
                                            <span className={styles.stepNumBadge}>Bước {sIdx + 1}</span>
                                            <div className={styles.stepInstructionText}>
                                              <MathRenderer content={step.instruction.replace(/^Bước\s*\d+[\:\.]\s*/i, "")} />
                                            </div>
                                          </div>
                                          {step.latex && (
                                            <div className={styles.stepRecipeFormula}>
                                              <MathRenderer content={`$$${step.latex}$$`} />
                                            </div>
                                          )}
                                        </li>
                                      ))}
                                    </ol>
                                  )}
                                </div>
                              ))}

                              {!methods.length && concept.learning_steps.length > 0 && (
                                <ol className={styles.stepRecipeList}>
                                  {concept.learning_steps.map((step, sIdx) => (
                                    <li key={sIdx} className={styles.stepRecipeItem}>
                                      <div className={styles.stepRecipeHeader}>
                                        <span className={styles.stepNumBadge}>Bước {sIdx + 1}</span>
                                        <div className={styles.stepInstructionText}>
                                          <MathRenderer content={step.instruction.replace(/^Bước\s*\d+[\:\.]\s*/i, "")} />
                                        </div>
                                      </div>
                                      {step.latex && (
                                        <div className={styles.stepRecipeFormula}>
                                          <MathRenderer content={`$$${step.latex}$$`} />
                                        </div>
                                      )}
                                    </li>
                                  ))}
                                </ol>
                              )}
                            </div>
                          )}

                          {/* 4. Worked Example Models (Ví dụ minh họa & Lời giải mẫu) */}
                          {examples.length > 0 && (
                            <div className={styles.noteBlockExample}>
                              <div className={styles.blockHeading}>
                                <span className={styles.blockIcon}>💡</span>
                                <h5>Ví dụ minh họa thực chiến &amp; Hướng dẫn giải chi tiết</h5>
                              </div>

                              <div className={styles.exampleCardsList}>
                                {examples.map((exNode) => {
                                  const { question, solution } = parseExampleBody(exNode.body);
                                  const solutionLines = formatSolutionLines(solution);

                                  return (
                                    <div key={exNode.id} className={styles.exampleModelCard}>
                                      <div className={styles.exampleCardHeader}>
                                        <span className={styles.exampleBadge}>VÍ DỤ MẪU</span>
                                        <strong>{exNode.title.replace(/^💡\s*(?:Ví dụ:\s*)?/i, "")}</strong>
                                        <small className={styles.exampleSourcePage}>Trang {exNode.source_page}</small>
                                      </div>

                                      {question && (
                                        <div className={styles.exampleQuestionBox}>
                                          <div className={styles.examTag}>Đề bài:</div>
                                          <div className={styles.examQuestionContent}>
                                            <MathRenderer content={question} />
                                          </div>
                                        </div>
                                      )}

                                      {solution && (
                                        <div className={styles.exampleSolutionBox}>
                                          <div className={styles.solutionTag}>Lời giải chi tiết:</div>
                                          <div className={styles.solutionBody}>
                                            {solutionLines.map((line, lIdx) => (
                                              <div key={lIdx} className={styles.solutionLine}>
                                                <MathRenderer content={line} />
                                              </div>
                                            ))}
                                          </div>
                                        </div>
                                      )}

                                      {exNode.latex && (
                                        <div className={styles.exampleResultBox}>
                                          <span className={styles.resultBadge}>Đáp số then chốt:</span>
                                          <div className={styles.resultMath}>
                                            <MathRenderer content={`$$${exNode.latex}$$`} />
                                          </div>
                                        </div>
                                      )}
                                    </div>
                                  );
                                })}
                              </div>
                            </div>
                          )}

                          {/* 5. Trap Alerts & Pro Tips (Bẫy sai lầm & Lưu ý) */}
                          {notes.length > 0 && (
                            <div className={styles.noteBlockTrap}>
                              <div className={styles.blockHeading}>
                                <span className={styles.blockIcon}>⚠️</span>
                                <h5>Bẫy sai lầm &amp; Lưu ý phòng tránh mất điểm</h5>
                              </div>

                              <div className={styles.trapCardsList}>
                                {notes.map((nNode) => (
                                  <div key={nNode.id} className={styles.trapItemCard}>
                                    <div className={styles.trapCardHeader}>
                                      <strong>{nNode.title.replace(/^⚠️\s*(?:Bẫy sai lầm:\s*)?/i, "")}</strong>
                                    </div>
                                    {nNode.latex && (
                                      <div className={styles.trapFormulaBox}>
                                        <MathRenderer content={`$$${nNode.latex}$$`} />
                                      </div>
                                    )}
                                    <div className={styles.trapExplanation}>
                                      <MathRenderer content={nNode.body} />
                                    </div>
                                  </div>
                                ))}
                              </div>
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  );
                })}

                {/* Standalone items under section */}
                {standaloneItems.length > 0 && (
                  <div className={styles.standaloneSectionItems}>
                    <h5>Ghi chú bổ sung chuyên đề</h5>
                    <div className={styles.standaloneGrid}>
                      {standaloneItems.map((item) => (
                        <div key={item.id} className={styles.standaloneCard}>
                          <strong>{item.title}</strong>
                          {item.latex && <MathRenderer content={`$$${item.latex}$$`} />}
                          {item.body && <MathRenderer content={item.body} />}
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </article>
          );
        })}
      </div>
    </div>
  );
}
