import fs from "node:fs";

const outputDir = "D:/CoachLearning/artifacts/edums-demo-video/output";
fs.mkdirSync(outputDir, { recursive: true });

const tabs = await fetch("http://127.0.0.1:9224/json").then((response) => response.json());
const target = tabs.find((tab) => tab.type === "page");
if (!target) throw new Error("No Chrome renderer page target was found.");

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

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

await send("Page.enable");
const renderUrl = process.argv[2] || "http://127.0.0.1:8765/renderer.html?autostart=1";
await send("Page.navigate", { url: renderUrl });

let finished = false;
for (let elapsed = 0; elapsed < 390; elapsed += 5) {
  await sleep(5000);
  const result = await send("Runtime.evaluate", { expression: "document.title", returnByValue: true });
  const title = String(result.result?.value || "");
  if (elapsed % 30 === 0) console.log(`render_progress_seconds=${elapsed}`);
  if (title.startsWith("DONE:")) {
    console.log(title);
    finished = true;
    break;
  }
}

if (!finished) throw new Error("Video render did not finish within the expected time.");

const metaResult = await send("Runtime.evaluate", {
  expression: "window.__videoMeta",
  returnByValue: true,
});
const meta = metaResult.result?.value;
if (!meta?.name || !Number.isFinite(meta.size) || meta.size <= 0) {
  throw new Error("Renderer did not expose a valid recorded video blob.");
}

const outputPath = `${outputDir}/${meta.name}`;
const partialPath = `${outputPath}.part`;
fs.writeFileSync(partialPath, "");
const chunkSize = 1024 * 1024;
let written = 0;
for (let start = 0; start < meta.size; start += chunkSize) {
  const end = Math.min(start + chunkSize, meta.size);
  const chunkResult = await send("Runtime.evaluate", {
    expression: `new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(String(reader.result).split(',', 2)[1]);
      reader.onerror = () => reject(reader.error);
      reader.readAsDataURL(window.__videoBlob.slice(${start}, ${end}));
    })`,
    awaitPromise: true,
    returnByValue: true,
  });
  const encoded = chunkResult.result?.value;
  if (typeof encoded !== "string") throw new Error(`Failed to read video chunk at ${start}.`);
  const bytes = Buffer.from(encoded, "base64");
  fs.appendFileSync(partialPath, bytes);
  written += bytes.length;
  if (written === meta.size || written % (20 * 1024 * 1024) < chunkSize) {
    console.log(`extract_progress_bytes=${written}/${meta.size}`);
  }
}

if (written !== meta.size) throw new Error(`Extracted ${written} bytes; expected ${meta.size}.`);
fs.renameSync(partialPath, outputPath);
console.log(`OUTPUT:${outputPath}:${written}:${meta.mimeType}`);
socket.close();
