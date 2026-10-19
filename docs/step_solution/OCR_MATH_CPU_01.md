# OCR-MATH-CPU-01 — Free local recognition on CPU (development preview)

## Recommendation

Start with **RapidLaTeXOCR 0.0.9 (ONNX Runtime CPU)** for short, single-line math expressions instead of the PyTorch-based pix2tex adapter. Both are optional; neither sends drawings to Mathpix. The ONNX variant is a CPU-focused initial experiment, **not yet verified to be sufficiently fast or accurate on this machine**.

Upstream: [RapidAI/RapidLaTeXOCR](https://github.com/RapidAI/RapidLaTeXOCR), [PyPI](https://pypi.org/project/rapid-latex-ocr/). The package is published under Apache-2.0. Model files contain approximate 37 MB, 85 MB and 49 MB ONNX graphs plus tokenizer according to upstream's older documentation; RAM consumption while running can be substantially higher.

## Install on your own machine

1. Use Python 3.10–3.12 and an isolated virtual environment. Check available RAM and disk space before installation.
2. From `backend/`, activate the venv and run:

```bash
python -m pip install -r requirements-ocr-cpu.txt
```

3. Model checkpoint files must be placed in the installed Python package's `rapid_latex_ocr/models/` directory (including `encoder.onnx`, `decoder.onnx`, `image_resizer.onnx`, `tokenizer.json`). Some upstream installation methods download checkpoints automatically; verify the files before starting backend and do not rely on request-time model downloads.
4. Configure your **local, gitignored** `backend/.env`:

```dotenv
MATH_OCR_PROVIDER=local_rapid
```

5. Start the usual FastAPI backend with **one worker** to avoid loading multiple copies of the model. Draw a **single short formula** in the student Math Workspace; wait for ink synchronization, click OCR, inspect or correct the resulting LaTeX and confirm only when accurate.

No Mathpix account, credit card, GPU, or OCR usage fees are needed for self-hosted inference. Existing computer and electricity costs still apply. Do not place checkpoints, student handwriting or secrets into Git. `MATH_OCR_PROVIDER=disabled` is always the safe default. `local_pix2tex` remains a slower/heavier fallback experiment, not the CPU-first default.

## Safety constraints

- One simultaneous model inference per backend process. Additional requests receive `503 OCR_LOCAL_BUSY`; students can retry.
- Model initialization is lazy. The server should be prewarmed with a *locally authorized* formula after provisioning weights; the first OCR request may otherwise pause while loading the model.
- Zero confidence in the response means **uncalibrated/unknown**, not definitely incorrect.
- Full-page multi-line written solutions and sign tables are **out of scope** for this first CPU benchmark. Start with short equations, fractions, radicals, derivatives and integrals.
- OCR is strictly a suggestion. An explicit confirmation is required before creating a solution step or updating learning evidence.
- To assess suitability, use at least 20 de-identified, consented handwritten math expressions and record exact LaTeX accuracy, student correction rate, CPU latency and peak memory (do not upload the original ink).
- CI only covers API contracts using a stub predictor. **Live inference/accuracy and RAM usage are unverified** until tested on the target CPU.

## Development checks

```bash
cd backend
python -m pytest -q tests/math_solutions/test_local_rapid_adapter.py
```

Never claim this model works well on a particular CPU solely because the contract tests pass.
