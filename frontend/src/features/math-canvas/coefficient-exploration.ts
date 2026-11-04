import { parseMathExpression, type GraphSettings, type MathExpression } from "./expression";
import { resolveGraphExpression } from "./presentation";
import { extractXPolynomial } from "./univariate-equation";

/** An explicit user action replaces fixed polynomial coefficients with named controls. */
export function createCoefficientExploration(model: MathExpression, settings: GraphSettings) {
  if (model.parameters.length) return null;
  const graph = resolveGraphExpression(model);
  if (graph.kind !== "explicit" || graph.dimension !== "2D") return null;
  const polynomial = extractXPolynomial(graph.node, {});
  if (!polynomial || polynomial.coefficients.some((value) => Math.abs(value) > 5)) return null;
  const [c, b, a] = polynomial.coefficients;
  const formula = a !== 0 ? "y=a*x^2+b*x+c" : b !== 0 ? "y=a*x+b" : "y=a";
  const values = a !== 0 ? { a, b, c } : b !== 0 ? { a: b, b: c } : { a: c };
  const parameters = Object.fromEntries(Object.entries(values).map(([name, value]) => [name, Object.is(value, -0) ? 0 : value]));
  return { model: parseMathExpression(formula), settings: { ...settings, parameters } };
}
