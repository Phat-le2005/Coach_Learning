import type { InkStroke } from "@/lib/api/contracts";

const PAGE_WIDTH = 794;
const PAGE_HEIGHT = 1123;

/** Rasterize only selected handwriting. The server never receives the whole ink document. */
export function renderInkRegionPng(strokes: InkStroke[]): string {
  const pens = strokes.filter((stroke) => stroke.tool === "PEN" && stroke.points.length > 0);
  if (!pens.length) throw new Error("Vùng này chưa có nét bút để nhận dạng.");
  const xs = pens.flatMap((stroke) => stroke.points.map((point) => point.x * PAGE_WIDTH));
  const ys = pens.flatMap((stroke) => stroke.points.map((point) => point.y * PAGE_HEIGHT));
  const left = Math.max(0, Math.min(...xs) - 32);
  const top = Math.max(0, Math.min(...ys) - 32);
  const width = Math.min(PAGE_WIDTH - left, Math.max(...xs) - left + 32);
  const height = Math.min(PAGE_HEIGHT - top, Math.max(...ys) - top + 32);
  const scale = Math.min(2, 1600 / width, 1600 / height);
  const canvas = document.createElement("canvas");
  canvas.width = Math.max(16, Math.ceil(width * scale));
  canvas.height = Math.max(16, Math.ceil(height * scale));
  const context = canvas.getContext("2d");
  if (!context) throw new Error("Trình duyệt không thể tạo ảnh vùng nét viết.");
  context.fillStyle = "#ffffff";
  context.fillRect(0, 0, canvas.width, canvas.height);
  context.lineCap = "round";
  context.lineJoin = "round";
  context.strokeStyle = "#172f29";
  context.fillStyle = "#172f29";
  for (const stroke of pens) {
    context.lineWidth = Math.max(2, Math.min(12, stroke.width * 1.5)) * scale;
    context.beginPath();
    stroke.points.forEach((point, index) => {
      const x = (point.x * PAGE_WIDTH - left) * scale;
      const y = (point.y * PAGE_HEIGHT - top) * scale;
      if (index === 0) context.moveTo(x, y);
      else context.lineTo(x, y);
    });
    if (stroke.points.length === 1) {
      const point = stroke.points[0];
      context.beginPath();
      context.arc((point.x * PAGE_WIDTH - left) * scale,
        (point.y * PAGE_HEIGHT - top) * scale, Math.max(1, context.lineWidth / 2), 0, 2 * Math.PI);
      context.fill();
    } else context.stroke();
  }
  const dataUrl = canvas.toDataURL("image/png");
  if (!dataUrl.startsWith("data:image/png;base64,")) throw new Error("Không tạo được ảnh PNG.");
  const encoded = dataUrl.slice("data:image/png;base64,".length);
  if (encoded.length > 2_800_000) throw new Error("Vùng nét viết quá lớn. Hãy chọn ít vùng hơn.");
  return encoded;
}
