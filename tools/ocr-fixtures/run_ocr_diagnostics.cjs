#!/usr/bin/env node
"use strict";
// Bounded diagnostic runner: real Next.js + real browser CoMER; no backend/account.
const fs = require("node:fs"), path = require("node:path"), net = require("node:net");
const { spawn, execFileSync } = require("node:child_process");
const { createHash } = require("node:crypto");
const assert = require("node:assert/strict");
const root = path.resolve(__dirname, "../..");
const args = process.argv.slice(2);
const option = (name, fallback) => { const i = args.indexOf(name); return i < 0 ? fallback : args[i + 1]; };
const input = path.resolve(args[0] && !args[0].startsWith("--") ? args[0] : path.join(root, ".tmp/tri-ocr-native/integral_case_01.json"));
const annotationPath = option("--annotation", null);
const output = path.resolve(option("--output", path.join(root, ".tmp/tri-ocr-diagnostics")));
const profile = option("--profile", "both");
const sha = (bytes) => createHash("sha256").update(bytes).digest("hex");
const write = (name, value) => fs.writeFileSync(path.join(output, name), JSON.stringify(value, null, 2));
const read = (file) => fs.readFileSync(file);
const build = path.join(root, "frontend/.test-build-run/src/features/math-workspace/utils");
const { chromium, expect } = require(path.join(root, "frontend/node_modules/@playwright/test"));
let server, browser, page;
async function freePort(port) {
  await new Promise((resolve, reject) => { const s = net.createServer(); s.once("error", () => reject(new Error(`QA_PORT_IN_USE: ${port}`))); s.listen(port, () => s.close(resolve)); });
}
async function main() {
  if (!fs.existsSync(input)) { fs.mkdirSync(output, { recursive: true }); write("summary.json", { status: "BLOCKED_MISSING_REAL_INK", input }); return; }
  // Keep captures and annotations immutable, including when the caller chooses an output path.
  for (const file of [input, annotationPath && path.resolve(annotationPath)].filter(Boolean)) {
    if (path.dirname(file) === output && ["manifest.json", "results.json", "annotation-template.json", "summary.json", "REPORT.md"].includes(path.basename(file))) throw new Error("OUTPUT_WOULD_OVERWRITE_INPUT");
  }
  fs.mkdirSync(path.join(output, "preprocessing"), { recursive: true });
  // Reuse the existing compilation target; never validate with stale compiled helpers.
  execFileSync(process.execPath, [path.join(root, "frontend/node_modules/typescript/bin/tsc"), "-p", "tsconfig.test.json", "--outDir", ".test-build-run"],
    { cwd: path.join(root, "frontend"), stdio: "inherit" });
  const { validateOcrEvalCapture } = require(path.join(build, "ocr-eval-replay.js"));
  const { annotationTemplate, validateRecognitionAnnotation } = require(path.join(build, "ocr-scope-diagnostics.js"));
  const captureBytes = read(input), capture = validateOcrEvalCapture(JSON.parse(captureBytes));
  const captureHash = sha(captureBytes);
  const annotationBytes = annotationPath ? read(path.resolve(annotationPath)) : null;
  const annotation = annotationBytes ? validateRecognitionAnnotation(JSON.parse(annotationBytes), capture, captureHash) : null;
  write("annotation-template.json", annotationTemplate(captureHash, path.basename(input)));
  const sources = [
    "frontend/src/features/math-workspace/utils/handwritten-ocr.ts", "frontend/src/features/math-workspace/utils/page-ocr.ts",
    "frontend/src/features/math-workspace/utils/structural-candidate-engine.ts", "frontend/src/features/math-workspace/utils/expression-reconstruction.ts",
    "frontend/src/features/math-workspace/utils/structured-transcription-ir.ts", "frontend/src/features/math-workspace/utils/ocr-model-diagnostics.ts",
    "frontend/src/features/math-workspace/utils/ocr-eval-replay.ts", "frontend/src/app/ocr-diagnostics/page.tsx", "frontend/src/proxy.ts", "frontend/package.json",
    "frontend/src/features/math-workspace/utils/ocr-scope-diagnostics.ts", "frontend/src/features/math-workspace/components/OcrDiagnosticsWorkbench.tsx",
    "tools/ocr-fixtures/run_ocr_diagnostics.cjs",
  ];
  const model = path.join(root, "frontend/public/ocr/comer/v0_1");
  const runtimeFile = "frontend/public/ocr/ink-on/chunks/inference-4T2UM6yg.js";
  const runtimeText = read(path.join(root, runtimeFile)).toString();
  assert.match(runtimeText, /const DEFAULT_MAX_STEPS = 50;/);
  assert.match(runtimeText, /const REPEAT_LIMIT = 3;/);
  const manifest = { schemaVersion: "ocr-diagnostics/1", date: new Date().toISOString(), gitSha: execFileSync("git", ["rev-parse", "HEAD"], { cwd: root, encoding: "utf8" }).trim(),
    branch: execFileSync("git", ["branch", "--show-current"], { cwd: root, encoding: "utf8" }).trim(),
    workingTree: execFileSync("git", ["status", "--short"], { cwd: root, encoding: "utf8" }).trim(),
    sourceHashes: Object.fromEntries(sources.map((file) => [file, sha(read(path.join(root, file)))])),
    capture: { file: input, sha256: captureHash, sourceKind: capture.sourceKind, provenance: "existing local MathCanvas capture; human-writing provenance not independently audited by this runner" },
    annotation: { file: annotationPath, sha256: annotationBytes ? sha(annotationBytes) : null, status: annotation?.annotationStatus ?? "MISSING", independentHumanGroundTruth: annotation?.annotationStatus === "HUMAN_VERIFIED" ? "DECLARED_BY_ANNOTATOR" : "MISSING" },
    modelIdentifier: "CoMER/v0_1/INT8", modelHashes: { encoder: sha(read(path.join(model, "encoder_int8.onnx"))), decoder: sha(read(path.join(model, "decoder_int8.onnx"))),
      vocab: sha(read(path.join(model, "vocab.json"))), runtime: sha(read(path.join(root, runtimeFile))) },
    configuration: { mode: "expression", beamWidth: 3, maxDecodeSteps: 50, repeatLimit: 3, executionProvider: "wasm", autoProfile: profile, e2Requested: args.includes("--e2") },
    privacy: "local files and local model assets only; no account or API mutation", node: process.version };
  write("manifest.json", manifest);
  await freePort(3004);
  const fd = fs.openSync(path.join(output, "next.log"), "w");
  server = spawn(process.execPath, [path.join(root, "frontend/node_modules/next/dist/bin/next"), "dev", "--hostname", "localhost", "--port", "3004"],
    { cwd: path.join(root, "frontend"), env: { ...process.env, NEXT_DIST_DIR: ".next-build" }, windowsHide: true, stdio: ["ignore", fd, fd] }); fs.closeSync(fd);
  const base = "http://localhost:3004";
  let ready = false;
  for (let i = 0; i < 90; i++) {
    if (server.exitCode !== null) throw new Error("QA_NEXT_SERVER_EXITED");
    try { ready = (await fetch(`${base}/ocr-diagnostics`, { signal: AbortSignal.timeout(3000) })).ok; } catch {}
    if (ready) break; await new Promise((resolve) => setTimeout(resolve, 500));
  }
  if (!ready) throw new Error("QA_NEXT_SERVER_NOT_READY");
  browser = await chromium.launch({ channel: "chrome", headless: true });
  page = await browser.newPage({ viewport: { width: 1440, height: 1000 }, acceptDownloads: true });
  const mutations = [], errors = [];
  page.on("request", (r) => { if (["POST", "PUT", "PATCH", "DELETE"].includes(r.method())) mutations.push({ method: r.method(), origin: new URL(r.url()).origin, path: new URL(r.url()).pathname }); });
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto(`${base}/ocr-diagnostics`);
  await page.getByLabel("Capture JSON", { exact: true }).setInputFiles(input);
  await expect(page.getByTestId("ocr-diagnostics-workbench")).toHaveAttribute("data-capture-sha256", captureHash);
  await expect(page.getByTestId("ocr-diagnostics-workbench")).toHaveAttribute("aria-busy", "false");
  await expect(page.getByText(`${capture.strokes.length} nét`, { exact: false }).first()).toBeVisible();
  // Exercise source selection with no invented label or human verification.
  if (capture.strokes.some((s) => s.tool === "PEN" && s.points.length)) {
    const first = page.getByRole("button", { name: "Chọn nét 1", exact: true });
    await first.press("Enter"); await expect(first).toHaveAttribute("aria-pressed", "true");
    await page.getByRole("button", { name: "Thêm nhóm nhãn", exact: true }).click();
    await page.getByRole("button", { name: "Bỏ nhóm group-1", exact: true }).click();
  }
  if (annotationPath) {
    await page.getByLabel("Annotation JSON", { exact: true }).setInputFiles(path.resolve(annotationPath));
    await expect(page.getByTestId("ocr-diagnostics-workbench")).toHaveAttribute("data-annotation-sha256", sha(annotationBytes));
    await expect(page.getByTestId("ocr-diagnostics-workbench")).toHaveAttribute("aria-busy", "false");
    await expect(page.getByTestId("ocr-diagnostics-workbench").getByRole("alert")).toHaveCount(0);
  }
  await page.getByLabel("Auto profile").selectOption(profile);
  if (args.includes("--e2")) await page.getByLabel("E2 width variants").check();
  await page.screenshot({ path: path.join(output, "annotation-view.png") });
  await page.getByTestId("run-diagnostics").click();
  await expect(page.getByTestId("run-diagnostics")).toBeEnabled({ timeout: 180000 });
  await expect(page.getByTestId("diagnostics-results")).toBeVisible();
  // Verify the original, unchanged student wrapper on the identical scopes/model/default preprocessing.
  await page.getByTestId("check-legacy-parity").click();
  await expect(page.getByTestId("check-legacy-parity")).toBeEnabled({ timeout: 180000 });
  // Exporting another draft must not rewrite the identity of the annotation used for this run.
  const draftDownload = page.waitForEvent("download");
  await page.getByRole("button", { name: "Tải annotation draft", exact: true }).click();
  await (await draftDownload).saveAs(path.join(output, "annotation-draft-after-run.json"));
  const pending = page.waitForEvent("download"); await page.getByTestId("export-diagnostics").click();
  await (await pending).saveAs(path.join(output, "results.json"));
  const results = JSON.parse(read(path.join(output, "results.json")));
  assert.equal(results.captureSha256, captureHash);
  assert.equal(results.annotationSha256, annotationBytes ? sha(annotationBytes) : null);
  for (const r of results.runs.filter((r) => r.diagnostic.status === "COMPLETED" || r.diagnostic.status === "ABSTAIN_NOT_MEANINGFUL")) assert.deepEqual(r.diagnostic.modelHashes, manifest.modelHashes);
  assert.ok(results.legacyParity.every((p) => p.equal), "diagnostic adapter changed selected legacy output");
  write("browser_network.json", { mutations, pageErrors: errors });
  const isDevTool = (r) => r.origin === base && r.path.startsWith("/__nextjs");
  const devToolRequests = mutations.filter(isDevTool);
  const applicationMutations = mutations.filter((r) => !isDevTool(r));
  assert.equal(applicationMutations.length, 0, JSON.stringify(applicationMutations));
  assert.equal(errors.length, 0, JSON.stringify(errors)); assert.equal(sha(read(input)), captureHash);
  if (annotationBytes) assert.equal(sha(read(path.resolve(annotationPath))), sha(annotationBytes));
  const inferenceErrors = results.runs.filter((r) => r.diagnostic.status === "ERROR");
  assert.equal(inferenceErrors.length, 0, JSON.stringify(inferenceErrors));
  const seenTensors = new Map();
  for (const r of results.runs.filter((r) => r.diagnostic.status === "COMPLETED")) {
    const key = [...r.scope.strokeIds].sort().join("|");
    const signature = { config: r.diagnostic.config, modelHashes: r.diagnostic.modelHashes,
      tensor: r.diagnostic.preprocessing.tensorSha256, mask: r.diagnostic.preprocessing.maskSha256 };
    if (seenTensors.has(key)) assert.deepEqual(signature, seenTensors.get(key), "same scope must have identical model/config/preprocessing across arms");
    seenTensors.set(key, signature);
  }
  const savePreview = (d, filename) => { if (d.status === "COMPLETED") fs.writeFileSync(path.join(output, "preprocessing", filename), Buffer.from(d.preprocessing.previewPng.split(",")[1], "base64")); };
  results.runs.forEach((r, i) => savePreview(r.diagnostic, `scope-${i}-default.png`));
  results.sensitivity.forEach((r, i) => savePreview(r.diagnostic, `variant-${i}-${r.variant}.png`));
  const selected = results.runs.filter((r) => r.diagnostic.status === "COMPLETED");
  const summary = { status: results.status, realSamples: results.summary.sourcePenStrokeCount ? 1 : 0, writerCount: results.writerId === "NOT_AVAILABLE" ? "NOT_AVAILABLE" : 1,
    ...results.summary, autoProfiles: results.profiles, sourceInputUnchanged: true, apiMutations: applicationMutations, devToolRequests, pageErrors: errors,
    legacyParityInferenceCalls: results.legacyParity.length,
    totalModelInvocationsIncludingParity: results.summary.inferenceCalls + results.legacyParity.length,
    selectedLegacyOutputParity: results.legacyParity, completedScopeCount: selected.length,
    postprocessingChangedCandidateCount: selected.reduce((n, r) => n + (Array.isArray(r.diagnostic.candidates) ? r.diagnostic.candidates.filter((b) => b.postprocessingChangedTokens).length : 0), 0),
    runtimeInferenceMs: selected.map((r) => ({ id: r.scope.id, profile: r.scope.profile, ...r.diagnostic.timings })),
    hypothesisConclusion: results.summary.labeledMathScopes ? "inspect per-scope comparison; limited to supplied human labels" : "H1/H2 unresolved without independent human scope and transcription; H3 observable but no ground-truth effect attributable",
    runtimeStopReason: "NOT_AVAILABLE; vendor drops per-beam termination reason", confidence: "NOT_AVAILABLE", e2DefaultChanged: false };
  write("summary.json", summary);
  await page.screenshot({ path: path.join(output, "diagnostics-view.png") });
  const rows = results.runs.map((r) => `| ${r.scope.profile} | ${r.scope.strokeIds.length} | ${r.diagnostic.status} | \`${r.diagnostic.rawLatex ?? "NOT_AVAILABLE"}\` | \`${r.diagnostic.selectedLatex ?? "NOT_AVAILABLE"}\` |`).join("\n");
  fs.writeFileSync(path.join(output, "REPORT.md"), `# OCR diagnostics 05.4\n\nStatus: **${results.status}**. One existing MathCanvas capture; writer count ${summary.writerCount}. Captured segmentation is prediction, never ground truth.\n\n| Profile | Strokes | Status | Raw decoding | Selected after repair/filtering |\n|---|---:|---|---|---|\n${rows}\n\nIndependent labeled oracle scopes: ${summary.labeledMathScopes}. Inference calls: ${summary.inferenceCalls}; completed: ${summary.completedInferences}. Automatic scopes without an eligible label: ${summary.unannotatedAutomaticScopes}.\n\nPostprocessing changed ${summary.postprocessingChangedCandidateCount} candidates. Runtime beam logProb and normalized scores are uncalibrated. Raw tokens, repaired tokens, selection, KaTeX validity and timing are distinct in results.json. EOS/max-length/repeat stop reasons and internal structural-check outcomes are NOT_AVAILABLE.\n\nLegacy output parity is checked on identical scopes; API mutations 0, browser errors 0, input hashes unchanged. Tensor previews come directly from the actual preprocessed float tensor. E2: ${summary.e2}. No preprocessing default or segmentation algorithm changed.\n\n${summary.hypothesisConclusion}. No accuracy or generalization claim without independent labels. Refer to manifest.json for actual model/runtime/source checksums, revision, annotation identity and configuration.\n`);
  console.log(JSON.stringify(summary, null, 2));
}
main().catch(async (error) => {
  fs.mkdirSync(output, { recursive: true });
  write("runner_failure.json", { status: "PARTIAL_OR_BLOCKED", reason: error.message });
  if (page) await page.screenshot({ path: path.join(output, "failure.png") }).catch(() => {});
  console.error(error.message); process.exitCode = 1;
}).finally(async () => {
  if (browser) await browser.close();
  if (server && server.exitCode === null) {
    if (process.platform === "win32") { try { execFileSync("taskkill", ["/PID", String(server.pid), "/T", "/F"], { stdio: "ignore" }); } catch {} }
    else server.kill();
  }
});
