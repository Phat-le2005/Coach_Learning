import { evaluateMath, normalizeFormula, parseScalarExpression, type MathNode, type ScalarContext } from "./expression";

export const SCENE_COLORS = ["#2563eb", "#e05a23", "#7c3aed", "#07856b", "#be185d", "#98670b", "#0891b2", "#475569"];
export type RelationOperator = "=" | "<" | "<=" | ">" | ">=";
export interface SceneRow { id: string; expression: string; visible: boolean; color: string }
export interface GraphSceneDocument { version: 2; dimension: "2D"; combine: "OVERLAY" | "AND" | "OR"; rows: SceneRow[] }
export interface SceneRelation { left: MathNode; right: MathNode; residual: MathNode; operator: RelationOperator }
export interface SceneLayer extends SceneRow { relations: SceneRelation[]; definition?: string; label: string; hint?: string }
export interface CompiledScene { document: GraphSceneDocument; layers: SceneLayer[]; parameters: string[]; errors: Record<string, string> }

export function normalizeRelation(source: string): string {
  return normalizeFormula(source.replace(/\\(?:geq|ge)/g, ">=").replace(/\\(?:leq|le)/g, "<=").replace(/≥/g, ">=").replace(/≤/g, "<="));
}
function substitute(node: MathNode, argument: MathNode): MathNode {
  if (node.kind === "variable" && node.name === "x") return argument;
  if (node.kind === "guard") return { ...node, argument: substitute(node.argument, argument), node: substitute(node.node, argument) };
  if (node.kind === "unary" || node.kind === "call") return { ...node, node: substitute(node.node, argument) };
  if (node.kind === "binary") return { ...node, left: substitute(node.left, argument), right: substitute(node.right, argument) };
  return node;
}

