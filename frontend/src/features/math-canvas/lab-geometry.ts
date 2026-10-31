import { evaluateMath } from "./expression";
import { relationContains } from "./scene";
import { compileLab, type CompiledLab, type LabDocument, type LabPoint } from "./lab-spec";

export interface LabLine { points: LabPoint[]; color: string; dashed?: boolean; arrow?: boolean }
export interface LabMarker { point: LabPoint; color: string; open?: boolean; label?: string }
export interface LabDrawing { lines: LabLine[]; polygons: { points: LabPoint[]; color: string }[]; markers: LabMarker[]; measurements: { label: string; value: string }[]; notices: string[] }
const COLORS = ["#0f9d89", "#ea7847", "#8b6be8", "#2a82d7", "#c85793", "#a68527"];
const valid = (point: LabPoint) => point.every((value) => Number.isFinite(value) && Math.abs(value) <= 10000);
const add = (a: LabPoint, b: LabPoint): LabPoint => a.map((value, i) => value + b[i]) as LabPoint;
const multiply = (a: LabPoint, factor: number): LabPoint => a.map((value) => value * factor) as LabPoint;
const dot = (a: LabPoint, b: LabPoint) => a.reduce((value, item, i) => value + item * b[i], 0);
const distance = (a: LabPoint, b: LabPoint) => Math.hypot(...a.map((value, i) => value - b[i]));
const format = (value: number | null) => value === null || !Number.isFinite(value) ? "Chưa xác định" : Number(value.toPrecision(6)).toString();

/** Compare one-sided slopes; corners, poles and undefined neighborhoods have no displayed derivative. */
export function numericalDerivative(fn: (x: number) => number, x: number): number | null {
  const h = 1e-4 * Math.max(1, Math.abs(x)), y = fn(x), left = fn(x - h), right = fn(x + h), innerLeft = fn(x - h / 2), innerRight = fn(x + h / 2);
  if (![y, left, right, innerLeft, innerRight].every(Number.isFinite)) return null;
  const a = (y - innerLeft) / (h / 2), b = (innerRight - y) / (h / 2), outer = (right - left) / (2 * h), inner = (innerRight - innerLeft) / h;
  if (Math.abs(a - b) > .005 * Math.max(1, Math.abs(a), Math.abs(b)) || Math.abs(inner - outer) > .002 * Math.max(1, Math.abs(inner))) return null;
  return Number.isFinite(inner) ? inner : null;
}

/** Proper finite integral only. Convergence is checked; this is not symbolic integration. */
export function numericalIntegral(fn: (x: number) => number, a: number, b: number): { value: number; error: number } | null {
  if (a === b) return Number.isFinite(fn(a)) ? { value: 0, error: 0 } : null;
  const simpson = (n: number) => {
    const h = (b - a) / n; let sum = 0;
    for (let i = 0; i <= n; i++) { const y = fn(a + i * h); if (!Number.isFinite(y) || Math.abs(y) > 1e8) return NaN; sum += y * (i === 0 || i === n ? 1 : i % 2 ? 4 : 2); }
    return sum * h / 3;
  };
  const coarse = simpson(1024), fine = simpson(2048), error = Math.abs(fine - coarse) / 15;
  return Number.isFinite(fine) && Number.isFinite(coarse) && error <= 1e-5 * Math.max(1, Math.abs(fine)) ? { value: fine, error } : null;
}

function sampleLine(drawing: LabDrawing, fn: (value: number) => LabPoint, start: number, end: number, color: string, domain: number, dashed = false): void {
  let points: LabPoint[] = [];
  const flush = () => { if (points.length > 1) drawing.lines.push({ points, color, dashed }); points = []; };
  for (let i = 0; i <= 720; i++) {
    const value = start + (end - start) * i / 720, point = fn(value);
    if (!valid(point)) { flush(); continue; }
    if (points.length) {
      const previous = points[points.length - 1], middle = fn(value - (end - start) / 1440), midpoint = multiply(add(previous, point), .5);
      if (!valid(middle) || distance(point, previous) > Math.max(4, domain * 3) || distance(middle, midpoint) > Math.max(.02, distance(point, previous) * .15)) flush();
    }
    points.push(point);
  }
  flush();
}

export function piecewiseValue(compiled: CompiledLab, x: number, parameters: Record<string, number>): { value: number; branch: number } {
  const branch = compiled.conditions.findIndex((conditions) => conditions.every((condition) => relationContains(condition, { ...parameters, x })));
  return { value: branch < 0 ? NaN : evaluateMath(compiled.nodes[branch], { ...parameters, x }), branch };
}

