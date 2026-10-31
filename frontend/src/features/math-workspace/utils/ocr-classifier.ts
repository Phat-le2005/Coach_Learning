import type { StepKind } from "@/lib/api/contracts";

export interface StepClassificationInput {
  contentLatex?: string | null;
  explanationText?: string | null;
}

export type StepClassificationResult =
  | {
      status: "DETERMINED";
      predictedType: StepKind;
      ruleId: string;
      matchedEvidence: string;
    }
  | {
      status: "ABSTAIN";
      predictedType: null;
      ruleId: null;
      matchedEvidence: null;
      reason: string;
    };

const MAX_SAFE_INPUT_LENGTH = 4000;

function checkBraceBalance(text: string): boolean {
  let depth = 0;
  for (let i = 0; i < text.length; i++) {
    if (text[i] === "{" || text[i] === "}") {
      let backslashCount = 0;
      let j = i - 1;
      while (j >= 0 && text[j] === "\\") {
        backslashCount++;
        j--;
      }
      if (backslashCount % 2 === 1) {
        // Escaped literal brace (e.g. \{ or \left\{), skip group depth counting
        continue;
      }
      if (text[i] === "{") depth++;
      else if (text[i] === "}") {
        depth--;
        if (depth < 0) return false;
      }
    }
  }
  return depth === 0;
}

/**
 * Pure, deterministic, rule-based mathematical step classifier for Grade 12 math.
 * Suggests a StepKind without altering, repairing, or mutating student input.
 * Supports explicit abstention (ABSTAIN) when evidence is ambiguous, incomplete, or conflicting.
 */
