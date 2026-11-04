/** Small mathematical grammar. No eval, Function, property access, or executable code. */
export type MathNode = { kind: "number"; value: number } | { kind: "variable"; name: string }
  | { kind: "unary"; node: MathNode } | { kind: "call"; name: string; node: MathNode }
  | { kind: "guard"; argument: MathNode; node: MathNode }
  | { kind: "binary"; op: string; left: MathNode; right: MathNode };

export interface MathExpression {
  expression: string;
  dimension: "2D" | "3D";
  kind: "explicit" | "implicit";
  parameters: string[];
  node: MathNode;
}
export interface GraphSettings {
  parameters: Record<string, number>;
  scale: number;
  offset: number;
  shift_x: number;
  shift_y: number;
  domain: number;
  view_mode?: "AUTO" | "2D" | "3D" | "EXTRUDED";
  slice_y?: number;
  scene_depth?: number;
  scene_surface?: boolean;
  scene?: import("./scene").GraphSceneDocument | null;
  lab?: import("./lab-spec").LabDocument | null;
}
export type NumericGraphSetting = "scale" | "offset" | "shift_x" | "shift_y" | "domain" | "slice_y";
export interface GraphCamera { position: [number, number, number]; target: [number, number, number]; zoom?: number }
export function defaultCamera(dimension: "2D" | "3D"): GraphCamera {
  return dimension === "3D" ? { position: [11, 9, 13], target: [0, 0, 0] } : { position: [0, 0, 16], target: [0, 0, 0] };
}
export const DEFAULT_GRAPH: GraphSettings = { parameters: {}, scale: 1, offset: 0, shift_x: 0, shift_y: 0, domain: 3 };
const FUNCTIONS: Record<string, (x: number) => number> = {
  sin: Math.sin, cos: Math.cos, tan: Math.tan, sqrt: Math.sqrt, abs: Math.abs,
  exp: Math.exp, log: Math.log, ln: Math.log,
};
const isFunction = (name: string) => Object.hasOwn(FUNCTIONS, name);

/** Conventional trig powers apply to the call value: cos²(x) = (cos(x))².
 * Keep the resulting power atomic, including when another outer power follows.
 * Negative/variable powers before the argument remain explicit-only to avoid
 * confusing reciprocal notation with inverse trigonometric functions.
 */
