const port = process.argv[2] || "9225";
const tabs = await fetch(`http://127.0.0.1:${port}/json`).then((response) => response.json());
const target = tabs.find((tab) => tab.type === "page");
const socket = new WebSocket(target.webSocketDebuggerUrl);
await new Promise((resolve, reject) => {
  socket.addEventListener("open", resolve, { once: true });
  socket.addEventListener("error", reject, { once: true });
});
let id = 0;
const pending = new Map();
socket.addEventListener("message", (event) => {
  const message = JSON.parse(event.data);
  if (message.method === "Runtime.exceptionThrown") {
    console.error(JSON.stringify(message.params.exceptionDetails, null, 2));
  }
  if (!message.id || !pending.has(message.id)) return;
  pending.get(message.id)(message.result);
  pending.delete(message.id);
});
const send = (method, params = {}) => {
  const messageId = ++id;
  socket.send(JSON.stringify({ id: messageId, method, params }));
  return new Promise((resolve) => pending.set(messageId, resolve));
};
await send("Runtime.enable");
await send("Page.navigate", { url: "http://127.0.0.1:8765/renderer.html" });
await new Promise((resolve) => setTimeout(resolve, 3000));
const result = await send("Runtime.evaluate", {
  expression: "({title:document.title,status:document.querySelector('#status')?.textContent,pixel:[...document.querySelector('canvas').getContext('2d').getImageData(960,540,1,1).data]})",
  returnByValue: true,
});
console.log(JSON.stringify(result.result?.value));
socket.close();
