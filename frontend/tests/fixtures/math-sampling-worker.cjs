// Node adapter for exercising the actual browser worker entry in a separate thread.
const { parentPort, workerData } = require("node:worker_threads");
globalThis.self = { onmessage: null, postMessage: (message, transfer) => parentPort.postMessage(message, transfer) };
parentPort.on("message", (data) => globalThis.self.onmessage({ data }));
require(workerData.entry);