export function classifyMathStep(
  input: StepClassificationInput,
): StepClassificationResult {
  // Input immutability: do not mutate the input object
  const rawLatex = input.contentLatex ?? "";
  const rawExpl = input.explanationText ?? "";

  const latex = rawLatex.trim();
  const expl = rawExpl.trim();
  const combined = `${latex} ${expl}`.trim();

  // 1. Empty or whitespace-only input -> ABSTAIN
  if (!combined) {
    return {
      status: "ABSTAIN",
      predictedType: null,
      ruleId: null,
      matchedEvidence: null,
      reason: "Đầu vào trống hoặc chỉ chứa khoảng trắng.",
    };
  }

  // 2. Input length safety check (guard against regex catastrophic backtracking)
  if (combined.length > MAX_SAFE_INPUT_LENGTH) {
    return {
      status: "ABSTAIN",
      predictedType: null,
      ruleId: null,
      matchedEvidence: null,
      reason: "Độ dài văn bản vượt quá giới hạn an toàn để phân loại tự động.",
    };
  }

  // 3. Malformed syntax checks (unbalanced LaTeX braces or dangling binary operators)
  if (latex && !checkBraceBalance(latex)) {
    return {
      status: "ABSTAIN",
      predictedType: null,
      ruleId: null,
      matchedEvidence: null,
      reason: "Công thức LaTeX chứa dấu ngoặc nhọn không cân bằng.",
    };
  }
  if (latex && /[+\-*/^=]\s*$/.test(latex)) {
    return {
      status: "ABSTAIN",
      predictedType: null,
      ruleId: null,
      matchedEvidence: null,
      reason: "Công thức kết thúc bằng toán tử chưa hoàn chỉnh.",
    };
  }

  // 4. Conflicting multi-step intent check:
  // e.g., "Tính đạo hàm rồi xét dấu" or "Tìm nghiệm và lập bảng biến thiên"
  const multiStepKeywords = [
    /(?:tính đạo hàm|đạo hàm).*?(?:rồi|và|sau đó).*?(?:xét dấu|bảng biến thiên|tìm nghiệm)/i,
    /(?:tìm nghiệm|giải phương trình).*?(?:rồi|và|sau đó).*?(?:lập bảng|kết luận)/i,
    /(?:xét dấu).*?(?:rồi|và|sau đó).*?(?:kết luận)/i,
  ];
  for (const pattern of multiStepKeywords) {
    const match = expl.match(pattern);
    if (match) {
      return {
        status: "ABSTAIN",
        predictedType: null,
        ruleId: null,
        matchedEvidence: null,
        reason: `Mô tả chứa nhiều bước giải kết hợp ('${match[0]}'), không thể gán nhãn bước đơn.`,
      };
    }
  }

  // 5. Conclusion rule (Monotonicity, Extrema, Asymptotes)
  // Highest priority for explicit mathematical conclusions
  const conclusionRegex =
    /(?:đồng biến|nghịch biến|đạt cực đại|đạt cực tiểu|đạt cực trị|có tiệm cận|vậy hàm số|do đó hàm số|kết luận:?|y_(?:CĐ|CT|cđ|ct)\s*=)/i;
  const matchConclusion = combined.match(conclusionRegex);
  if (matchConclusion) {
    return {
      status: "DETERMINED",
      predictedType: "CONCLUSION",
      ruleId: "RULE_CONCLUSION_MONOTONICITY",
      matchedEvidence: matchConclusion[0],
    };
  }

  // 6. Variation Table rule
  // Explicit mention of variation table keywords (using Unicode word boundaries)
  const varTableRegex =
    /(?:^|[^\p{L}\p{N}])(?:bảng biến thiên|BBT|lập BBT)(?:$|[^\p{L}\p{N}])/iu;
  const matchVarTable = combined.match(varTableRegex);
  if (matchVarTable) {
    return {
      status: "DETERMINED",
      predictedType: "VARIATION_TABLE",
      ruleId: "RULE_VARIATION_TABLE",
      matchedEvidence: matchVarTable[0].trim(),
    };
  }

  // 7. Sign Table rule
  // Explicit mention of sign table keywords (using Unicode word boundaries)
  const signTableRegex =
    /(?:^|[^\p{L}\p{N}])(?:bảng xét dấu|BXĐ|xét dấu (?:y'|f'\(x\)))(?:$|[^\p{L}\p{N}])/iu;
  const matchSignTable = combined.match(signTableRegex);
  if (matchSignTable) {
    return {
      status: "DETERMINED",
      predictedType: "SIGN_TABLE",
      ruleId: "RULE_SIGN_TABLE",
      matchedEvidence: matchSignTable[0].trim(),
    };
  }

  // 8. Assumption / Domain rule
  // Requires explicit domain/condition context keywords.
  // Isolated inequalities like "x > 0" without domain context are rejected from ASSUMPTION.
  const assumptionRegex =
    /(?:^|[^\p{L}\p{N}])(?:TXĐ|Tập xác định|ĐKXĐ|Điều kiện xác định|D\s*=\s*(?:\\mathbb\{R\}|R|\\R|\[|\()|ĐK\s*:|Điều kiện\s*:)/iu;
  const matchAssumption = combined.match(assumptionRegex);
  if (matchAssumption) {
    return {
      status: "DETERMINED",
      predictedType: "ASSUMPTION",
      ruleId: "RULE_ASSUMPTION_DOMAIN",
      matchedEvidence: matchAssumption[0].trim(),
    };
  }

  // 9. Root Finding rule
  // Evidence of solving equations for roots / critical points
  // Sub-case A: Setting derivative to zero: y' = 0 or f'(x) = 0
  const derivZeroRegex = /(?:y'|f'\(x\)|g'\(x\))\s*=\s*0(?!\d)/i;
  const matchDerivZero = combined.match(derivZeroRegex);
  if (matchDerivZero) {
    return {
      status: "DETERMINED",
      predictedType: "ROOT_FINDING",
      ruleId: "RULE_ROOT_FINDING_DERIVATIVE_ZERO",
      matchedEvidence: matchDerivZero[0],
    };
  }

  // Sub-case B: Equivalence chain solving for roots: <=> x = ... or <=> [x = ...
  const solveChainRegex =
    /(?:\\Leftrightarrow\s*x\s*=|\\Leftrightarrow\s*\[\s*x|\\Leftrightarrow\s*\\left\[\s*\\begin\{(?:cases|array)\}|x_1\s*=|x_2\s*=|x\s*=\s*[-0-9\.\/]+\s*(?:\\lor|,|\bhoặc\b)\s*x\s*=|x\s*\\in\s*\\\{[-0-9\.\/,\s]+\\\})/i;
  const matchSolveChain = combined.match(solveChainRegex);
  if (matchSolveChain) {
    return {
      status: "DETERMINED",
      predictedType: "ROOT_FINDING",
      ruleId: "RULE_ROOT_FINDING_SOLVE_CHAIN",
      matchedEvidence: matchSolveChain[0],
    };
  }

  // Sub-case C: Explicit root finding text context: "Giải phương trình", "Cho y' = 0", "Nghiệm của"
  const rootTextRegex =
    /(?:^|[^\p{L}\p{N}])(?:giải phương trình|tìm nghiệm|cho (?:y'|f'\(x\))\s*=\s*0|phương trình có nghiệm|nghiệm của phương trình)(?:$|[^\p{L}\p{N}])/iu;
  const matchRootText = expl.match(rootTextRegex);
  if (matchRootText) {
    return {
      status: "DETERMINED",
      predictedType: "ROOT_FINDING",
      ruleId: "RULE_ROOT_FINDING_TEXT_CONTEXT",
      matchedEvidence: matchRootText[0].trim(),
    };
  }

  // Sub-case D: Full equation equating polynomial to zero: e.g. "3x^2 - 6x = 0"
  // (Excludes isolated single variables like "x = 0" without context)
  if (latex && /^[-0-9a-zA-Z\s\+\-\*\/\^\(\)\{\}\\]+=\s*0$/.test(latex)) {
    // Ensure LHS has degree >= 1 (contains variable x and operation)
    if (/[xX]\s*[\^2-9\+\-\*]/.test(latex)) {
      return {
        status: "DETERMINED",
        predictedType: "ROOT_FINDING",
        ruleId: "RULE_ROOT_FINDING_POLYNOMIAL_ZERO",
        matchedEvidence: "= 0",
      };
    }
  }

  // 10. Derivative Calculation rule
  // Must compute/evaluate a derivative formula: y' = 3x^2 - 6x or f'(x) = ...
  // Rejects equations where RHS is 0 (already caught by ROOT_FINDING)
  const derivativeRegex = /(?:y'|f'\(x\)|g'\(x\)|\bdy\/dx|\\frac\{dy\}\{dx\})\s*=\s*([^=;]+)/i;
  const matchDerivative = combined.match(derivativeRegex);
  if (matchDerivative) {
    const rhs = matchDerivative[1].trim();
    if (rhs && rhs !== "0") {
      return {
        status: "DETERMINED",
        predictedType: "DERIVATIVE_CALCULATION",
        ruleId: "RULE_DERIVATIVE_CALCULATION",
        matchedEvidence: matchDerivative[0].trim(),
      };
    }
  }

  // 11. Verbal Explanation rule
  // Explicit verbal reasoning words without specific mathematical formulas (Unicode word boundaries)
  const explanationRegex =
    /(?:^|[^\p{L}\p{N}])(?:vì|do đó|ta có|áp dụng|theo bài ra|nhận xét|chú ý|mặt khác|tương tự)(?:$|[^\p{L}\p{N}])/iu;
  const matchExplanation = expl.match(explanationRegex);
  if (matchExplanation) {
    return {
      status: "DETERMINED",
      predictedType: "EXPLANATION",
      ruleId: "RULE_EXPLANATION_VERBAL_PROSE",
      matchedEvidence: matchExplanation[0].trim(),
    };
  }

  // 12. Isolated variable assignment without context: e.g. "x = 2", "x > 0", "y = 5"
  // These are ambiguous without context (could be root, asymptote, substitution, or interval)
  if (latex && /^[xyzXYZ]\s*(?:=|>|<|\\ge|\\le)\s*[-0-9\.\/]+$/.test(latex) && !expl) {
    return {
      status: "ABSTAIN",
      predictedType: null,
      ruleId: null,
      matchedEvidence: null,
      reason: `Biểu thức gán/bất đẳng thức đơn độc ('${latex}') thiếu ngữ cảnh để phân loại chắc chắn.`,
    };
  }

  // 13. Default: Ambiguous or unclassified input -> ABSTAIN
  return {
    status: "ABSTAIN",
    predictedType: null,
    ruleId: null,
    matchedEvidence: null,
    reason: "Không có đủ bằng chứng cú pháp hoặc từ khóa rõ ràng để phân loại bước giải.",
  };
}
