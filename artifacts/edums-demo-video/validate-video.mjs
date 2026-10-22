import crypto from "node:crypto";
import fs from "node:fs";

const port = process.argv[2] || "9224";
const fileName = process.argv[3] || "EduMS_Demo_6_phut.mp4";
const videoPath = `D:/CoachLearning/artifacts/edums-demo-video/output/${fileName}`;
const framePath = "D:/CoachLearning/artifacts/edums-demo-video/prototype/final-video-frame-170s.png";
const videoUrl = `http://127.0.0.1:8765/output/${fileName}`;

const tabs = await fetch(`http://127.0.0.1:${port}/json`).then((response) => response.json());
const target = tabs.find((tab) => tab.type === "page");
if (!target) throw new Error("No Chrome page target was found.");

const socket = new WebSocket(target.webSocketDebuggerUrl);
await new Promise((resolve, reject) => {
  socket.addEventListener("open", resolve, { once: true });
  socket.addEventListener("error", reject, { once: true });
});

let id = 0;
const pending = new Map();
socket.addEventListener("message", (event) => {
  const message = JSON.parse(event.data);
  if (!message.id || !pending.has(message.id)) return;
  const callbacks = pending.get(message.id);
  pending.delete(message.id);
  if (message.error) callbacks.reject(new Error(message.error.message));
  else callbacks.resolve(message.result);
});

function send(method, params = {}) {
  const messageId = ++id;
  socket.send(JSON.stringify({ id: messageId, method, params }));
  return new Promise((resolve, reject) => pending.set(messageId, { resolve, reject }));
}

await send("Page.enable");
await send("Page.navigate", { url: "http://127.0.0.1:8765/renderer.html" });
await new Promise((resolve) => setTimeout(resolve, 1000));
const metadata = await send("Runtime.evaluate", {
  expression: `new Promise((resolve, reject) => {
    document.body.innerHTML = '<video id="validationVideo" muted preload="auto" style="position:fixed;inset:0;width:100vw;height:100vh;background:#082e27;object-fit:contain"></video>';
    const video = document.querySelector('#validationVideo');
    video.onloadedmetadata = () => {
      video.onseeked = () => resolve({duration: video.duration, width: video.videoWidth, height: video.videoHeight, seekedTo: video.currentTime});
      video.currentTime = Math.min(170, Math.max(0, video.duration - 1));
    };
    video.onerror = () => reject(new Error('Video element failed to load: ' + (video.error?.message || 'unknown error')));
    video.src = ${JSON.stringify(videoUrl)};
  })`,
  awaitPromise: true,
  returnByValue: true,
});

const screenshot = await send("Page.captureScreenshot", { format: "png", fromSurface: true });
fs.writeFileSync(framePath, Buffer.from(screenshot.data, "base64"));
const hash = crypto.createHash("sha256").update(fs.readFileSync(videoPath)).digest("hex");
console.log(JSON.stringify({
  ...metadata.result?.value,
  bytes: fs.statSync(videoPath).size,
  sha256: hash,
  framePath,
}, null, 2));
socket.close();
