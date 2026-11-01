import { sampleGraph, type GraphSettings, type MathExpression, type MathNode } from "./expression";

export type GraphRenderMode = "CURVE_2D" | "CURVE_3D" | "EXTRUDED_3D" | "SURFACE_3D" | "SLICE_2D"
  | "CONTOUR_2D" | "CONTOUR_3D" | "LEVEL_SURFACE_3D" | "LEVEL_SLICE_2D";

/** Render f(x)=y as the same curve as y=f(x), without rewriting the saved relation.
 * A contour grid clips both coordinates to ±domain and can otherwise omit the vertex.
 */
export function resolveGraphExpression(model: MathExpression): MathExpression {
  if (model.kind !== "implicit" || model.dimension !== "2D" || model.node.kind !== "binary" || model.node.op !== "-") return model;
  const { left, right } = model.node;
  if (right.kind !== "variable" || right.name !== "y") return model;
  const dependsOnOtherCoordinate = (node: MathNode): boolean => {
    if (node.kind === "variable") return node.name === "y" || node.name === "z";
    if (node.kind === "binary") return dependsOnOtherCoordinate(node.left) || dependsOnOtherCoordinate(node.right);
    if (node.kind === "guard") return dependsOnOtherCoordinate(node.argument) || dependsOnOtherCoordinate(node.node);
    return node.kind === "unary" || node.kind === "call" ? dependsOnOtherCoordinate(node.node) : false;
  };
  if (dependsOnOtherCoordinate(left)) return model;
  return { ...model, kind: "explicit", expression: `y=${model.expression.split("=")[0]}`, node: left };
}

/** A camera choice must never reclassify or rewrite the mathematical expression. */
export function resolveGraphView(model: MathExpression, settings: GraphSettings): GraphRenderMode {
  model = resolveGraphExpression(model);
  if (model.kind === "implicit") return model.dimension === "3D"
    ? settings.view_mode === "2D" ? "LEVEL_SLICE_2D" : "LEVEL_SURFACE_3D"
    : settings.view_mode === "3D" ? "CONTOUR_3D" : "CONTOUR_2D";
  if (model.dimension === "3D") return settings.view_mode === "2D" ? "SLICE_2D" : "SURFACE_3D";
  if (settings.view_mode === "EXTRUDED") return "EXTRUDED_3D";
  return settings.view_mode === "3D" ? "CURVE_3D" : "CURVE_2D";
}

export function isSpatialView(mode: GraphRenderMode): boolean {
  return ["CURVE_3D", "EXTRUDED_3D", "SURFACE_3D", "CONTOUR_3D", "LEVEL_SURFACE_3D"].includes(mode);
}

export function describeGraphView(model: MathExpression, settings: GraphSettings): string {
  switch (resolveGraphView(model, settings)) {
    case "CONTOUR_2D": return "Đường mức 2D · F(x,y) = 0";
    case "CONTOUR_3D": return "Đường mức trong không gian 3D · F(x,y) = 0, z = 0";
    case "LEVEL_SURFACE_3D": return "Mặt mức 3D · F(x,y,z) = 0";
    case "LEVEL_SLICE_2D": return `Giao tuyến 2D · F(x,y₀,z) = 0, y₀ = ${settings.slice_y ?? 0}`;
    case "CURVE_2D": return "Đường cong 2D · y = F(x)";
    case "CURVE_3D": return "Đường cong trong không gian 3D · y = F(x), z = 0";
    case "EXTRUDED_3D": return "Bề mặt kéo dài · y = F(x), z thay đổi tự do";
    case "SLICE_2D": return `Mặt cắt 2D · z = F(x, y₀), y₀ = ${settings.slice_y ?? 0}`;
    default: return "Bề mặt 3D · z = F(x, y)";
  }
}

export function recommendGraph(model: MathExpression): { title: string; reason: string } {
  model = resolveGraphExpression(model);
  if (model.kind === "implicit") return model.dimension === "3D"
    ? { title: "Đề xuất mặt mức 3D", reason: "Phương trình liên hệ các tọa độ trong không gian. Xoay để quan sát hình dạng, hoặc xem giao tuyến tại y cố định." }
    : { title: "Đề xuất đường mức 2D", reason: "Phương trình liên hệ x và y. Đường vẽ biểu diễn các điểm thỏa mãn cả hai vế." };
  return model.dimension === "3D"
    ? { title: "Đề xuất bề mặt 3D", reason: "Mỗi cặp (x, y) cho một độ cao z. Đổi tham số để quan sát độ cong và hướng của bề mặt." }
    : { title: "Đề xuất đồ thị 2D", reason: "Mỗi giá trị x cho một giá trị y. Quan sát độ dốc và hình dạng khi thay đổi tham số." };
}

/** World Y is the displayed height; the label specifies whether this is mathematical y or z. */
export function sampleViewPoint(model: MathExpression, settings: GraphSettings, x: number, second = 0): [number, number, number] {
  model = resolveGraphExpression(model);
  const mode = resolveGraphView(model, settings);
  const inputY = mode === "SLICE_2D" ? settings.slice_y ?? 0 : second;
  const value = sampleGraph(model, settings, x, inputY);
  return [x, value, mode === "SURFACE_3D" || mode === "EXTRUDED_3D" ? second : 0];
}
