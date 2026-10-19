# OCR-MATH-CPU-02 — Real CPU inference and benchmark

## Acceptance status: NOT_TESTED for handwriting; real CPU smoke completed

On 2026-10-19, the user authorized installation and a real CPU run after freeing
RAM. RapidLaTeXOCR and all four official checkpoints were installed outside the
global Python environment. **Real ONNX inference ran on five self-rendered
typeset images**, a separate 25-call repeat of those same images, and the
20-image synthetic bundle described below. These images are technical smoke
samples, not handwritten evidence. The user confirmed that no permitted set of
20 human-handwritten formulas is available yet. Therefore
the overall handwritten-OCR acceptance state remains `NOT_TESTED`, despite the
real model execution reported below. No fake predictor was used for measurements.

## Environment inspected

| Item | Observed value |
|---|---|
| OS | Windows 10, build 19043, 64-bit |
| CPU | Intel Core i7-1255U, 12 logical processors |
| Physical RAM | 7.68 GiB |
| Available RAM before installation on 2026-10-19 | 2.23 GiB (1.29 GiB before the user freed RAM) |
| Free workspace disk | 149.57 GiB |
| Python | 3.12.3 |
| OCR environment | Isolated `backend/.venv` in the OCR worktree |

System memory was read with `psutil.virtual_memory()` because Windows CIM and
`systeminfo` were denied to this shell. Available RAM changes with other apps.

## Dependency and checkpoint contract

- `backend/requirements-ocr-cpu.txt` pins RapidLaTeXOCR `0.0.9`, uses
  `onnxruntime` CPU, Pillow, NumPy `<2`, and `psutil` for memory sampling. No
  PyTorch, CUDA or Mathpix was installed for `local_rapid`.
- Installed versions in the isolated environment: RapidLaTeXOCR `0.0.9`,
  ONNX Runtime `1.31.0`, Pillow `11.3.0`, NumPy `1.26.4`, psutil `7.2.2`,
  requests `2.34.2`.
- The upstream `rapid-latex-ocr==0.0.9` package imports `requests` but its
  wheel metadata does not declare it. The first real model-load attempt failed
  with `ModuleNotFoundError: requests`; we added `requests>=2.31,<3` to the
  optional requirements. Missing transitive dependencies now return
  `503 OCR_LOCAL_DEPENDENCY_MISSING`.
- Official package: <https://pypi.org/project/rapid-latex-ocr/>
- Official checkpoint source:
  <https://github.com/RapidAI/RapidLaTeXOCR/releases/tag/v0.0.0>
- Four required files: `encoder.onnx`, `decoder.onnx`, `image_resizer.onnx`,
  `tokenizer.json`. They total 178,952,787 bytes (170.7 MiB) in the local
  gitignored `.tmp/ocr_cpu_models/` directory; the model is not checked into Git.
- Local SHA-256: encoder
  `01bf5dc25539ca0cd5b1bd29296ea495977a6ba5f629dc4178277809d26e5e7d`,
  decoder `bd695497bf1b22279b7626f5916c79226e1e244c84355f8da7edfd2d921d0072`,
  resizer `e0b075c39700f64d50400f39c8fc186bbb3b5d84d31864008313f376603aca9d`,
  tokenizer `1dc27b18d6a518d0d5ff3f4bb7bd98521fe80ad39e5b2a246d4109f1bb9d5019`.
- `scripts.prepare_ocr_cpu_model` streams each file from the official release
  only when explicitly called with `--download`; it verifies minimum sizes,
  records local SHA-256 values, and stores files under gitignored `.tmp/`.
  `LocalRapidOCRAdapter` passes these paths explicitly to the upstream model,
  preventing upstream's constructor from downloading during an API request.

## Benchmark design and current measurements

`python -m scripts.benchmark_ocr_cpu` accepts a reviewed manifest with image
files, ID, group, reference LaTeX, source, and permission marker for handwriting.
It loads the real ONNX model once, measures model initialization separately,
warms it up, then runs images sequentially. It records per-image inference
time, literal exact LaTeX match, character error rate, recognized rate, RSS
before and after, sampled peak RSS, image SHA-256, and a sanitized error code.
The summary reports mean and interpolated p95 latency and first/last RSS to
inspect memory growth. A literal mismatch is a potential manual correction;
actual human correction count remains unset until reviewed.

| Group | Distinct images / calls | Recognized | Literal exact LaTeX | Mean / p95 inference | Peak process RSS |
|---|---:|---:|---:|---:|---:|
| Typeset technical smoke | 5 / 5 | 5/5 | 1/5 (20%) | 0.509 / 0.706 seconds | 316.8 MiB during initialization; 313.0 MiB during inference |
| New synthetic handwriting-styled smoke bundle | 20 / 20 | 20/20 | 2/20 (10%) | 0.526 / 1.092 seconds | 314.3 MiB during inference |
| Repeat stability check on the same five images | 5 / 25 | 25/25 | 5/25 (20%) | 0.477 / 0.650 seconds | 314.0 MiB during inference |
| Permitted handwriting | 0 / 0 of required 20 distinct images | NOT_TESTED | NOT_TESTED | NOT_TESTED | NOT_TESTED |

