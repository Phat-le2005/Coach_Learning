import type { StepKind } from "@/lib/api/contracts";
import { STEP_KINDS } from "@/lib/api/contracts";

export { STEP_KINDS };
export type { StepKind };

export type ArtifactKind =
  | "SIGN_TABLE"
  | "VARIATION_TABLE"
  | "INTERVAL_SET"
  | "SYSTEM_OF_EQUATIONS";

export interface SignTablePayload {
  critical_points: (number | string)[];
  signs: string[];
}

export interface MathArtifact {
  artifact_type: ArtifactKind;
  payload: SignTablePayload | Record<string, unknown>;
}

export interface SolutionStepItem {
  id: string;
  step_index: number;
  step_type: StepKind;
  content_latex: string | null;
  explanation_text: string | null;
  step_revision_number: number;
  artifact?: MathArtifact | null;
  is_deleted?: boolean;
}

export interface StepRevisionItem {
  id: string;
  step_revision_number: number;
  step_index_at_revision: number;
  content_latex: string | null;
  explanation_text: string | null;
  artifact?: MathArtifact | null;
  change_reason: string;
  created_at: string;
}

export interface SolutionSolverAttempt {
  id: string;
  status: string;
  context_type: string;
  source_kind: string;
  mode: string;
  attempt_revision_number: number;
  question_id?: string | null;
  steps: SolutionStepItem[];
  started_at: string;
  updated_at: string;
  submitted_at?: string | null;
  total_score?: number | null;
  is_correct?: boolean | null;
}

export const STEP_KIND_DISPLAY_NAMES: Record<StepKind, string> = {
  ASSUMPTION: "1. Giả thiết & TXĐ (Assumption)",
  DERIVATIVE_CALCULATION: "2. Tính đạo hàm (Derivative Calculation)",
  ROOT_FINDING: "3. Tìm nghiệm đạo hàm (Root Finding)",
  SIGN_TABLE: "4. Bảng xét dấu (Sign Table)",
  VARIATION_TABLE: "5. Bảng biến thiên (Variation Table)",
  CONCLUSION: "6. Kết luận khoảng đơn điệu (Conclusion)",
  EXPLANATION: "Diễn giải / Lập luận (Explanation)",
  CUSTOM: "Bước giải tự do (Custom Step)",
};
