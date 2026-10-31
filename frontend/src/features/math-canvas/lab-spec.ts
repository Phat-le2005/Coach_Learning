import { normalizeFormula, parseScalarExpression, type MathNode } from "./expression";
import { compileGraphScene, type SceneRelation } from "./scene";

export type LabPoint = [number, number, number];
export type LabDocument =
  | { version: 1; kind: "PIECEWISE"; dimension: "2D"; branches: { expression: string; condition: string }[] }
  | { version: 1; kind: "PARAMETRIC"; dimension: "2D" | "3D"; coordinates: string[]; interval: [number, number]; progress: number }
  | { version: 1; kind: "VECTOR"; dimension: "2D" | "3D"; origin: string[]; u: string[]; v: string[]; operation: "SUM" | "DIFFERENCE" | "PROJECTION" }
  | { version: 1; kind: "CALCULUS"; dimension: "2D"; expression: string; point: number; bounds: [number, number]; rectangles: number; showDerivative: boolean };
export interface CompiledLab { document: LabDocument; parameters: string[]; nodes: MathNode[]; conditions: SceneRelation[][] }
export const LAB_TITLES: Record<LabDocument["kind"], string> = { PIECEWISE: "Hàm từng đoạn", PARAMETRIC: "Đường tham số", VECTOR: "Vector & tọa độ", CALCULUS: "Đạo hàm & tích phân" };

export function describeLabDocument(document: LabDocument): string[] {
  if (document.kind === "PIECEWISE") return document.branches.map((branch) => `y = ${branch.expression}, khi ${branch.condition}`);
  if (document.kind === "PARAMETRIC") return [...document.coordinates.map((value, index) => `${["x", "y", "z"][index]}(t) = ${value}`), `${document.interval[0]} ≤ t ≤ ${document.interval[1]}`];
  if (document.kind === "VECTOR") return [`O = (${document.origin.join("; ")})`, `u = (${document.u.join("; ")})`, `v = (${document.v.join("; ")})`, document.operation === "SUM" ? "Tổng u + v" : document.operation === "DIFFERENCE" ? "Hiệu u − v" : "Hình chiếu của u lên v"];
  return [`f(x) = ${document.expression}`, `Điểm tiếp xúc x₀ = ${document.point}`, `Tích phân từ ${document.bounds[0]} đến ${document.bounds[1]}`, `${document.rectangles} hình chữ nhật dùng điểm giữa`];
}

export function validLabCamera(value: unknown): value is import("./expression").GraphCamera {
  if (!value || typeof value !== "object") return false;
  const camera = value as import("./expression").GraphCamera;
  return Array.isArray(camera.position) && Array.isArray(camera.target) && camera.position.length === 3 && camera.target.length === 3
    && [...camera.position, ...camera.target].every((coordinate) => typeof coordinate === "number" && Number.isFinite(coordinate) && Math.abs(coordinate) <= 1000)
    && Math.hypot(...camera.position.map((coordinate, index) => coordinate - camera.target[index])) >= .1
    && typeof camera.zoom === "number" && Number.isFinite(camera.zoom) && camera.zoom >= .05 && camera.zoom <= 30;
}

/** Typed representations share the scalar grammar; no formula is executed as JavaScript. */
export function compileLab(input: LabDocument): CompiledLab {
  const document = structuredClone(input), parameters = new Set<string>(), nodes: MathNode[] = [], conditions: SceneRelation[][] = [];
  if (document.version !== 1 || !Object.hasOwn(LAB_TITLES, document.kind) || !["2D", "3D"].includes(document.dimension)) throw new Error("Dạng khám phá chưa được hỗ trợ.");
  function scalar(source: string, coordinate?: "x" | "t"): string {
    const parsed = parseScalarExpression(normalizeFormula(source));
    for (const name of parsed.variables) {
      if (name === coordinate) continue;
      if (["x", "y", "z"].includes(name) || !/^[a-df-w]$/.test(name)) throw new Error(coordinate ? `Biểu thức này chỉ dùng biến ${coordinate} và các tham số a–w (trừ e).` : "Tọa độ dùng số hoặc tham số a–w (trừ e).");
      parameters.add(name);
    }
    nodes.push(parsed.node); return parsed.canonical;
  }
  const bounded = (value: number, min = -100, max = 100) => { if (!Number.isFinite(value) || value < min || value > max) throw new Error(`Giá trị phải nằm từ ${min} đến ${max}.`); };
  if (document.kind === "PIECEWISE") {
    if (document.dimension !== "2D" || document.branches.length < 1 || document.branches.length > 6) throw new Error("Hàm từng đoạn có từ 1 đến 6 nhánh trên mặt phẳng.");
    document.branches = document.branches.map((branch, index) => {
      const expression = scalar(branch.expression, "x");
      const scene = compileGraphScene({ version: 2, dimension: "2D", combine: "AND", rows: [{ id: "condition", expression: branch.condition, visible: true, color: "#167a60" }] });
      const layer = scene.layers[0];
      if (Object.keys(scene.errors).length || !layer || /[yz]/.test(layer.expression) || !layer.expression.includes("x")) throw new Error(`Điều kiện nhánh ${index + 1} cần một khoảng theo x, ví dụ x<0 hoặc 0<=x<=2.`);
      scene.parameters.forEach((name) => parameters.add(name)); conditions.push(layer.relations);
      return { expression, condition: layer.expression };
    });
  } else if (document.kind === "PARAMETRIC") {
    if (document.coordinates.length !== (document.dimension === "3D" ? 3 : 2)) throw new Error("Cần đủ tọa độ cho đường tham số.");
    document.coordinates = document.coordinates.map((value) => scalar(value, "t"));
    document.interval.forEach((value) => bounded(value)); bounded(document.progress, 0, 1);
    if (document.interval[1] - document.interval[0] < 1e-6) throw new Error("Cận cuối của t phải lớn hơn cận đầu.");
  } else if (document.kind === "VECTOR") {
    const count = document.dimension === "3D" ? 3 : 2;
    if (!["SUM", "DIFFERENCE", "PROJECTION"].includes(document.operation) || [document.origin, document.u, document.v].some((values) => values.length !== count)) throw new Error("Cần đủ thành phần vector và một phép toán hợp lệ.");
    document.origin = document.origin.map((value) => scalar(value));
    document.u = document.u.map((value) => scalar(value)); document.v = document.v.map((value) => scalar(value));
  } else {
    if (document.dimension !== "2D") throw new Error("Khám phá giải tích dùng hàm một biến x.");
    document.expression = scalar(document.expression, "x"); bounded(document.point, -10, 10);
    document.bounds.forEach((value) => bounded(value, -10, 10));
    if (!Number.isInteger(document.rectangles) || document.rectangles < 4 || document.rectangles > 120 || typeof document.showDerivative !== "boolean") throw new Error("Số hình chữ nhật từ 4 đến 120.");
  }
  if (parameters.size > 6) throw new Error("Mỗi khám phá có tối đa 6 tham số dùng chung.");
  return { document, parameters: [...parameters].sort(), nodes, conditions };
}