/** A scene has explicit relation semantics. Function definitions never execute source code. */
export function compileGraphScene(document: GraphSceneDocument): CompiledScene {
  const errors: Record<string, string> = {}, normalized = new Map<string, string>();
  const definitions = new Map<string, { id: string; body: string }>(), duplicates = new Set<string>();
  const layers: SceneLayer[] = [], canonicalRows: SceneRow[] = [], parameters = new Set<string>();
  if (document.rows.length > 8) throw new Error("Mỗi bảng có tối đa 8 dòng biểu thức.");
  if (new Set(document.rows.map((row) => row.id)).size !== document.rows.length) throw new Error("Mã dòng biểu thức bị trùng.");
  for (const row of document.rows) {
    if (!row.expression.trim()) continue;
    try {
      const source = normalizeRelation(row.expression); normalized.set(row.id, source);
      const match = source.match(/^([a-df-w])\(x\)=([^=<>]+)$/);
      if (match) {
        if (definitions.has(match[1])) { duplicates.add(match[1]); errors[definitions.get(match[1])!.id] = `Hàm ${match[1]} được định nghĩa hai lần.`; }
        definitions.set(match[1], { id: row.id, body: match[2] });
      }
    } catch (error) { errors[row.id] = error instanceof Error ? error.message : "Chưa đọc được công thức."; }
  }
  const cache = new Map<string, ReturnType<typeof parseScalarExpression>>(), visiting = new Set<string>();
  const context: ScalarContext = { functions: new Set(definitions.keys()), resolve: (name, argument) => ({ kind: "guard", argument, node: substitute(resolveDefinition(name).node, argument) }) };
  function resolveDefinition(name: string): ReturnType<typeof parseScalarExpression> {
    if (duplicates.has(name)) throw new Error(`Hàm ${name} được định nghĩa hai lần.`);
    const definition = definitions.get(name);
    if (!definition) throw new Error(`Chưa định nghĩa hàm ${name}(x). Thêm một dòng như ${name}(x)=x^2.`);
    if (visiting.has(name)) throw new Error(`Các hàm tham chiếu vòng tại ${name}(x). Hãy sửa định nghĩa.`);
    const existing = cache.get(name); if (existing) return existing;
    visiting.add(name);
    try {
      const parsed = parseScalarExpression(definition.body, context);
      if (parsed.variables.has("y") || parsed.variables.has("z")) throw new Error(`Hàm ${name}(x) chỉ nhận biến x; các chữ khác là tham số.`);
      cache.set(name, parsed); return parsed;
    } finally { visiting.delete(name); }
  }
  for (const row of document.rows) {
    const source = normalized.get(row.id); if (!source || errors[row.id]) continue;
    try {
      let canonical: string, definition: string | undefined, horizontal=false;
      const relations: SceneRelation[] = [], symbols = new Set<string>();
      const match = source.match(/^([a-df-w])\(x\)=([^=<>]+)$/);
      if (match) {
        const parsed = resolveDefinition(match[1]); parsed.variables.forEach((name) => symbols.add(name)); symbols.add("y");
        const left: MathNode = { kind: "variable", name: "y" };
        relations.push({ left, right: parsed.node, residual: { kind: "binary", op: "-", left, right: parsed.node }, operator: "=" });
        canonical = `${match[1]}(x)=${parsed.canonical}`; definition = match[1];
      } else {
        const parts = source.split(/(<=|>=|=|<|>)/);
        if (parts.length === 1) parts.unshift("y", "=");
        if (parts.length > 7 || parts.length < 3 || parts.some((part) => !part)) throw new Error("Dùng một quan hệ như y≥x² hoặc một khoảng như 0≤x≤2.");
        const operands = parts.filter((_, index) => index % 2 === 0).map((part) => parseScalarExpression(part, context));
        operands.forEach((parsed) => parsed.variables.forEach((name) => symbols.add(name)));
        horizontal=operands.length===2&&parts[1]==="="&&operands[0].node.kind==="variable"&&operands[0].node.name==="y"&&!operands[1].variables.has("x")&&!operands[1].variables.has("y")&&!operands[1].variables.has("z");
        for (let i = 0; i < operands.length - 1; i++) {
          const operator = parts[i * 2 + 1] as RelationOperator;
          if (operands.length > 2 && operator === "=") throw new Error("Tách các phương trình thành những dòng riêng.");
          const left = operands[i].node, right = operands[i + 1].node;
          relations.push({ left, right, residual: { kind: "binary", op: "-", left, right }, operator });
        }
        canonical = operands.map((part, i) => `${i ? parts[i * 2 - 1] : ""}${part.canonical}`).join("");
      }
      if (symbols.has("z")) throw new Error("Công thức có z cần chế độ Không gian 3D. Bấm nút 3D ở dòng này.");
      if (!symbols.has("x") && !symbols.has("y")) throw new Error("Biểu thức cần chứa tọa độ x hoặc y.");
      symbols.forEach((name) => { if (name !== "x" && name !== "y") parameters.add(name); });
      const canonicalRow = { ...row, expression: canonical }; canonicalRows.push(canonicalRow);
      const symbolicParameters=[...symbols].filter((name)=>name!=="x"&&name!=="y").sort();
      const hint=horizontal&&symbolicParameters.length
        ? `Không có x trong công thức: ${symbolicParameters.join(", ")} là tham số, nên đồ thị là đường thẳng ngang. Nếu em muốn vẽ y=f(x), hãy kiểm tra lại ký hiệu trong công thức.`
        : undefined;
      layers.push({ ...canonicalRow, relations, definition, label: definition ? `Hàm ${definition}(x)` : horizontal ? "Đường thẳng ngang" : relations.every((relation) => relation.operator === "=") ? "Phương trình" : "Bất phương trình", hint });
    } catch (error) { errors[row.id] = error instanceof Error ? error.message : "Biểu thức chưa hợp lệ."; }
  }
  if (parameters.size > 6) for (const row of document.rows) if (row.expression.trim()) errors[row.id] ??= "Bảng có tối đa 6 tham số dùng chung.";
  return { document: { ...document, rows: canonicalRows }, layers, parameters: [...parameters].sort(), errors };
}

/** Exact membership predicate; numerical boundary sampling has a separate approximation. */
export function relationContains(relation: SceneRelation, values: Record<string, number>): boolean {
  const left = evaluateMath(relation.left, values), right = evaluateMath(relation.right, values);
  if (!Number.isFinite(left) || !Number.isFinite(right)) return false;
  switch (relation.operator) { case "=": return left === right; case "<": return left < right; case "<=": return left <= right; case ">": return left > right; case ">=": return left >= right; }
}
export function layerContains(layer: SceneLayer, x: number, y: number, parameters: Record<string, number>): boolean {
  return layer.relations.every((relation) => relationContains(relation, { ...parameters, x, y }));
}
