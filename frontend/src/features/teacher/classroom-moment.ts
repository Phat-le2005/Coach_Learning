import type { classMomentSummary } from "./classroom-personalization";
import { MAM_STICKER_SVG } from "./components/MamMascot";

export type MomentFormat = "post" | "story";
export type MomentSummary = ReturnType<typeof classMomentSummary>;

function loadImage(source: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => { const img = new Image(); img.onload = () => resolve(img); img.onerror = () => reject(new Error("Không tải được ảnh lớp học.")); img.src = source; });
}

function fillRound(context: CanvasRenderingContext2D, x: number, y: number, width: number, height: number, radius: number, fill: string | CanvasGradient) {
  context.beginPath(); context.roundRect(x, y, width, height, radius); context.fillStyle = fill; context.fill();
}

function fitText(context: CanvasRenderingContext2D, text: string, width: number) {
  let result = text;
  while (context.measureText(result).width > width && result.length > 1) result = result.slice(0, -1);
  return result === text ? result : `${result.trimEnd()}…`;
}

/** The export receives only aggregate counts and a name-free WebGL snapshot. */
export async function renderClassroomMoment(snapshot: string | null, summary: MomentSummary, format: MomentFormat) {
  const canvas = document.createElement("canvas");
  canvas.width = 1080; canvas.height = format === "story" ? 1920 : 1350;
  const context = canvas.getContext("2d");
  if (!context) throw new Error("Thiết bị chưa hỗ trợ tạo ảnh chia sẻ.");
  const height = canvas.height;
  const background = context.createLinearGradient(0, 0, 1080, height);
  background.addColorStop(0, "#e4f4e9"); background.addColorStop(.55, "#fff9eb"); background.addColorStop(1, "#eae3f6");
  context.fillStyle = background; context.fillRect(0, 0, 1080, height);
  context.fillStyle = "#d4e8d6"; context.beginPath(); context.arc(1010, 85, 195, 0, Math.PI * 2); context.fill();
  context.fillStyle = "#eee3ce"; context.beginPath(); context.arc(-30, height - 170, 170, 0, Math.PI * 2); context.fill();
  context.textAlign = "left"; context.fillStyle = "#537965"; context.font = "600 26px Segoe UI, Arial";
  context.fillText("LỚP MÌNH  /  COZY CAMPUS", 64, 73);
  context.fillStyle = "#204c3c"; context.font = "700 67px Segoe UI, Arial"; context.fillText(summary.title, 60, 166);
  context.font = "400 29px Segoe UI, Arial"; context.fillStyle = "#647c6b";
  context.fillText(fitText(context, summary.classroom, 920), 64, 218);

  const photo = { x: 48, y: 262, width: 984, height: format === "story" ? 1050 : 635 };
  fillRound(context, photo.x, photo.y, photo.width, photo.height, 38, "#eff5e8");
  context.save(); context.beginPath(); context.roundRect(photo.x, photo.y, photo.width, photo.height, 38); context.clip();
  let scene: HTMLImageElement | null = null;
  if (snapshot) { try { scene = await loadImage(snapshot); } catch { /* A name-free illustration remains available without WebGL. */ } }
  if (scene) {
    const scale = Math.max(photo.width / scene.width, photo.height / scene.height);
    const w = scene.width * scale, h = scene.height * scale;
    context.drawImage(scene, photo.x + (photo.width - w) / 2, photo.y + (photo.height - h) / 2, w, h);
  } else {
    context.fillStyle = "#dce8d2"; context.fillRect(photo.x, photo.y, photo.width, photo.height);
    for (let index = 9; index >= 0; index--) {
      const row = Math.floor(index / 2), scale = 1 - row * .11;
      const x = 540 + (index % 2 ? 1 : -1) * (170 - row * 15);
      const y = photo.y + photo.height - 100 - row * (photo.height - 180) / 5;
      fillRound(context, x - 94 * scale, y + 22, 188 * scale, 70 * scale, 14, "#e8cda3");
      context.fillStyle = "#f3c8a5"; context.beginPath(); context.arc(x, y, 40 * scale, 0, Math.PI * 2); context.fill();
      context.fillStyle = "#594137"; context.beginPath(); context.arc(x, y - 10 * scale, 41 * scale, Math.PI, Math.PI * 2); context.fill();
      for (const dx of [-12, 12]) { context.beginPath(); context.arc(x + dx * scale, y + 2 * scale, 3 * scale, 0, Math.PI * 2); context.fill(); }
    }
    context.fillStyle = "#486e56"; context.font = "500 22px Segoe UI, Arial"; context.fillText("ẢNH LỚP MINH HỌA", 80, photo.y + 52);
  }
  context.restore();

  const metaY = photo.y + photo.height + 36;
  fillRound(context, 64, metaY, 660, 120, 28, "#ffffff");
  context.fillStyle = "#28644a"; context.font = "700 47px Segoe UI, Arial"; context.fillText(summary.hasProgress ? `${summary.completed}/${summary.total}` : `${summary.total} bạn học`, 94, metaY + 54);
  context.fillStyle = "#637b6a"; context.font = "400 24px Segoe UI, Arial"; context.fillText(summary.hasProgress ? "bạn đã hoàn thành toàn bộ bài tập" : "Chưa có dữ liệu hoàn thành bài tập", 94, metaY + 92);
  const mascot = await loadImage(`data:image/svg+xml;charset=utf-8,${encodeURIComponent(MAM_STICKER_SVG)}`);
  context.drawImage(mascot, 785, metaY - 12, 200, 200);
  context.fillStyle = "#244b39"; context.font = "600 29px Segoe UI, Arial";
  context.fillText(summary.goalReached ? "Một tràng vỗ tay cho lớp mình!" : "Mỗi ngày một chút.", 64, metaY + 185);
  if (!summary.goalReached) context.fillText("Cùng nhau đi xa hơn.", 64, metaY + 229);
  context.fillStyle = "#758777"; context.font = "400 22px Segoe UI, Arial";
  const date = new Intl.DateTimeFormat("vi-VN", { timeZone: "Asia/Ho_Chi_Minh", dateStyle: "medium" }).format(new Date());
  context.fillText(`${date}   ·   #LopMinhHomNay`, 64, height - 43);
  context.textAlign = "right"; context.font = "600 22px Segoe UI, Arial"; context.fillText(summary.isDemo ? "EduMS · Lớp minh họa" : "EduMS", 1015, height - 43);
  const blob = await new Promise<Blob>((resolve, reject) => canvas.toBlob((value) => value ? resolve(value) : reject(new Error("Không tạo được ảnh PNG.")), "image/png"));
  return { blob, dataUrl: canvas.toDataURL("image/png"), width: canvas.width, height: canvas.height };
}

export async function renderMamSticker(): Promise<Blob> {
  const canvas = document.createElement("canvas"); canvas.width = 512; canvas.height = 512;
  const context = canvas.getContext("2d");
  if (!context) throw new Error("Thiết bị chưa hỗ trợ tạo sticker.");
  const mascot = await loadImage(`data:image/svg+xml;charset=utf-8,${encodeURIComponent(MAM_STICKER_SVG)}`);
  context.drawImage(mascot, 0, 0, 512, 512);
  return new Promise<Blob>((resolve, reject) => canvas.toBlob((value) => value ? resolve(value) : reject(new Error("Không tạo được sticker PNG.")), "image/png"));
}
