import fs from "node:fs";
import path from "node:path";

const root = "D:/CoachLearning";
const outputDir = path.join(root, "artifacts/edums-demo-video/captures");
const envPath = path.join(root, "backend/.env");

function readEnv(name) {
  const text = fs.readFileSync(envPath, "utf8");
  const line = text.split(/\r?\n/).find((item) => item.trim().startsWith(`${name}=`));
  if (!line) throw new Error(`${name} is not configured in backend/.env`);
  return line.slice(line.indexOf("=") + 1).trim().replace(/^['"]|['"]$/g, "");
}

const password = readEnv("SEED_DEMO_PASSWORD");
if (!password) throw new Error("SEED_DEMO_PASSWORD is empty in backend/.env");

const tabs = await fetch("http://127.0.0.1:9223/json").then((response) => response.json());
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
  const { resolve, reject } = pending.get(message.id);
  pending.delete(message.id);
  if (message.error) reject(new Error(message.error.message));
  else resolve(message.result);
});

function send(method, params = {}) {
  const messageId = ++id;
  socket.send(JSON.stringify({ id: messageId, method, params }));
  return new Promise((resolve, reject) => pending.set(messageId, { resolve, reject }));
}

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

async function navigate(url, settleMs = 4500) {
  await send("Page.navigate", { url });
  await sleep(settleMs);
}

async function evaluate(expression) {
  const result = await send("Runtime.evaluate", {
    expression,
    awaitPromise: true,
    returnByValue: true,
  });
  return result.result?.value;
}

async function screenshot(fileName) {
  const result = await send("Page.captureScreenshot", {
    format: "png",
    captureBeyondViewport: false,
  });
  fs.writeFileSync(path.join(outputDir, fileName), Buffer.from(result.data, "base64"));
}

await send("Page.enable");
await send("Runtime.enable");
await send("Emulation.setDeviceMetricsOverride", {
  width: 1920,
  height: 1080,
  deviceScaleFactor: 1,
  mobile: false,
});

await navigate("http://localhost:3000/login", 2500);
await evaluate(`(() => {
  const setValue = (input, value) => {
    const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set;
    setter.call(input, value);
    input.dispatchEvent(new Event("input", { bubbles: true }));
    input.dispatchEvent(new Event("change", { bubbles: true }));
  };
  const email = document.querySelector('input[type="email"]');
  const password = document.querySelector('input[type="password"]');
  if (!email || !password) throw new Error("Login form inputs were not found.");
  setValue(email, "student01.demo@example.com");
  setValue(password, ${JSON.stringify(password)});
  document.querySelector('button[type="submit"]')?.click();
  return true;
})()`);
await sleep(5000);

const currentUrl = await evaluate("location.href");
if (!String(currentUrl).includes("/student")) {
  throw new Error(`Student login did not complete. Current URL: ${currentUrl}`);
}

await navigate("http://localhost:3000/student", 6000);
await screenshot("student-home.png");

await navigate("http://localhost:3000/student/knowledge", 9000);
await screenshot("knowledge-galaxy.png");

await evaluate(`(() => {
  const buttons = [...document.querySelectorAll("button")];
  const target = buttons.find((button) => /cây cổ thụ/i.test(button.textContent || ""));
  if (target) target.click();
  return Boolean(target);
})()`);
await sleep(2500);
await screenshot("knowledge-tree.png");

socket.close();
console.log("Captured authenticated EduMS screens without exposing credentials.");