The five-image run initialized the model in 1.369 seconds, with RSS rising from
54.3 to 270.7 MiB; mean literal character error rate was 0.420. The 25-call
run initialized in 1.304 seconds. RSS after the first and last inference was
280.0 and 280.1 MiB respectively. This short repeat showed no sustained RSS
growth; it is not a long-running leak test or 25 independent accuracy samples.

Observed literal mismatches, with reference followed by model output:

| Sample | Reference | Real OCR output | Observation |
|---|---|---|---|
| SMOKE_001 | `x^2+3x+2` | `x^{2}+3x+2` | LaTeX formatting differs |
| SMOKE_002 | `\frac{1}{x+1}` | `\frac{1}{x+1}` | Exact match |
| SMOKE_003 | `\sqrt{x^2+1}` | `\sqrt{X^{2}+1}` | `x` recognized as uppercase `X` |
| SMOKE_004 | `f'(x)=3x^2-6x` | `{}^{f}(x)=3x^{2}-6x` | Prime/derivative mark recognized incorrectly |
| SMOKE_005 | `\int_0^1 x^2\,dx` | `\textstyle\int_{0}^{1}x^{2}\,d x` | LaTeX formatting differs |

Literal exact match deliberately does not collapse semantically equivalent
LaTeX forms. Four literal mismatches do not equal four confirmed human edits;
actual human correction count remains unmeasured. Accuracy and latency
thresholds for handwritten samples have not been agreed, so no handwritten
`PASS` or `FAIL` can be concluded.

### Additional 20-image synthetic smoke run

The user supplied `backend/data/EduMS_OCR_20_mau_Toan12.zip` on 2026-10-19.
Its README explicitly labels `synthetic_smoke/images/S01.png` through
`S20.png` as self-authored simulated handwriting graphics, **not real human
handwriting**. The archive contains no handwritten PNGs; the
`handwritten/` directory has a template manifest only. ZIP CRC checks passed,
and the 20 manifest entries reference 20 distinct PNG hashes. Only the
synthetic manifest and its images were extracted into gitignored `.tmp/` for
this test. The original archive was not modified or committed.

The real ONNX model returned nonempty text for all 20 synthetic images, but
literal LaTeX exact match was 2/20 (10%), with mean literal CER 1.480, mean
inference time 0.526 seconds, p95 1.092 seconds, model load 1.515 seconds,
and sampled peak inference process RSS 314.3 MiB. Literal CER exceeds 1 here
because several predictions contain long hallucinated fragments. A manual
string/content review separated the 18 literal mismatches into nine apparent
formatting-only differences (`S01`, `S04`, `S06`, `S07`, `S08`, `S10`, `S13`,
`S16`, `S17`) and nine substantive recognition errors (`S02`, `S03`, `S09`,
`S11`, `S12`, `S14`, `S15`, `S18`, `S19`). Including the two exact matches,
11/20 appear to preserve the intended mathematical content; this is a
preliminary human review, not a semantic accuracy benchmark.

Concrete errors include `x` becoming `X` or `\\chi` (`S02`, `S03`, `S12`),
`y` becoming `V` (`S18`), added derivative text (`S09`), malformed limit and
trigonometric expressions (`S14`, `S15`), and a nonsensical output for the
visually clear `\\sqrt{16}=4` (`S19`). Re-running `S09`, `S14`, `S15`, and
`S19` after grayscale conversion and foreground cropping produced the same
predictions. This small preprocessing probe does not establish that other
preprocessing or models cannot help. It does establish that the current model
cannot be trusted to grade from these OCR suggestions without user review.

Command, run from `backend/` in the isolated OCR worktree:

```powershell
.venv/Scripts/python.exe -m scripts.benchmark_ocr_cpu --manifest ../.tmp/ocr_20_synthetic/manifest.json --model-dir ../.tmp/ocr_cpu_models --output ../.tmp/ocr_cpu_20_synthetic_report.json
```

The CLI printed `NOT_TESTED` and returned nonzero because it deliberately
requires 20 permitted **human handwritten** samples for acceptance. The
synthetic-smoke measurements above did run; they are not a handwriting PASS.

## EduMS integration checked