export function sampleLab(document: LabDocument, parameters: Record<string, number>, domain: number): LabDrawing {
  const compiled = compileLab(document), drawing: LabDrawing = { lines: [], polygons: [], markers: [], measurements: [], notices: [] };
  if (!Number.isFinite(domain) || domain < 1 || domain > 10 || compiled.parameters.some((name) => !Number.isFinite(parameters[name]) || Math.abs(parameters[name]) > 5)) throw new Error("Tham số hoặc miền khảo sát không hợp lệ.");
  const value = (index: number, extra: Record<string, number> = {}) => evaluateMath(compiled.nodes[index], { ...parameters, ...extra });
  if (document.kind === "PIECEWISE") {
    for (let branch = 0; branch < document.branches.length; branch++) sampleLine(drawing, (x) => { const result = piecewiseValue(compiled, x, parameters); return [x, result.branch === branch ? result.value : NaN, 0]; }, -domain, domain, COLORS[branch], domain);
    // Locate changes in branch membership, then display both included and excluded limits.
    for (let i = 1; i <= 720; i++) {
      let lo = -domain + 2 * domain * (i - 1) / 720, hi = -domain + 2 * domain * i / 720;
      const left = piecewiseValue(compiled, lo, parameters).branch, right = piecewiseValue(compiled, hi, parameters).branch;
      if (left === right) continue;
      for (let j = 0; j < 35; j++) { const mid = (lo + hi) / 2; if (piecewiseValue(compiled, mid, parameters).branch === left) lo = mid; else hi = mid; }
      const x = (lo + hi) / 2;
      const included = compiled.conditions.findIndex((conditions) => conditions.every((condition) => {
        const l = evaluateMath(condition.left, { ...parameters, x }), r = evaluateMath(condition.right, { ...parameters, x });
        return Math.abs(l - r) < 1e-8 ? ["=", "<=", ">="].includes(condition.operator) : relationContains(condition, { ...parameters, x });
      }));
      for (const branch of new Set([left, right])) if (branch >= 0) { const point: LabPoint = [x, value(branch, { x }), 0]; if (valid(point) && drawing.markers.length < 60) drawing.markers.push({ point, color: COLORS[branch], open: included !== branch }); }
    }
    drawing.notices.push("Chấm đặc: lấy điểm; chấm rỗng: không lấy điểm. Nếu điều kiện chồng nhau, nhánh trên được ưu tiên. Chi tiết nhỏ hơn bước lấy mẫu có thể bị bỏ sót.");
  } else if (document.kind === "PARAMETRIC") {
    const point = (t: number): LabPoint => [value(0, { t }), value(1, { t }), document.dimension === "3D" ? value(2, { t }) : 0];
    sampleLine(drawing, point, ...document.interval, COLORS[0], domain);
    const t = document.interval[0] + (document.interval[1] - document.interval[0]) * document.progress, current = point(t);
    if (valid(current)) drawing.markers.push({ point: current, color: COLORS[1], label: "P(t)" });
    drawing.measurements.push({ label: "Tham số đường t", value: format(t) }, { label: "Điểm P(t)", value: valid(current) ? `(${current.slice(0, document.dimension === "3D" ? 3 : 2).map(format).join("; ")})` : "Ngoài miền xác định" });
  } else if (document.kind === "VECTOR") {
    const count = document.dimension === "3D" ? 3 : 2;
    const vector = (offset: number): LabPoint => [value(offset), value(offset + 1), count === 3 ? value(offset + 2) : 0];
    const origin = vector(0), u = vector(count), v = vector(count * 2);
    if (![origin, u, v].every(valid)) { drawing.notices.push("Một thành phần vector chưa xác định hoặc vượt phạm vi hiển thị."); return drawing; }
    const normU = Math.sqrt(dot(u, u)), normV = Math.sqrt(dot(v, v)), product = dot(u, v);
    const result = document.operation === "SUM" ? add(u, v) : document.operation === "DIFFERENCE" ? add(u, multiply(v, -1)) : normV > 1e-10 ? multiply(v, product / (normV * normV)) : null;
    drawing.lines.push({ points: [origin, add(origin, u)], color: COLORS[0], arrow: true }, { points: [origin, add(origin, v)], color: COLORS[1], arrow: true });
    drawing.markers.push({ point: origin, color: "#748298", label: "O" }, { point: add(origin, u), color: COLORS[0], label: "u" }, { point: add(origin, v), color: COLORS[1], label: "v" });
    if (result && valid(add(origin, result))) {
      const name = document.operation === "SUM" ? "u + v" : document.operation === "DIFFERENCE" ? "u − v" : "projᵥ u";
      drawing.lines.push({ points: [origin, add(origin, result)], color: COLORS[2], arrow: true }); drawing.markers.push({ point: add(origin, result), color: COLORS[2], label: name });
      if (document.operation === "SUM") drawing.lines.push({ points: [add(origin, u), add(origin, result), add(origin, v)], color: "#91a1b5", dashed: true });
      if (document.operation === "PROJECTION") drawing.lines.push({ points: [add(origin, u), add(origin, result)], color: "#91a1b5", dashed: true });
      drawing.measurements.push({ label: name, value: `(${result.slice(0, count).map(format).join("; ")})` });
    } else if (!result) drawing.notices.push("Không thể chiếu lên vector v = 0.");
    drawing.measurements.push({ label: "Độ dài |u|", value: format(normU) }, { label: "Độ dài |v|", value: format(normV) }, { label: "Tích vô hướng u · v", value: format(product) }, { label: "Góc giữa u và v", value: normU > 1e-10 && normV > 1e-10 ? `${format(Math.acos(Math.max(-1, Math.min(1, product / (normU * normV)))) * 180 / Math.PI)}°` : "Chưa xác định (vector 0)" });
  } else {
    const fn = (x: number) => value(0, { x }), slope = numericalDerivative(fn, document.point), y = fn(document.point);
    sampleLine(drawing, (x) => [x, fn(x), 0], -domain, domain, COLORS[0], domain);
    if (document.showDerivative) sampleLine(drawing, (x) => [x, numericalDerivative(fn, x) ?? NaN, 0], -domain, domain, COLORS[2], domain);
    if (Number.isFinite(y) && Math.abs(y) <= 10000) drawing.markers.push({ point: [document.point, y, 0], color: COLORS[1], label: "A" });
    if (slope !== null) { sampleLine(drawing, (x) => [x, y + slope * (x - document.point), 0], -domain, domain, COLORS[1], domain, true); }
    else drawing.notices.push("Chưa xác định được đạo hàm tại điểm này: có thể là góc nhọn, điểm gián đoạn hoặc ngoài miền xác định.");
    const [a, b] = document.bounds, integral = numericalIntegral(fn, a, b), dx = (b - a) / document.rectangles; let sum = 0, good = true;
    if (integral) for (let i = 0; i < document.rectangles; i++) {
      const left = a + dx * i, right = left + dx, height = fn((left + right) / 2);
      if (!Number.isFinite(height) || Math.abs(height) > 10000) { good = false; break; }
      sum += height * dx;
      drawing.polygons.push({ points: [[left, 0, 0], [right, 0, 0], [right, height, 0], [left, height, 0]], color: height >= 0 ? "#27b59c" : "#ea7847" });
    }
    if (!integral || !good) { drawing.polygons = []; drawing.notices.push("Chưa tính được tích phân hữu hạn đáng tin cậy trong khoảng này. Kiểm tra miền xác định, điểm kỳ dị hoặc dao động quá nhanh; tích phân suy rộng chưa được hỗ trợ."); }
    drawing.measurements.push({ label: `f(${format(document.point)})`, value: format(y) }, { label: "Độ dốc tiếp tuyến f′(x₀) ≈", value: format(slope) }, { label: `∫ từ ${format(a)} đến ${format(b)} ≈`, value: integral && good ? format(integral.value) : "Chưa xác định" }, { label: `Tổng ${document.rectangles} hình chữ nhật ≈`, value: integral && good ? format(sum) : "Chưa xác định" });
    drawing.notices.push("Xanh ngọc: f(x); tím: đạo hàm gần đúng; cam nét đứt: tiếp tuyến. Hình chữ nhật dùng điểm giữa; miền trên/dưới trục có đóng góp trái dấu. Đổi thứ tự hai cận làm đổi dấu tích phân. Các kết quả là xấp xỉ số.");
  }
  if (!drawing.lines.length) drawing.notices.push("Chưa thấy hình hợp lệ trong miền này. Kiểm tra công thức, tham số và miền xác định.");
  return drawing;
}
