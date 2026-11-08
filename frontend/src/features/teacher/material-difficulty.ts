import { oneOf } from "../../lib/api/validation";

export const MATERIAL_DIFFICULTY_LEVELS = ["NHAN_BIET", "THONG_HIEU", "VAN_DUNG", "VAN_DUNG_CAO"] as const;
export type MaterialDifficultyLevel = (typeof MATERIAL_DIFFICULTY_LEVELS)[number];

export const MATERIAL_DIFFICULTY_LABELS: Record<MaterialDifficultyLevel, string> = {
  NHAN_BIET: "Nhận biết", THONG_HIEU: "Thông hiểu", VAN_DUNG: "Vận dụng", VAN_DUNG_CAO: "Vận dụng cao",
};

export function parseMaterialDifficulty(value: unknown, path: string): MaterialDifficultyLevel | null {
  return value == null ? null : oneOf(value, path, MATERIAL_DIFFICULTY_LEVELS);
}
