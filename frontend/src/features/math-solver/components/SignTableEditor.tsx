"use client";

import React, { useState } from "react";
import { Plus, Trash2, ArrowLeftRight } from "lucide-react";
import type { SignTablePayload } from "../types";
import { cycleSign, invertSigns, addCriticalPoint, removeCriticalPoint } from "../utils";
import styles from "./SignTableEditor.module.css";

interface SignTableEditorProps {
  value: SignTablePayload;
  onChange: (newValue: SignTablePayload) => void;
  isReadOnly?: boolean;
}

export function SignTableEditor({
  value,
  onChange,
  isReadOnly = false,
}: SignTableEditorProps) {
  const [newPointInput, setNewPointInput] = useState("");

  const criticalPoints = value.critical_points ?? [];
  const signs = value.signs ?? (criticalPoints.length > 0 ? Array(criticalPoints.length + 1).fill("+") : ["+"]);

  const handleCycleSign = (index: number) => {
    if (isReadOnly) return;
    const currentSign = signs[index] || "+";
    const nextSign = cycleSign(currentSign);
    const updatedSigns = [...signs];
    updatedSigns[index] = nextSign;
    onChange({
      critical_points: criticalPoints,
      signs: updatedSigns,
    });
  };

  const handleAddPoint = () => {
    if (isReadOnly || !newPointInput.trim()) return;
    const nextPayload = addCriticalPoint(value, newPointInput);
    onChange(nextPayload);
    setNewPointInput("");
  };

  const handleRemovePoint = (idx: number) => {
    if (isReadOnly) return;
    const nextPayload = removeCriticalPoint(value, idx);
    onChange(nextPayload);
  };

  const handlePointChange = (idx: number, newVal: string) => {
    if (isReadOnly) return;
    const num = Number(newVal);
    const val = isNaN(num) || newVal.trim() === "" ? newVal : num;
    const updatedPoints = [...criticalPoints];
    updatedPoints[idx] = val;
    onChange({
      critical_points: updatedPoints,
      signs: [...signs],
    });
  };

  const handleInvertAllSigns = () => {
    if (isReadOnly) return;
    const updated = invertSigns(signs);
    onChange({
      critical_points: criticalPoints,
      signs: updated,
    });
  };

  return (
    <div className={styles.container}>
      <div className={styles.headerRow}>
        <div className={styles.titleGroup}>
          <span className={styles.title}>Bảng xét dấu đạo hàm y&apos;</span>
          <span className={styles.subtitle}>
            {isReadOnly ? "(Chế độ xem)" : "Click vào ô dấu (+, -) để đổi dấu"}
          </span>
        </div>

        {!isReadOnly && (
          <div className={styles.controlGroup}>
            <button
              type="button"
              className={styles.toolBtn}
              onClick={handleInvertAllSigns}
              title="Đảo ngược tất cả các dấu (+ thành - và ngược lại)"
            >
              <ArrowLeftRight size={14} />
              Đảo dấu
            </button>
          </div>
        )}
      </div>

      {/* Horizontal scroll container for responsiveness on 360px & 390px */}
      <div className={styles.tableScrollWrapper}>
        <table className={styles.signTable}>
          <thead>
            {/* Row 1: x coordinates */}
            <tr>
              <th className={styles.headerLabelCell}>x</th>
              <td className={styles.infinityCell}>-∞</td>
              {criticalPoints.map((point, idx) => (
                <React.Fragment key={`pt-${idx}`}>
                  <td className={styles.intervalSpaceCell} aria-hidden="true" />
                  <td className={styles.pointCell}>
                    {isReadOnly ? (
                      <span className={styles.pointDisplay}>{String(point)}</span>
                    ) : (
                      <div className={styles.pointInputWrap}>
                        <input
                          type="text"
                          className={styles.pointInput}
                          value={String(point)}
                          onChange={(e) => handlePointChange(idx, e.target.value)}
                          aria-label={`Điểm dừng thứ ${idx + 1}`}
                        />
                        <button
                          type="button"
                          className={styles.removePointBtn}
                          onClick={() => handleRemovePoint(idx)}
                          title="Xóa điểm này"
                          aria-label={`Xóa điểm ${point}`}
                        >
                          <Trash2 size={12} />
                        </button>
                      </div>
                    )}
                  </td>
                </React.Fragment>
              ))}
              <td className={styles.intervalSpaceCell} aria-hidden="true" />
              <td className={styles.infinityCell}>+∞</td>
            </tr>
          </thead>
          <tbody>
            {/* Row 2: y' values & signs */}
            <tr>
              <th className={styles.headerLabelCell}>y&apos;</th>
              <td className={styles.blankBoundCell} />
              {signs.map((sign, idx) => (
                <React.Fragment key={`sign-${idx}`}>
                  <td className={styles.signCell}>
                    <button
                      type="button"
                      className={`${styles.signBtn} ${
                        sign === "+"
                          ? styles.signPositive
                          : sign === "-"
                          ? styles.signNegative
                          : styles.signNeutral
                      }`}
                      onClick={() => handleCycleSign(idx)}
                      disabled={isReadOnly}
                      title={isReadOnly ? undefined : "Click để đổi dấu (+ / - / 0 / ||)"}
                    >
                      {sign}
                    </button>
                  </td>
                  {idx < criticalPoints.length && (
                    <td className={styles.zeroCell}>0</td>
                  )}
                </React.Fragment>
              ))}
              <td className={styles.blankBoundCell} />
            </tr>
          </tbody>
        </table>
      </div>

      {/* Add new point bar */}
      {!isReadOnly && (
        <div className={styles.addPointBar}>
          <input
            type="text"
            className={styles.addInput}
            value={newPointInput}
            onChange={(e) => setNewPointInput(e.target.value)}
            placeholder="Nhập giá trị x (ví dụ: -1, 3)..."
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                handleAddPoint();
              }
            }}
          />
          <button
            type="button"
            className={styles.addBtn}
            onClick={handleAddPoint}
            disabled={!newPointInput.trim()}
          >
            <Plus size={16} />
            Thêm điểm x
          </button>
        </div>
      )}
    </div>
  );
}
