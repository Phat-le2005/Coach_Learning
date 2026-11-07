#!/usr/bin/env node
/**
 * Reproducible, local-only comparison of segmentation v2 and structural shadow.
 *
 * Usage from repo root:
 *   cd frontend && npm run test:compile && cd ..
 *   node tools/ocr-fixtures/run_shadow_batch.cjs \
 *      .tmp/tri-ocr-external-fixtures .tmp/tri-ocr-shadow-results
 *
 * Reads INKML_EXTERNAL fixture JSON; never contacts services, writes to the
 * caller-specified output directory. Do not commit real handwriting captures.
 */
"use strict";
const fs = require("node:fs");
const path = require("node:path");
const crypto = require("node:crypto");
const { execFileSync } = require("node:child_process");

const root = path.resolve(__dirname, "../..");
const buildPath = path.join(root, "frontend", ".test-build-run", "src", "features", "math-workspace", "utils");
const sources = [
  "frontend/src/features/math-workspace/utils/page-ocr.ts",
  "frontend/src/features/math-workspace/utils/structural-candidate-engine.ts",
  "frontend/src/features/math-workspace/utils/ocr-shadow-qa.ts",
];

function hash(buffer) { return crypto.createHash("sha256").update(buffer).digest("hex"); }
function gitHead() {
  try { return execFileSync("git", ["rev-parse", "HEAD"], { cwd: root, encoding: "utf8" }).trim(); }
  catch { return "UNAVAILABLE"; }
}

function assertInk(strokes, name) {
  if (!Array.isArray(strokes)) throw new Error(`${name}: strokes not an array`);
  const ids = new Set();
  for (const stroke of strokes) {
    if (!stroke || typeof stroke.id !== "string" || ids.has(stroke.id)) {
      throw new Error(`${name}: invalid/duplicate stroke id`);
    }
    ids.add(stroke.id);
    if (stroke.tool !== "PEN" && stroke.tool !== "HIGHLIGHTER") {
      throw new Error(`${name}: unsupported tool`);
    }
    if (!Array.isArray(stroke.points) || stroke.points.some((p) =>
      !p || !Number.isFinite(p.x) || !Number.isFinite(p.y))) {
      throw new Error(`${name}: invalid point`);
    }
  }
}

function main() {
  const [inputArg, outputArg] = process.argv.slice(2);
  if (!inputArg || !outputArg) {
    process.stderr.write("Usage: node run_shadow_batch.cjs <fixture-directory> <output-directory>\n");
    process.exitCode = 2;
    return;
  }
  const input = path.resolve(inputArg);
  const output = path.resolve(outputArg);
  if (input === output) throw new Error("Input and output directories must differ");
  const compiledFiles = ["page-ocr.js", "structural-candidate-engine.js", "ocr-shadow-qa.js"];
  for (const file of compiledFiles) {
    if (!fs.existsSync(path.join(buildPath, file))) {
      throw new Error(`Missing ${file}; first run 'cd frontend && npm run test:compile'`);
    }
  }

  // Deliberately load the same TypeScript modules used by MathCanvas.
  const { segmentPageInk_v2 } = require(path.join(buildPath, "page-ocr.js"));
  const { buildOcrShadowQaReport } = require(path.join(buildPath, "ocr-shadow-qa.js"));
  const files = fs.readdirSync(input).filter((f) => f.endsWith(".json") &&
    f !== "converted_manifest.json").sort();
  if (files.length === 0) throw new Error("No fixture JSON files found");
  const records = [];
  for (const file of files) {
    const bytes = fs.readFileSync(path.join(input, file));
    const fixture = JSON.parse(bytes.toString("utf8"));
    if (fixture.fixtureKind !== "INKML_EXTERNAL" || !Array.isArray(fixture.strokes)) {
      continue; // Ignore metadata JSON, never invent sample inputs.
    }
    assertInk(fixture.strokes, file);
    const baselineRegions = segmentPageInk_v2(fixture.strokes);
    const report = buildOcrShadowQaReport(fixture.strokes, baselineRegions);
    records.push({
      sampleId: fixture.sampleId ?? path.basename(file, ".json"),
      inputFile: file,
      inputSha256: hash(bytes),
      sourcePath: fixture.sourcePath ?? null,
      inkCreationMethod: fixture.provenance?.inkCreationMethod ?? "unknown",
      strokeCount: report.sourcePenStrokeCount,
      baselineRegionCount: report.baselineRegionCount,
      candidateCount: report.structuralCandidateCount,
      baselineRegions: baselineRegions.map((region) => ({
        id: region.id, strokeIds: region.strokes.map((stroke) => stroke.id),
      })),
      qa: report,
    });
  }
  if (!records.length) throw new Error("No INKML_EXTERNAL fixtures found");
  const provenance = {
    gitHead: gitHead(),
    compiled: compiledFiles.map((file) => ({
      file, sha256: hash(fs.readFileSync(path.join(buildPath, file))),
    })),
    sources: sources.map((file) => ({
      file, sha256: hash(fs.readFileSync(path.join(root, file))),
    })),
    nodeVersion: process.version,
    sampleCount: records.length,
    // Wall-clock timing deliberately excluded from reproducibility comparison.
  };
  fs.mkdirSync(output, { recursive: true });
  fs.writeFileSync(path.join(output, "shadow_batch.json"),
    JSON.stringify({ provenance, records }, null, 2) + "\n");
  process.stdout.write(`Evaluated ${records.length} ink fixtures, output: ${path.join(output, "shadow_batch.json")}\n`);
}

try { main(); }
catch (error) {
  process.stderr.write(`OCR_SHADOW_BATCH_FAILED: ${error instanceof Error ? error.message : String(error)}\n`);
  process.exitCode = 1;
}
