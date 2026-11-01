import { evaluateMath, type MathExpression, type MathNode } from "./expression";
import type { SampledGeometry } from "./geometry";

type Polynomial = [number, number, number];
export interface XPolynomialEquation {
  degree: 0 | 1 | 2;
  roots: number[];
  solution: "FINITE" | "ALL_REAL" | "NO_REAL";
  relatedFunction: string;
}

/** Read coefficients structurally; sampling a few points cannot prove polynomial identity. */
export function extractXPolynomial(node: MathNode, parameters: Record<string, number>) {
  let hasX = false;
  function polynomial(node: MathNode): Polynomial | null {
    if (node.kind === "number") return [node.value, 0, 0];
    if (node.kind === "variable") {
      if (node.name === "x") { hasX = true; return [0, 1, 0]; }
      if (["y", "z"].includes(node.name)) return null;
      const value = parameters[node.name] ?? 1;
      return Number.isFinite(value) ? [value, 0, 0] : null;
    }
    if (node.kind === "unary") { const p = polynomial(node.node); return p ? p.map((v) => -v) as Polynomial : null; }
    if (node.kind === "guard") return null;
    if (node.kind === "call") {
      const p = polynomial(node.node);
      if (!p || p[1] !== 0 || p[2] !== 0) return null;
      const value = evaluateMath(node, parameters);
      return Number.isFinite(value) ? [value, 0, 0] : null;
    }
    const left = polynomial(node.left), right = polynomial(node.right);
    if (!left || !right) return null;
    const multiply = (a: Polynomial, b: Polynomial): Polynomial | null => {
      const out = [0, 0, 0, 0, 0];
      for (let i = 0; i < 3; i++) for (let j = 0; j < 3; j++) out[i + j] += a[i] * b[j];
      return out[3] === 0 && out[4] === 0 ? out.slice(0, 3) as Polynomial : null;
    };
    if (node.op === "+" || node.op === "-") return left.map((v, i) => v + (node.op === "+" ? 1 : -1) * right[i]) as Polynomial;
    if (node.op === "*") return multiply(left, right);
    if (node.op === "/") return right[1] === 0 && right[2] === 0 && right[0] !== 0 ? left.map((v) => v / right[0]) as Polynomial : null;
    if (node.op === "^" && right[1] === 0 && right[2] === 0) {
      if (right[0] === 0) return [1, 0, 0];
      if (right[0] === 1) return left;
      if (right[0] === 2) return multiply(left, left);
    }
    return null;
  }
  const coefficients = polynomial(node);
  return coefficients?.every(Number.isFinite) ? { coefficients, hasX } : null;
}

/** Exact polynomial structure only: no search for roots across poles or guessed tangencies. */
export function analyzeXPolynomialEquation(model: MathExpression, parameters: Record<string, number>): XPolynomialEquation | null {
  if (model.kind !== "implicit" || model.dimension !== "2D") return null;
  const polynomial = extractXPolynomial(model.node, parameters);
  if (!polynomial?.hasX) return null;
  const { coefficients } = polynomial;
  const [c, b, a] = coefficients;
  let roots: number[] = [], solution: XPolynomialEquation["solution"] = "FINITE";
  const degree = a !== 0 ? 2 : b !== 0 ? 1 : 0;
  if (degree === 0) solution = c === 0 ? "ALL_REAL" : "NO_REAL";
  else if (degree === 1) roots = [-c / b];
  else {
    const discriminant = b * b - 4 * a * c;
    if (!Number.isFinite(discriminant)) return null;
    if (discriminant < 0) solution = "NO_REAL";
    else if (discriminant === 0) roots = [-b / (2 * a)];
    else {
      const q = -0.5 * (b + (b < 0 ? -1 : 1) * Math.sqrt(discriminant));
      roots = [q / a, c / q].sort((x, y) => x - y);
    }
  }
  if (!roots.every(Number.isFinite)) return null;
  const [lhs, rhs] = model.expression.split("=");
  const relatedFunction = rhs === "0" ? `y=${lhs}` : `y=(${lhs})-(${rhs})`;
  return { degree, roots: roots.map((root) => Object.is(root, -0) ? 0 : root), solution, relatedFunction };
}

export function sampleXPolynomialEquation(equation: XPolynomialEquation, domain: number): SampledGeometry {
  return { positions: equation.roots.filter((x) => Math.abs(x) <= domain).flatMap((x) => [x, -domain, 0, x, domain, 0]), primitive: "segments", truncated: false };
}

export function describeEquationRoot(value: number): string {
  return `x ${Number.isInteger(value) ? "=" : "≈"} ${Number(value.toPrecision(7)).toString().replace(/-/g, "−")}`;
}