function normalizeTrigPowers(input: string, depth = 0): string {
  if (depth > 24) throw new Error("Công thức lồng quá sâu.");
  const pattern = /(?<![a-z])(sin|cos|tan)\^(?:\(([1-9]\d*)\)|([1-9]\d*))\(/g;
  let output = "", cursor = 0, match: RegExpExecArray | null;
  while ((match = pattern.exec(input))) {
    const open = pattern.lastIndex - 1;
    let end = open + 1, nesting = 1;
    for (; end < input.length; end++) {
      if (input[end] === "(") nesting++;
      if (input[end] === ")" && --nesting === 0) break;
    }
    if (nesting) throw new Error("Thiếu dấu đóng ngoặc.");
    const argument = normalizeTrigPowers(input.slice(open + 1, end), depth + 1);
    output += input.slice(cursor, match.index) + `(${match[1]}(${argument})^${match[2] ?? match[3]})`;
    cursor = end + 1; pattern.lastIndex = cursor;
  }
  return output + input.slice(cursor);
}

export function normalizeFormula(source: string): string {
  if (source.length > 500) throw new Error("Công thức quá dài (tối đa 500 ký tự).");
  let text = source.trim().replace(/\$/g, "").replace(/\\(?:left|right|,|;|!|quad|qquad)/g, "")
    .replace(/[−–]/g, "-").replace(/[×·]/g, "*").replace(/÷/g, "/")
    .replace(/²/g, "^2").replace(/³/g, "^3").replace(/π/g, "pi")
    .replace(/\\(?:cdot|times)/g, "*").replace(/\\pi/g, "pi")
    .replace(/\\(sin|cos|tan|exp|log|ln)/g, "$1");
  function expand(input: string, depth = 0): string {
    if (depth > 24) throw new Error("Công thức lồng quá sâu.");
    let index = 0, output = "";
    function group(): string {
      while (input[index] === " ") index++;
      if (input[index++] !== "{") throw new Error("Nhóm LaTeX chưa đúng định dạng.");
      const start = index; let nesting = 1;
      while (index < input.length && nesting) { if (input[index] === "{") nesting++; if (input[index] === "}") nesting--; index++; }
      if (nesting) throw new Error("Thiếu dấu đóng ngoặc LaTeX.");
      return expand(input.slice(start, index - 1), depth + 1);
    }
    while (index < input.length) {
      const command = input.slice(index).match(/^\\(dfrac|tfrac|frac|sqrt)/);
      if (command) {
        index += command[0].length;
        const first = group();
        output += command[1] === "sqrt" ? `sqrt(${first})` : `((${first})/(${group()}))`;
      } else if (input[index] === "{") output += `(${group()})`;
      else output += input[index++];
    }
    return output;
  }
  text = expand(text);
  text = text.replace(/\s+/g, "").toLowerCase();
  if (/[\\{}]/.test(text)) throw new Error("Ký hiệu LaTeX chưa được hỗ trợ. Hãy sửa thành dạng z=x^2+y^2.");
  return normalizeTrigPowers(text);
}

export function parseMathExpression(source: string): MathExpression {
  const normalized = normalizeFormula(source);
  const sides = normalized.split("=");
  if (sides.length > 2) throw new Error("Hãy chọn một công thức với tối đa một dấu bằng.");
  const lhs = sides.length === 2 ? sides[0] : "";
  const implicit = sides.length === 2 && !["y", "z", "f(x)", "f(x,y)"].includes(lhs);
  if (sides.some((side) => !side)) throw new Error("Biểu thức chưa hoàn chỉnh.");
  // An implicit equation is sampled as the zero set of lhs-rhs, never solved.
  const body = implicit ? `(${lhs})-(${sides[1]})` : sides[sides.length - 1];
  const { node, variables, canonical } = parseScalarExpression(body);
  if (!implicit && variables.has("z")) throw new Error("Vế phải của hàm tường minh không được chứa z. Với phương trình ẩn, nhập dạng x²+y²+z²=4.");
  const dimension = implicit ? (variables.has("z") ? "3D" : "2D")
    : lhs === "z" || lhs === "f(x,y)" || variables.has("y") ? "3D" : "2D";
  if (!implicit && (lhs === "y" || lhs === "f(x)") && dimension === "3D") throw new Error("Vế phải của y=f(x) không được chứa y. Hãy chuyển mọi hạng tử sang một vế để vẽ phương trình ẩn.");
  if (implicit && !["x", "y", "z"].some((v) => variables.has(v))) throw new Error("Phương trình cần chứa tọa độ x, y hoặc z.");
  const parameters = [...variables].filter((v) => !["x", "y", "z"].includes(v)).sort();
  if (parameters.length > 6) throw new Error("Tối đa 6 tham số trong một hàm.");
  let boundary = 0, nesting = 0;
  if (implicit) for (let i = 0; i < canonical.length; i++) {
    if (canonical[i] === "(") nesting++;
    if (canonical[i] === ")" && --nesting === 0) { boundary = i; break; }
  }
  const equation = implicit ? `${canonical.slice(1, boundary)}=${canonical.slice(boundary + 3, -1)}`
    : `${dimension === "3D" ? "z" : "y"}=${canonical}`;
  return { expression: equation, dimension, kind: implicit ? "implicit" : "explicit", parameters, node };
}

export interface ScalarContext {
  functions: Set<string>;
  resolve: (name: string, argument: MathNode) => MathNode;
}
/** Shared scalar grammar; user-defined functions are expanded as bounded ASTs. */
export function parseScalarExpression(body: string, context?: ScalarContext): { node: MathNode; variables: Set<string>; canonical: string } {
  const callable = (name: string) => isFunction(name) || !!context?.functions.has(name) || (!!context && /^[fgh]$/.test(name));
  const raw = body.match(/(?:\d+(?:\.\d*)?|\.\d+)(?:e[+-]?\d+)?|[a-z]+|[+*/^()-]/g) ?? [];
  if (!body || raw.join("") !== body || raw.length > 160) throw new Error("Công thức chứa ký hiệu không hỗ trợ.");
  // Split adjacent single-letter symbols: xy, ax, etc. Known functions/constants remain intact.
  const expanded = raw.flatMap((token) => /^[a-z]+$/.test(token) && !isFunction(token) && token !== "pi"
    ? token.split("") : [/^(?:\d|\.)/.test(token) ? Number(token).toString() : token]);
  const tokens: string[] = [];
  for (const token of expanded) {
    const prev = tokens[tokens.length - 1];
    if (prev && (/^[\da-z.]/.test(prev) || prev === ")") && (/^[\da-z.]/.test(token) || token === "(") && !callable(prev)) tokens.push("*");
    tokens.push(token);
  }
  if (tokens.length > 120 || tokens.join("").length > 498) throw new Error("Công thức quá phức tạp để trực quan hóa.");
  let index = 0;
  const variables = new Set<string>();
  function primary(depth: number): MathNode {
    if (depth > 40) throw new Error("Công thức lồng quá sâu.");
    const token = tokens[index++];
    if (token === "(") {
      const node = expression(0, depth + 1);
      if (tokens[index++] !== ")") throw new Error("Thiếu dấu đóng ngoặc.");
      return node;
    }
    if (token === "+") return expression(25, depth + 1);
    if (token === "-") return { kind: "unary", node: expression(25, depth + 1) };
    if (token && callable(token) && (isFunction(token) || context?.functions.has(token) || tokens[index] === "(")) {
      if (tokens[index] === "^") throw new Error(`Hãy viết lũy thừa theo dạng (${token}(x))^2; số mũ âm hoặc tham số cần đặt sau đối số.`);
      if (tokens[index++] !== "(") throw new Error(`Hãy viết ${token}(...) với dấu ngoặc.`);
      const node = expression(0, depth + 1);
      if (tokens[index++] !== ")") throw new Error("Thiếu dấu đóng ngoặc.");
      return isFunction(token) ? { kind: "call", name: token, node } : context!.resolve(token, node);
    }
    if (token && /^(?:\d|\.)/.test(token)) {
      const value = Number(token);
      if (!Number.isFinite(value) || Math.abs(value) > 1e6) throw new Error("Hằng số ngoài phạm vi hỗ trợ.");
      return { kind: "number", value };
    }
    if (token === "pi" || token === "e") return { kind: "number", value: token === "pi" ? Math.PI : Math.E };
    if (token && /^[a-z]$/.test(token)) {
      variables.add(token);
      return { kind: "variable", name: token };
    }
    throw new Error("Biểu thức chưa hoàn chỉnh.");
  }
  function expression(min: number, depth: number): MathNode {
    let left = primary(depth + 1);
    while (index < tokens.length) {
      const op = tokens[index];
      const precedence = op === "+" || op === "-" ? 10 : op === "*" || op === "/" ? 20 : op === "^" ? 30 : -1;
      if (precedence < min) break;
      index++;
      const right = expression(op === "^" ? precedence : precedence + 1, depth + 1);
      left = { kind: "binary", op, left, right };
    }
    return left;
  }
  const node = expression(0, 0);
  if (index !== tokens.length) throw new Error("Biểu thức chưa hoàn chỉnh.");
  // Expanded functions may introduce parameters absent from the original call.
  variables.clear();
  let count = 0;
  function visit(current: MathNode, depth = 0): void {
    if (++count > 600 || depth > 40) throw new Error("Hàm hợp quá phức tạp để vẽ. Hãy tách thành các dòng đơn giản hơn.");
    if (current.kind === "variable") variables.add(current.name);
    else if (current.kind === "guard") { visit(current.argument, depth + 1); visit(current.node, depth + 1); }
    else if (current.kind === "unary" || current.kind === "call") visit(current.node, depth + 1);
    else if (current.kind === "binary") { visit(current.left, depth + 1); visit(current.right, depth + 1); }
  }
  visit(node);
  return { node, variables, canonical: tokens.join("") };
}

export function evaluateMath(node: MathNode, values: Record<string, number>): number {
  if (node.kind === "number") return node.value;
  if (node.kind === "variable") return values[node.name] ?? 1;
  if (node.kind === "guard") return Number.isFinite(evaluateMath(node.argument, values)) ? evaluateMath(node.node, values) : NaN;
  if (node.kind === "unary") return -evaluateMath(node.node, values);
  if (node.kind === "call") return FUNCTIONS[node.name](evaluateMath(node.node, values));
  const l = evaluateMath(node.left, values), r = evaluateMath(node.right, values);
  switch (node.op) { case "+": return l + r; case "-": return l - r; case "*": return l * r; case "/": return l / r; default: return l ** r; }
}
export function sampleGraph(model: MathExpression, settings: GraphSettings, x: number, y = 0): number {
  const value = settings.scale * evaluateMath(model.node, { ...settings.parameters, x: x - settings.shift_x, y: y - settings.shift_y }) + settings.offset;
  return Number.isFinite(value) && Math.abs(value) <= 1e5 ? value : NaN;
}

/** Coordinates stay mathematical here; renderers own the world-axis mapping. */
export function sampleImplicit(model: MathExpression, settings: GraphSettings, x: number, y: number, z = 0): number {
  const value = evaluateMath(model.node, { ...settings.parameters, x, y, z });
  return Number.isFinite(value) ? value : NaN;
}