export interface LabExample { id: string; title: string; question: string; document: LabDocument }
export const LAB_EXAMPLES: LabExample[] = [
  { id: "piecewise", title: "Hai quy luật, một hàm số", question: "Hai nhánh có gặp nhau tại x = 0 không? Thay a và quan sát bước nhảy.", document: { version: 1, kind: "PIECEWISE", dimension: "2D", branches: [{ expression: "-x", condition: "x<0" }, { expression: "x^2+a", condition: "x>=0" }] } },
  { id: "ellipse", title: "Điểm chạy thành ellipse", question: "Thay a, b rồi kéo t. Khi nào ellipse trở thành đường tròn?", document: { version: 1, kind: "PARAMETRIC", dimension: "2D", coordinates: ["a*cos(t)", "b*sin(t)"], interval: [0, 6.283185307179586], progress: .15 } },
  { id: "helix", title: "Đường xoắn trong không gian", question: "Tăng a làm thay đổi bán kính hay bước xoắn? Xoay hình để kiểm tra.", document: { version: 1, kind: "PARAMETRIC", dimension: "3D", coordinates: ["2*cos(t)", "2*sin(t)", "a*t/4"], interval: [-12.566370614359172, 12.566370614359172], progress: .5 } },
  { id: "vectors", title: "Quy tắc hình bình hành", question: "Đổi thành phần vector u. Tổng u + v có còn nằm trên đường chéo không?", document: { version: 1, kind: "VECTOR", dimension: "2D", origin: ["0", "0"], u: ["a", "1"], v: ["1", "2"], operation: "SUM" } },
  { id: "vectors3d", title: "Hai vector trong Oxyz", question: "Thử phép chiếu. Khi hai vector vuông góc, hình chiếu có độ dài bao nhiêu?", document: { version: 1, kind: "VECTOR", dimension: "3D", origin: ["0", "0", "0"], u: ["2", "1", "a"], v: ["1", "2", "1"], operation: "PROJECTION" } },
  { id: "calculus", title: "Độ dốc và diện tích", question: "Kéo điểm tiếp xúc, sau đó đổi hai cận. Vì sao tích phân có thể âm?", document: { version: 1, kind: "CALCULUS", dimension: "2D", expression: "x^2-1", point: 1, bounds: [-1, 1], rectangles: 12, showDerivative: true } },
];

export function parseLabDraft(raw: string | null): { document: LabDocument; parameters: Record<string, number>; domain: number; note: string; camera?: import("./expression").GraphCamera } | null {
  if (!raw || raw.length > 18000) return null;
  try {
    const data = JSON.parse(raw), compiled = compileLab(data.document);
    if (!data.parameters || typeof data.parameters !== "object" || Array.isArray(data.parameters) || Object.keys(data.parameters).length > 6 || Object.entries(data.parameters).some(([name, value]) => !compiled.parameters.includes(name) || typeof value !== "number" || !Number.isFinite(value) || Math.abs(value) > 5) || !Number.isFinite(data.domain) || data.domain < 1 || data.domain > 10 || typeof data.note !== "string" || data.note.length > 1000) return null;
    return { document: compiled.document, parameters: data.parameters, domain: data.domain, note: data.note, ...(validLabCamera(data.camera) ? {camera:data.camera} : {}) };
  } catch { return null; }
}
