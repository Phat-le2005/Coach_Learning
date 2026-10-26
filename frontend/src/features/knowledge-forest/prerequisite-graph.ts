/**
 * Verified pedagogical prerequisite graph between Math 12 Problem Types.
 * Derived strictly from the official GDPT 2018 concept relations and problem type mappings.
 * Does not invent speculative edges.
 */

export interface PrerequisiteEdge {
  sourceCode: string; // The prerequisite skill (must study first)
  targetCode: string; // The dependent skill (unlocked after prerequisite)
  weight?: number;
}

// Canonical prerequisite mappings derived from curriculum concept relations:
// (ANTIDERIVATIVE -> DEFINITE_INTEGRAL, DERIVATIVE -> MONOTONICITY -> EXTREMA,
//  VECTOR -> GEOMETRY_3D -> OXYZ, CONDITIONAL_PROBABILITY -> TOTAL_PROBABILITY, etc.)
export const VERIFIED_PREREQUISITE_EDGES: readonly PrerequisiteEdge[] = [
  // --- Giải tích: Đạo hàm & Khảo sát hàm số ---
  { sourceCode: "MONOTONICITY_FROM_DERIVATIVE_SIGN", targetCode: "MONOTONICITY_FROM_VARIATION_TABLE" },
  { sourceCode: "MONOTONICITY_FROM_VARIATION_TABLE", targetCode: "MONOTONICITY_FROM_GRAPH" },
  { sourceCode: "MONOTONICITY_FROM_VARIATION_TABLE", targetCode: "MONOTONICITY_FROM_EXPRESSION" },
  { sourceCode: "MONOTONICITY_FROM_EXPRESSION", targetCode: "PARAMETER_MONOTONICITY" },
  { sourceCode: "MONOTONICITY_FROM_EXPRESSION", targetCode: "FIND_FUNCTION_EXTREMA" },
  { sourceCode: "EXTREMA_FROM_DERIVATIVE_SIGN", targetCode: "EXTREMA_FROM_VARIATION_TABLE" },
  { sourceCode: "EXTREMA_FROM_VARIATION_TABLE", targetCode: "FIND_FUNCTION_EXTREMA" },
  { sourceCode: "FIND_FUNCTION_EXTREMA", targetCode: "PARAMETER_EXTREMA_COUNT" },
  { sourceCode: "FIND_FUNCTION_EXTREMA", targetCode: "GLOBAL_EXTREMA_INTERVAL" },
  { sourceCode: "GLOBAL_EXTREMA_INTERVAL", targetCode: "GLOBAL_EXTREMA_OPTIMIZATION_MODEL" },
  { sourceCode: "ASYMPTOTE_FROM_LIMITS", targetCode: "ASYMPTOTE_FROM_EXPRESSION" },
  { sourceCode: "ASYMPTOTE_FROM_EXPRESSION", targetCode: "ASYMPTOTE_FROM_VARIATION_TABLE" },
  { sourceCode: "ASYMPTOTE_FROM_VARIATION_TABLE", targetCode: "GRAPH_IDENTIFICATION_FROM_FEATURES" },
  { sourceCode: "MONOTONICITY_FROM_GRAPH", targetCode: "GRAPH_IDENTIFICATION_FROM_FEATURES" },
  { sourceCode: "FIND_FUNCTION_EXTREMA", targetCode: "GRAPH_IDENTIFICATION_FROM_FEATURES" },
  { sourceCode: "GRAPH_IDENTIFICATION_FROM_FEATURES", targetCode: "COMPLETE_FUNCTION_ANALYSIS_CUBIC" },
  { sourceCode: "GRAPH_IDENTIFICATION_FROM_FEATURES", targetCode: "COMPLETE_FUNCTION_ANALYSIS_FRACTIONAL" },
  { sourceCode: "COMPLETE_FUNCTION_ANALYSIS_CUBIC", targetCode: "EXTREMA_GEOMETRIC_APPLICATION" },

  // --- Nguyên hàm & Tích phân ---
  { sourceCode: "ANTIDERIVATIVE_TABLE_APPLICATION", targetCode: "ANTIDERIVATIVE_BY_SUBSTITUTION" },
  { sourceCode: "ANTIDERIVATIVE_TABLE_APPLICATION", targetCode: "ANTIDERIVATIVE_BY_PARTS" },
  { sourceCode: "ANTIDERIVATIVE_TABLE_APPLICATION", targetCode: "DEFINITE_INTEGRAL_DEFINITION_APPLICATION" },
  { sourceCode: "DEFINITE_INTEGRAL_DEFINITION_APPLICATION", targetCode: "DEFINITE_INTEGRAL_BY_SUBSTITUTION" },
  { sourceCode: "DEFINITE_INTEGRAL_DEFINITION_APPLICATION", targetCode: "DEFINITE_INTEGRAL_BY_PARTS" },
  { sourceCode: "DEFINITE_INTEGRAL_DEFINITION_APPLICATION", targetCode: "AREA_BY_INTEGRAL" },
  { sourceCode: "AREA_BY_INTEGRAL", targetCode: "VOLUME_BY_INTEGRAL" },
  { sourceCode: "VOLUME_BY_INTEGRAL", targetCode: "PHYSICS_GEOMETRIC_APPLICATION_INTEGRAL" },

  // --- Vectơ & Hệ tọa độ trong không gian ---
  { sourceCode: "VECTOR_ADDITION_SUBTRACTION_3D", targetCode: "SCALAR_VECTOR_MULTIPLICATION_3D" },
  { sourceCode: "SCALAR_VECTOR_MULTIPLICATION_3D", targetCode: "VECTOR_DOT_PRODUCT_3D" },
  { sourceCode: "VECTOR_DOT_PRODUCT_3D", targetCode: "VECTOR_ANGLE_CALCULATION_3D" },
  { sourceCode: "VECTOR_ADDITION_SUBTRACTION_3D", targetCode: "SPACE_COORDINATES_POINT" },
  { sourceCode: "SPACE_COORDINATES_POINT", targetCode: "SPACE_COORDINATES_VECTOR" },
  { sourceCode: "SPACE_COORDINATES_VECTOR", targetCode: "VECTOR_OPERATIONS_BY_COORDINATES" },
  { sourceCode: "VECTOR_OPERATIONS_BY_COORDINATES", targetCode: "VECTOR_COLLINEARITY_COORDINATES" },
  { sourceCode: "VECTOR_OPERATIONS_BY_COORDINATES", targetCode: "DOT_PRODUCT_BY_COORDINATES" },
  { sourceCode: "DOT_PRODUCT_BY_COORDINATES", targetCode: "VECTOR_ORTHOGONALITY_COORDINATES" },
  { sourceCode: "VECTOR_ORTHOGONALITY_COORDINATES", targetCode: "CROSS_PRODUCT_COORDINATES" },

  // --- Phương pháp tọa độ Oxyz ---
  { sourceCode: "SPACE_COORDINATES_POINT", targetCode: "SPHERE_EQUATION_RECOGNITION" },
  { sourceCode: "SPHERE_EQUATION_RECOGNITION", targetCode: "SPHERE_EQUATION_WRITING" },
  { sourceCode: "CROSS_PRODUCT_COORDINATES", targetCode: "PLANE_NORMAL_VECTOR_IDENTIFICATION" },
  { sourceCode: "PLANE_NORMAL_VECTOR_IDENTIFICATION", targetCode: "PLANE_EQUATION_WRITING" },
  { sourceCode: "PLANE_EQUATION_WRITING", targetCode: "POINT_TO_PLANE_DISTANCE" },
  { sourceCode: "PLANE_NORMAL_VECTOR_IDENTIFICATION", targetCode: "LINE_DIRECTION_VECTOR_IDENTIFICATION" },
  { sourceCode: "LINE_DIRECTION_VECTOR_IDENTIFICATION", targetCode: "LINE_EQUATION_WRITING" },
  { sourceCode: "LINE_EQUATION_WRITING", targetCode: "LINE_PLANE_POSITION_RELATION" },
  { sourceCode: "POINT_TO_PLANE_DISTANCE", targetCode: "LINE_DISTANCE_IN_OXYZ" },
  { sourceCode: "PLANE_EQUATION_WRITING", targetCode: "PLANE_SPHERE_RELATION" },

  // --- Thống kê mẫu số liệu ghép nhóm ---
  { sourceCode: "GROUPED_DATA_FREQUENCY_TABLE", targetCode: "CALCULATE_GROUPED_MEAN" },
  { sourceCode: "GROUPED_DATA_FREQUENCY_TABLE", targetCode: "CALCULATE_GROUPED_MEDIAN" },
  { sourceCode: "CALCULATE_GROUPED_MEDIAN", targetCode: "CALCULATE_GROUPED_QUARTILES" },
  { sourceCode: "CALCULATE_GROUPED_QUARTILES", targetCode: "CALCULATE_GROUPED_IQR" },
  { sourceCode: "CALCULATE_GROUPED_MEAN", targetCode: "CALCULATE_GROUPED_VARIANCE" },
  { sourceCode: "CALCULATE_GROUPED_VARIANCE", targetCode: "CALCULATE_GROUPED_STANDARD_DEVIATION" },
  { sourceCode: "CALCULATE_GROUPED_STANDARD_DEVIATION", targetCode: "COMPARE_GROUPED_VARIANCE_SD" },

  // --- Xác suất có điều kiện ---
  { sourceCode: "SAMPLE_SPACE_EVENT_IDENTIFICATION", targetCode: "CONDITIONAL_PROBABILITY_DEFINITION" },
  { sourceCode: "CONDITIONAL_PROBABILITY_DEFINITION", targetCode: "CONDITIONAL_PROBABILITY_FORMULA" },
  { sourceCode: "CONDITIONAL_PROBABILITY_FORMULA", targetCode: "MULTIPLICATION_RULE_PROBABILITY" },
  { sourceCode: "CONDITIONAL_PROBABILITY_FORMULA", targetCode: "PROBABILITY_TREE_METHOD" },
  { sourceCode: "MULTIPLICATION_RULE_PROBABILITY", targetCode: "TOTAL_PROBABILITY_FORMULA" },
  { sourceCode: "TOTAL_PROBABILITY_FORMULA", targetCode: "BAYES_FORMULA_APPLICATION" },
];

