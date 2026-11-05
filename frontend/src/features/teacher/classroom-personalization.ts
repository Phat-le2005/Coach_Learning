import { avatarSeed, assignmentProgress } from "./classroom-model";
import type { ClassroomStudentInfo } from "./classroom-types";

export const BAG_COLORS = {
  mint: { label: "Xanh mint", hex: "#8bc9ad", color: 0x8bc9ad },
  lavender: { label: "Tím lavender", hex: "#baa9df", color: 0xbaa9df },
  peach: { label: "Cam đào", hex: "#efb99b", color: 0xefb99b },
  sky: { label: "Xanh trời", hex: "#9fc8df", color: 0x9fc8df },
} as const;
export type BagColor = keyof typeof BAG_COLORS;
export type DeskDecoration = "plant" | "star" | "none";
export interface DeskStyle { bagColor: BagColor; decoration: DeskDecoration; glasses: boolean }
export type ClassroomStyles = Record<string, DeskStyle>;

export function defaultDeskStyle(studentId: string): DeskStyle {
  const seed = avatarSeed(studentId);
  return { bagColor: (Object.keys(BAG_COLORS) as BagColor[])[seed % 4], decoration: seed % 3 === 0 ? "star" : "plant", glasses: seed % 4 === 0 };
}

export function classroomStyleKey(classroomId: string): string { return `edums:cozy-campus:v1:${classroomId}`; }

export function parseClassroomStyles(raw: string | null, studentIds: readonly string[]): ClassroomStyles {
  const result: ClassroomStyles = Object.create(null);
  if (!raw || raw.length > 100_000) return result;
  try {
    const source: unknown = JSON.parse(raw);
    if (!source || typeof source !== "object" || Array.isArray(source)) return result;
    const stored = source as Record<string, unknown>;
    if (stored.version !== 1 || !stored.students || typeof stored.students !== "object" || Array.isArray(stored.students)) return result;
    for (const id of studentIds) {
      if (["__proto__", "constructor", "prototype"].includes(id)) continue;
      const entry = (stored.students as Record<string, unknown>)[id];
      if (!entry || typeof entry !== "object" || Array.isArray(entry)) continue;
      const value = entry as Record<string, unknown>;
      if (typeof value.bagColor !== "string" || !Object.hasOwn(BAG_COLORS, value.bagColor) || !["plant", "star", "none"].includes(String(value.decoration)) || typeof value.glasses !== "boolean") continue;
      result[id] = { bagColor: value.bagColor as BagColor, decoration: value.decoration as DeskDecoration, glasses: value.glasses };
    }
  } catch { /* Local preferences are optional; invalid storage never blocks a lesson. */ }
  return result;
}

export function serializeClassroomStyles(styles: ClassroomStyles): string { return JSON.stringify({ version: 1, students: styles }); }

export function classMomentSummary(students: readonly ClassroomStudentInfo[], classroomName: string, showClassName: boolean, isDemo = true) {
  const total = students.length;
  const completed = students.filter((student) => student.totalAssignments !== null && student.totalAssignments > 0 && assignmentProgress(student) === 100).length;
  const hasProgress = total > 0 && students.every((student) => assignmentProgress(student) !== null);
  return {
    hasProgress,
    title: "Lớp mình hôm nay",
    classroom: showClassName ? classroomName : "Cùng nhau, mình tiến bộ",
    total,
    completed,
    isDemo,
    goalReached: hasProgress && completed === total,
    caption: total > 0 && completed === total ? "Một tràng vỗ tay cho lớp mình!" : "Mỗi ngày một chút. Cùng nhau đi xa hơn.",
  };
}

export function celebrationProgress(start: number, now: number): number {
  if (start < 0 || now < start || now - start >= 2000) return 0;
  return Math.sin(Math.PI * (now - start) / 2000);
}
