"use client";

import React, { useState, useMemo } from "react";
import {
  BookOpen,
  PenTool,
  UploadCloud,
  Search,
  Filter,
  Download,
  Share2,
  FileText,
  CheckCircle,
  FileCheck,
} from "lucide-react";
import type { TeacherMaterial, MaterialCategory } from "../types";
import { UploadMaterialModal } from "./UploadMaterialModal";
import styles from "../TeacherDashboard.module.css";

interface MaterialsTabProps {
  materials: TeacherMaterial[];
  onAddMaterial: (material: TeacherMaterial) => void;
}

export function MaterialsTab({ materials, onAddMaterial }: MaterialsTabProps) {
  const [activeCategory, setActiveCategory] = useState<MaterialCategory>("theory");
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedTopic, setSelectedTopic] = useState<string>("ALL");
  const [isUploadModalOpen, setIsUploadModalOpen] = useState(false);

  const topicsList = useMemo(() => {
    const set = new Set<string>();
    for (const m of materials) set.add(m.topic);
    return ["ALL", ...Array.from(set)];
  }, [materials]);

  const filteredMaterials = useMemo(() => {
    return materials.filter((m) => {
      if (m.category !== activeCategory) return false;
      if (selectedTopic !== "ALL" && m.topic !== selectedTopic) return false;
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase();
        return (
          m.title.toLowerCase().includes(q) ||
          m.description.toLowerCase().includes(q) ||
          m.topic.toLowerCase().includes(q)
        );
      }
      return true;
    });
  }, [materials, activeCategory, selectedTopic, searchQuery]);

  const theoryCount = materials.filter((m) => m.category === "theory").length;
  const practiceCount = materials.filter((m) => m.category === "practice").length;

  return (
    <div>
      {/* Top action row */}
      <div className={styles.viewHeader}>
        <div className={styles.viewTitleGroup}>
          <h2 className={styles.viewTitle}>Kho tài liệu giảng dạy</h2>
          <span className={styles.viewSubtitle}>
            Quản lý giáo án, chuyên đề lý thuyết và phiếu bài tập thực hành Toán 12
          </span>
        </div>

        <div className={styles.viewActions}>
          {/* Switch Category */}
          <div className={styles.categorySwitch}>
            <button
              type="button"
              className={`${styles.categoryBtn} ${activeCategory === "theory" ? styles.categoryBtnActive : ""}`}
              onClick={() => setActiveCategory("theory")}
            >
              📖 Lý thuyết ({theoryCount})
            </button>
            <button
              type="button"
              className={`${styles.categoryBtn} ${activeCategory === "practice" ? styles.categoryBtnActive : ""}`}
              onClick={() => setActiveCategory("practice")}
            >
              ✍️ Thực hành & Bài tập ({practiceCount})
            </button>
          </div>

          <button
            type="button"
            className={styles.btnPrimary}
            onClick={() => setIsUploadModalOpen(true)}
          >
            <UploadCloud size={16} />
            Tải lên tài liệu
          </button>
        </div>
      </div>

      {/* Filter and Search Bar */}
      <div style={{ display: "flex", gap: "0.75rem", marginBottom: "1.25rem", flexWrap: "wrap" }}>
        <div style={{ flex: 1, minWidth: "240px", position: "relative" }}>
          <input
            type="text"
            className={styles.formInput}
            style={{ paddingLeft: "2.25rem" }}
            placeholder={`Tìm kiếm trong kho ${activeCategory === "theory" ? "lý thuyết" : "thực hành"}...`}
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
          <Search
            size={16}
            style={{ position: "absolute", left: "0.75rem", top: "50%", transform: "translateY(-50%)", color: "var(--text-tertiary)" }}
          />
        </div>

        <div style={{ minWidth: "200px" }}>
          <select
            className={styles.formSelect}
            value={selectedTopic}
            onChange={(e) => setSelectedTopic(e.target.value)}
          >
            <option value="ALL">Tất cả chủ đề</option>
            {topicsList.filter(t => t !== "ALL").map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Material Grid */}
      {filteredMaterials.length === 0 ? (
        <div style={{ textAlign: "center", padding: "3rem", background: "var(--surface-elevated)", borderRadius: "14px", border: "1px dashed var(--border-soft)" }}>
          <FileText size={36} style={{ color: "var(--text-tertiary)", marginBottom: "0.5rem" }} />
          <h4 style={{ margin: "0 0 0.25rem", color: "var(--text-primary)" }}>Chưa có tài liệu phù hợp</h4>
          <p style={{ margin: 0, fontSize: "0.85rem", color: "var(--text-secondary)" }}>
            Thử thay đổi từ khóa tìm kiếm hoặc bấm &quot;Tải lên tài liệu&quot; để thêm tài liệu mới.
          </p>
        </div>
      ) : (
        <div className={styles.materialGrid}>
          {filteredMaterials.map((item) => (
            <div key={item.id} className={styles.materialCard}>
              <div>
                <div className={styles.materialTop}>
                  <span
                    className={`${styles.materialFormatBadge} ${
                      item.format === "pdf"
                        ? styles.badgePdf
                        : item.format === "docx"
                        ? styles.badgeDocx
                        : styles.badgeExam
                    }`}
                  >
                    {item.format}
                  </span>
                  <span className={styles.materialTopic}>{item.topic}</span>
                </div>

                <h3 className={styles.materialTitle}>{item.title}</h3>
                <p className={styles.materialDesc}>{item.description}</p>
              </div>

              <div className={styles.materialFooter}>
                <div className={styles.materialMeta}>
                  <span>{item.fileSize}</span>
                  <span>•</span>
                  <span>{item.downloadsCount} lượt tải</span>
                </div>

                <div className={styles.materialActions}>
                  <button
                    type="button"
                    className={styles.cardActionBtn}
                    onClick={() => alert(`Đã tạo liên kết chia sẻ cho "${item.title}".`)}
                    title="Gán cho lớp học"
                  >
                    <Share2 size={13} style={{ marginRight: "3px", verticalAlign: "middle" }} />
                    Gán lớp
                  </button>
                  <button
                    type="button"
                    className={styles.cardActionBtn}
                    onClick={() => alert(`Bắt đầu tải về "${item.title}".`)}
                    title="Tải tài liệu về máy"
                  >
                    <Download size={13} style={{ marginRight: "3px", verticalAlign: "middle" }} />
                    Tải về
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Upload modal */}
      <UploadMaterialModal
        isOpen={isUploadModalOpen}
        onClose={() => setIsUploadModalOpen(false)}
        onAddMaterial={onAddMaterial}
      />
    </div>
  );
}
