#!/usr/bin/env node
/**
 * Automated Real Ink Regression Runner for MathCanvas OCR V2 (QA 04.5).
 * Validates OcrEvalCaptureV1, executes segmentPageInk_v2 and buildOcrShadowQaReport,
 * checks stroke conservation and asserts negative classification (zero false SYSTEM).
 */
"use strict";

const fs = require("node:fs");
const path = require("node:path");
const crypto = require("node:crypto");
const { performance } = require("node:perf_hooks");

const root = path.resolve(__dirname, "../..");
const buildPath = path.join(root, "frontend", ".test-build-run", "src", "features", "math-workspace", "utils");

function sha256(buf) {
  return crypto.createHash("sha256").update(buf).digest("hex");
}

function main() {
  const fixturePath = path.join(root, ".tmp", "tri-ocr-native", "integral_case_01.json");
  const outputDir = path.join(root, ".tmp", "tri-ocr-qa-impl045");

  if (!fs.existsSync(fixturePath)) {
    console.error(`BLOCKED_MISSING_REAL_INK_FIXTURE: ${fixturePath} does not exist`);
    process.exitCode = 1;
    return;
  }

  if (!fs.existsSync(outputDir)) {
    fs.mkdirSync(outputDir, { recursive: true });
  }

  const rawBytes = fs.readFileSync(fixturePath);
  const captureRaw = JSON.parse(rawBytes.toString("utf8"));

  // Check required compiled modules
  const required = ["page-ocr.js", "structural-candidate-engine.js", "ocr-shadow-qa.js", "ocr-eval-replay.js", "expression-reconstruction.js"];
  for (const f of required) {
    if (!fs.existsSync(path.join(buildPath, f))) {
      console.error(`Missing compiled module ${f}. Please run 'npm run test:compile' in frontend`);
      process.exitCode = 2;
      return;
    }
  }

  const { validateOcrEvalCapture, reconstructSegmentationInput } = require(path.join(buildPath, "ocr-eval-replay.js"));
  const { segmentPageInk_v2 } = require(path.join(buildPath, "page-ocr.js"));
  const { detectStructuralCandidates } = require(path.join(buildPath, "structural-candidate-engine.js"));
  const { buildOcrShadowQaReport } = require(path.join(buildPath, "ocr-shadow-qa.js"));
  const { proposeIntegralExpressionUnits } = require(path.join(buildPath, "expression-reconstruction.js"));

  // 1. Validate OcrEvalCaptureV1
  const capture = validateOcrEvalCapture(captureRaw);
  const strokes = reconstructSegmentationInput(capture);

  // Input immutability check
  const serializedBefore = JSON.stringify(strokes);

  // 2. Input Manifest
  const inputManifest = {
    fixtureName: "integral_case_01.json",
    fixtureSha256: sha256(rawBytes),
    sourceKind: capture.sourceKind,
    pageIndex: capture.pageIndex,
    strokeCount: capture.strokes.length,
    capturedRegionCount: capture.segmentation.regions.length,
    recordedDiagnostics: capture.diagnostics,
    timestamp: new Date().toISOString(),
  };
  fs.writeFileSync(path.join(outputDir, "input_manifest.json"), JSON.stringify(inputManifest, null, 2), "utf8");

  // 3. Replay Segmentation v2
  const t0Seg = performance.now();
  const replayedRegions = segmentPageInk_v2(strokes);
  const segDurationMs = performance.now() - t0Seg;

  const capturedRegionStrokeIds = capture.segmentation.regions.map(r => r.strokeIds);
  const replayedRegionStrokeIds = replayedRegions.map(r => r.strokes.map(s => s.id));

  const replayResult = {
    capturedRegionsCount: capture.segmentation.regions.length,
    replayedRegionsCount: replayedRegions.length,
    identicalToCapture: JSON.stringify(capturedRegionStrokeIds) === JSON.stringify(replayedRegionStrokeIds),
    durationMs: Math.round(segDurationMs * 100) / 100,
    replayedRegions: replayedRegions.map((r, idx) => ({
      index: idx + 1,
      id: r.id,
      strokeCount: r.strokes.length,
      strokeIds: r.strokes.map(s => s.id),
      bounds: r.bounds,
    })),
  };
  fs.writeFileSync(path.join(outputDir, "replay_result.json"), JSON.stringify(replayResult, null, 2), "utf8");

  // 4. Structural Candidate Engine
  const t0Struct = performance.now();
  const candidates = detectStructuralCandidates(strokes);
  const structDurationMs = performance.now() - t0Struct;

  const structuralResult = {
    candidateCount: candidates.length,
    durationMs: Math.round(structDurationMs * 100) / 100,
    hasSystemCandidate: candidates.some(c => c.kind === "SYSTEM"),
    hasAlternativesCandidate: candidates.some(c => c.kind === "ALTERNATIVES"),
    candidates: candidates.map((c, idx) => ({
      index: idx + 1,
      id: c.id,
      kind: c.kind,
      strokeCount: c.sourceStrokeIds.length,
      sourceStrokeIds: c.sourceStrokeIds,
      bounds: c.bounds,
      childrenCount: c.children.length,
      children: c.children.map(ch => ({
        id: ch.id,
        kind: ch.kind,
        strokeCount: ch.sourceStrokeIds.length,
        sourceStrokeIds: ch.sourceStrokeIds,
      })),
      reasons: c.reasons,
    })),
  };
  fs.writeFileSync(path.join(outputDir, "structural_result.json"), JSON.stringify(structuralResult, null, 2), "utf8");

  // 5. Shadow QA Report
  const shadowReport = buildOcrShadowQaReport(strokes, replayedRegions);

  // Core OCR V2: proposal only. This MUST NOT alter baseline regions or drafts.
  const integralUnits = proposeIntegralExpressionUnits(strokes);
  const expressionSummary = {
    unitCount: integralUnits.length,
    units: integralUnits,
    baselineRegionsUnchanged: replayResult.identicalToCapture,
  };
  fs.writeFileSync(path.join(outputDir, "expression_reconstruction.json"),
    JSON.stringify(expressionSummary, null, 2), "utf8");

  // 6. Stroke Integrity Checks
  const expectedPenIds = new Set(strokes.filter(s => s.tool === "PEN").map(s => s.id));
  const assignedStrokeIds = candidates.flatMap(c => c.sourceStrokeIds);
  const missingStrokes = [...expectedPenIds].filter(id => !assignedStrokeIds.includes(id));
  const counts = new Map();
  assignedStrokeIds.forEach(id => counts.set(id, (counts.get(id) || 0) + 1));
  const duplicateStrokes = [...counts.entries()].filter(([, cnt]) => cnt > 1).map(([id]) => id);
  const unknownStrokes = assignedStrokeIds.filter(id => !expectedPenIds.has(id));

  const strokeIntegrity = {
    totalInputStrokes: strokes.length,
    sourcePenStrokeCount: shadowReport.sourcePenStrokeCount,
    strokeConservationPass: missingStrokes.length === 0 && duplicateStrokes.length === 0 && unknownStrokes.length === 0,
    missingStrokes,
    duplicateStrokes,
    unknownStrokes,
    inputNotMutated: JSON.stringify(strokes) === serializedBefore,
  };
  fs.writeFileSync(path.join(outputDir, "stroke_integrity.json"), JSON.stringify(strokeIntegrity, null, 2), "utf8");

  // 7. Overall Test Suite & Invariants
  const tests = [
    {
      name: "All 10 pen strokes are preserved in segmentation and structural candidates",
      pass: strokeIntegrity.sourcePenStrokeCount === 10 && strokeIntegrity.strokeConservationPass,
    },
    {
      name: "Zero missing, duplicate or unknown stroke IDs",
      pass: missingStrokes.length === 0 && duplicateStrokes.length === 0 && unknownStrokes.length === 0,
    },
    {
      name: "Input strokes array is strictly immutable across analysis",
      pass: strokeIntegrity.inputNotMutated,
    },
    {
      name: "Zero false SYSTEM detection (Integral Guard PASS)",
      pass: !structuralResult.hasSystemCandidate,
    },
    {
      name: "Zero false ALTERNATIVES detection",
      pass: !structuralResult.hasAlternativesCandidate,
    },
    {
      name: "Segmentation v2 matches recorded 4 regions snapshot",
      pass: replayResult.capturedRegionsCount === 4 && replayResult.replayedRegionsCount === 4 && replayResult.identicalToCapture,
    },
    {
      name: "Full integral proposal joins limits and body without creating an OCR step",
      pass: integralUnits.length === 1 &&
        integralUnits[0].sourceStrokeIds.length === 10 &&
        integralUnits[0].upperLimitStrokeIds.length === 1 &&
        integralUnits[0].lowerLimitStrokeIds.length === 1 &&
        integralUnits[0].bodyStrokeIds.length === 7 &&
        replayResult.identicalToCapture,
    },
    {
      name: "Shadow QA report reports zero missing and duplicate strokes",
      pass: shadowReport.shadowMissingStrokeIds.length === 0 && shadowReport.shadowDuplicateStrokeIds.length === 0 && shadowReport.shadowUnknownStrokeIds.length === 0,
    },
  ];

  const allPassed = tests.every(t => t.pass);
  const testResults = {
    allPassed,
    totalTests: tests.length,
    passedCount: tests.filter(t => t.pass).length,
    failedCount: tests.filter(t => !t.pass).length,
    tests,
    timestamp: new Date().toISOString(),
  };
  fs.writeFileSync(path.join(outputDir, "test_results.json"), JSON.stringify(testResults, null, 2), "utf8");

  console.log("=== REAL INK REGRESSION RESULTS ===");
  console.log(`Input strokes: ${strokeIntegrity.totalInputStrokes} | Replayed regions: ${replayResult.replayedRegionsCount} | Candidates: ${structuralResult.candidateCount}`);
  console.log(`Integral Guard (No false SYSTEM): ${!structuralResult.hasSystemCandidate ? "PASS" : "FAIL"}`);
  console.log(`No false ALTERNATIVES: ${!structuralResult.hasAlternativesCandidate ? "PASS" : "FAIL"}`);
  console.log(`Stroke Conservation: ${strokeIntegrity.strokeConservationPass ? "PASS" : "FAIL"}`);
  console.log(`Overall Invariants: ${allPassed ? "ALL 8 TESTS PASSED" : "SOME TESTS FAILED"}`);
  console.log(`Artifacts saved in: ${outputDir}`);

  if (!allPassed) {
    process.exitCode = 3;
  }
}

main();