// Pre-build index for fast lookups
const prerequisiteMap = new Map<string, string[]>();
const postrequisiteMap = new Map<string, string[]>();

for (const edge of VERIFIED_PREREQUISITE_EDGES) {
  // Edge: sourceCode is prerequisite of targetCode
  const prereqs = prerequisiteMap.get(edge.targetCode) ?? [];
  prereqs.push(edge.sourceCode);
  prerequisiteMap.set(edge.targetCode, prereqs);

  const postreqs = postrequisiteMap.get(edge.sourceCode) ?? [];
  postreqs.push(edge.targetCode);
  postrequisiteMap.set(edge.sourceCode, postreqs);
}

/**
 * Returns all direct prerequisite problem type codes that must be learned before the target.
 */
export function getPrerequisitesForProblemType(ptCode: string): string[] {
  return prerequisiteMap.get(ptCode) ?? [];
}

/**
 * Returns all direct postrequisite problem type codes unlocked by completing this skill.
 */
export function getPostrequisitesForProblemType(ptCode: string): string[] {
  return postrequisiteMap.get(ptCode) ?? [];
}

/**
 * Returns full transitive learning path chain leading to targetCode (DFS traversal).
 */
export function getLearningPathChain(targetCode: string): string[] {
  const visited = new Set<string>();
  const path: string[] = [];

  function dfs(code: string) {
    if (visited.has(code)) return;
    visited.add(code);
    const prereqs = prerequisiteMap.get(code) ?? [];
    for (const prereq of prereqs) {
      dfs(prereq);
    }
    path.push(code);
  }

  dfs(targetCode);
  return path;
}