The existing frontend saves dirty ink before OCR and prevents recognition if
that save fails. The backend checks student ownership, passes the saved strokes
to the adapter, and ignores highlighter strokes during rasterization. OCR
returns a suggestion; a separate student confirmation creates a solution step.
Uncalibrated local confidence is shown as unknown. A busy CPU returns
`503 OCR_LOCAL_BUSY`, and missing model files return
`503 OCR_LOCAL_MODEL_UNAVAILABLE`. The edge-of-page single-dot raster bug was
fixed so a pen point at normalized coordinate 1.0 remains visible.

The direct adapter path was also exercised with two simple pen strokes and an
ignored highlighter stroke: PNG rasterization → real model → editable LaTeX
suggestion returned, with uncalibrated confidence `0.0`. The crude X-like
stroke was recognized as `\displaystyle{\mathcal{X}}_{\sim}`, so this test
only demonstrates that the real adapter path executes; it is not a handwritten
accuracy sample. A live browser session with authenticated student, database,
ink save, confirmation modal and Solution Step was not run in this isolated
worktree. That end-to-end path remains open.

## Commands and results so far

Run from `backend/` unless stated otherwise:

| Command | Observed result |
|---|---|
| `.venv/Scripts/python.exe -m pip install -r requirements-ocr-cpu.txt` | PASS; installed optional CPU packages in isolated venv |
| `.venv/Scripts/python.exe -m scripts.prepare_ocr_cpu_model --download` | PASS; four official files downloaded and SHA-256 inventory recorded under gitignored `.tmp/` |
| `.venv/Scripts/python.exe -m pytest -q tests/math_solutions/test_ocr_cpu_benchmark.py tests/math_solutions/test_local_rapid_adapter.py tests/math_solutions/test_local_render.py` | 17 passed |
| `.venv/Scripts/python.exe -m pytest -q tests/math_solutions` | 129 passed, 5 skipped |
| `python -m pytest -q --maxfail=1 tests/curriculum/test_final_readiness_preflight.py` | 31 passed after restoring checkout files to their original LF bytes |
| `.venv/Scripts/python.exe -m app.api.check_contract` | PASS |
| `.venv/Scripts/python.exe -m app.api.v2.check_contract` | PASS |
| `.venv/Scripts/python.exe -m pip check` | PASS, no broken requirements |
| `.venv/Scripts/python.exe -m scripts.benchmark_ocr_cpu --manifest data/fixtures/ocr_cpu_smoke/manifest.json --model-dir ../.tmp/ocr_cpu_models --output ../.tmp/ocr_cpu_benchmark_smoke_real.json` | Real ONNX smoke completed; overall status `NOT_TESTED` because handwriting set is empty |
| Same benchmark command with the gitignored 25-call repeat manifest | Real ONNX repeat completed; overall status `NOT_TESTED` because handwriting set is empty |
| `npm.cmd run test` from `frontend/` | 124 passed |
| `npm.cmd run typecheck` from `frontend/` | PASS |
| `npm.cmd run build` from `frontend/` | BLOCKED: Turbopack rejects a test-only `node_modules` junction outside the worktree root |
| `npm.cmd run build -- --webpack` from `frontend/` | PASS: compiled, typed, and generated all 16 static pages |

Earlier Python tests used the global environment; the current OCR/solution
tests and API contracts above were rerun in the isolated OCR venv. An attempted
full backend `python -m pytest -q` run reached about 45% of 1904 tests, then was
stopped when the Python process reached about 4.1 GiB RSS and system available
RAM fell below 0.4 GiB. It had reported several curriculum hash failures before
the stop. The cause was this Windows worktree checkout converting tracked JSON
from LF to CRLF; restoring the original Git bytes without any academic edit made
the focused 31-test validator file pass. A narrow `.gitattributes` rule now
preserves LF checkout bytes for `backend/data` JSON/CSV files on Windows. The
full suite was not rerun because of the memory limit. No full-backend PASS or
live browser OCR result is claimed.

## To complete the real benchmark

1. Follow `backend/data/fixtures/ocr_cpu_handwritten/README.md` to place at
   least 20 consented, de-identified handwritten formula PNGs and a reviewed
   manifest under gitignored `.tmp/ocr_math_cpu_handwritten/` when available.
2. Run the benchmark with `--manifest`, `--output`,
   `--min-handwritten-exact-rate`, and `--max-handwritten-p95-seconds` using
   thresholds agreed before evaluation. Inspect failures and actual human
   correction needs; repeat sequentially to inspect RSS growth.
3. Run one backend worker with `MATH_OCR_PROVIDER=local_rapid` and
   `MATH_OCR_MODEL_DIR=../.tmp/ocr_cpu_models`; verify the full Canvas → Ink
   Save → PNG → ONNX → editable confirmation → Solution Step path in a browser.

The user must supply or authorize 20 handwritten samples; the five typeset
images cannot substitute for that dataset. Do not commit model weights, student
drawings, API keys or local `.env` files.
