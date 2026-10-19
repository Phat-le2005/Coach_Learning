# OCR-MATH-CPU-02 — Real CPU inference and benchmark

## Acceptance status: NOT_TESTED

The model has **not yet been run** in the isolated OCR environment. The machine
had only about 1.29 GB available RAM during inspection on 2026-10-19. The user
has asked to defer the checkpoint download and inference while code and tests
are completed. No consented set of 20 handwritten formula images has been supplied.
Contract tests and the five self-rendered smoke PNGs are not evidence of OCR
accuracy. The benchmark JSON at `.tmp/ocr_cpu_benchmark_smoke.json` currently
reports `NOT_TESTED` because RapidLaTeXOCR is not installed in that environment.

## Environment inspected

| Item | Observed value |
|---|---|
| OS | Windows 10, build 19043, 64-bit |
| CPU | Intel Core i7-1255U, 12 logical processors |
| Physical RAM | 7.68 GiB |
| Available RAM at first inspection | 1.29 GiB |
| Free workspace disk | 148.73 GiB |
| Python | 3.12.3 |
| OCR environment | `backend/.venv` in the OCR worktree; created, packages pending |

System memory was read with `psutil.virtual_memory()` because Windows CIM and
`systeminfo` were denied to this shell. Available RAM changes with other apps.

## Dependency and checkpoint contract

- `backend/requirements-ocr-cpu.txt` pins RapidLaTeXOCR `0.0.9`, uses
  `onnxruntime` CPU, Pillow, NumPy `<2`, and `psutil` for memory sampling. No
  PyTorch, CUDA or Mathpix is needed for `local_rapid`.
- The installed versions of RapidLaTeXOCR and ONNX Runtime in the isolated
  environment are **pending** until installation is performed.
- Official package: <https://pypi.org/project/rapid-latex-ocr/>
- Official checkpoint source:
  <https://github.com/RapidAI/RapidLaTeXOCR/releases/tag/v0.0.0>
- Four required files: `encoder.onnx`, `decoder.onnx`, `image_resizer.onnx`,
  `tokenizer.json`. The model is not checked into Git.
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

| Group | Available images | Actual ONNX inference | Accuracy | Mean / p95 | Peak RSS |
|---|---:|---|---|---|---|
| Typeset technical smoke | 5 | NOT_TESTED | NOT_TESTED | NOT_TESTED | NOT_TESTED |
| Permitted handwriting | 0 of required 20 | NOT_TESTED | NOT_TESTED | NOT_TESTED | NOT_TESTED |

No recognition errors or success rates can be reported without model output.
Acceptance thresholds for handwritten exact rate and p95 latency have not been
agreed; the CLI requires these values before it can conclude PASS or FAIL.

## EduMS integration checked

The existing frontend saves dirty ink before OCR and prevents recognition if
that save fails. The backend checks student ownership, passes the saved strokes
to the adapter, and ignores highlighter strokes during rasterization. OCR
returns a suggestion; a separate student confirmation creates a solution step.
Uncalibrated local confidence is shown as unknown. A busy CPU returns
`503 OCR_LOCAL_BUSY`, and missing model files return
`503 OCR_LOCAL_MODEL_UNAVAILABLE`. The edge-of-page single-dot raster bug was
fixed so a pen point at normalized coordinate 1.0 remains visible.

This is verified by code and tests, **not** by a live browser session with
the real ONNX model and database. That end-to-end path remains open.

## Commands and results so far

Run from `backend/` unless stated otherwise:

| Command | Observed result |
|---|---|
| `python -m pytest -q tests/math_solutions/test_ocr_cpu_benchmark.py tests/math_solutions/test_local_rapid_adapter.py tests/math_solutions/test_local_render.py` | 15 passed |
| `python -m pytest -q tests/math_solutions` | 127 passed, 5 skipped |
| `python -m pytest -q --maxfail=1 tests/curriculum/test_final_readiness_preflight.py` | 31 passed after restoring checkout files to their original LF bytes |
| `python -m app.api.check_contract` | PASS |
| `python -m app.api.v2.check_contract` | PASS |
| `python -m scripts.benchmark_ocr_cpu --manifest data/fixtures/ocr_cpu_smoke/manifest.json --output ../.tmp/ocr_cpu_benchmark_smoke.json` | NOT_TESTED: RapidLaTeXOCR missing |
| `npm.cmd run test` from `frontend/` | 124 passed |
| `npm.cmd run typecheck` from `frontend/` | PASS |
| `npm.cmd run build` from `frontend/` | BLOCKED: Turbopack rejects a test-only `node_modules` junction outside the worktree root |
| `npm.cmd run build -- --webpack` from `frontend/` | PASS: compiled, typed, and generated all 16 static pages |

The Python tests above used the globally installed Python environment while
the isolated OCR environment awaits dependency installation. An attempted full
backend `python -m pytest -q` run reached about 45% of 1904 tests, then was
stopped when the Python process reached about 4.1 GiB RSS and system available
RAM fell below 0.4 GiB. It had reported several curriculum hash failures before
the stop. The cause was this Windows worktree checkout converting tracked JSON
from LF to CRLF; restoring the original Git bytes without any academic edit made
the focused 31-test validator file pass. A narrow `.gitattributes` rule now
preserves LF checkout bytes for `backend/data` JSON/CSV files on Windows. The
full suite was not rerun because of the memory limit. No full-backend PASS or
live browser OCR result is claimed.

## To complete the real benchmark

1. Close memory-heavy applications and recheck that the system has enough
   available RAM for model initialization and sequential inference.
2. In the worktree `backend/`, install into the already created isolated venv:
   `backend/.venv/Scripts/python.exe -m pip install -r requirements-ocr-cpu.txt`.
3. Run `backend/.venv/Scripts/python.exe -m scripts.prepare_ocr_cpu_model --download`
   from `backend/` only after the agreed resource check.
4. Run the smoke benchmark with the five committed self-authored PNGs, then
   follow `backend/data/fixtures/ocr_cpu_handwritten/README.md` to place at
   least 20 consented, de-identified handwritten formula PNGs and a reviewed
   manifest under gitignored `.tmp/ocr_math_cpu_handwritten/`.
5. Run the benchmark with `--manifest`, `--output`,
   `--min-handwritten-exact-rate`, and `--max-handwritten-p95-seconds` using
   thresholds agreed before evaluation. Inspect failures and actual human
   correction needs; repeat sequentially to inspect RSS growth.
6. Run one backend worker with `MATH_OCR_PROVIDER=local_rapid` and
   `MATH_OCR_MODEL_DIR=../.tmp/ocr_cpu_models`; verify the full Canvas → Ink
   Save → PNG → ONNX → editable confirmation → Solution Step path in a browser.

The user must supply or authorize 20 handwritten samples; the five typeset
images cannot substitute for that dataset. Do not commit model weights, student
drawings, API keys or local `.env` files.
