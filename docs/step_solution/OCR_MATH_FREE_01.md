# OCR-MATH-FREE-01 — free, local handwriting recognition (pix2tex)

## Why
Mathpix is a paid service. This optional implementation runs the MIT-licensed [pix2tex LaTeX-OCR](https://github.com/lukas-blecher/LaTeX-OCR) model on your own machine. It renders saved vector pen strokes into a cropped PNG and passes that image to a local model; it **does not call any paid OCR API**. The student still reviews and explicitly confirms the LaTeX before creating a solution step. `hint_topic` never determines the output formula.

A future benchmark may compare UniMERNet Tiny ([repository](https://github.com/opendatalab/UniMERNet)) on the same samples, but this PR uses pix2tex because its Python image-to-LaTeX interface is straightforward to integrate.

## Run locally

Use an isolated Python environment. First verify that your machine has enough RAM and free disk space to install PyTorch and download a model checkpoint. CPU is allowed but can be slow; a dedicated GPU can improve latency.

```bash
cd backend
python -m venv .venv
# Activate .venv for your operating system before installing
python -m pip install -r requirements-ocr-local.txt
```

Set the following in your **untracked** `backend/.env` (or your deployment's private environment manager):

```dotenv
MATH_OCR_PROVIDER=local_pix2tex
MATH_OCR_TIMEOUT_SECONDS=12
```

Start the usual FastAPI backend. Visit the existing authenticated student Math Workspace, draw *one expression*, wait for ink save, then choose OCR. On the first invocation pix2tex may download its checkpoint from the internet, but recognition runs **locally** afterward. Downloading the free model requires an internet connection once; no Mathpix account or API key is needed. Prewarm and provision the model checkpoint before using a classroom environment; never install downloads in a production request path.

If dependencies or weights are unavailable, the API returns `503 OCR_LOCAL_DEPENDENCY_MISSING` or `503 OCR_LOCAL_MODEL_UNAVAILABLE`, instead of fabricating a formula. The `mathpix` option remains available for comparison but **do not enable** it if you require zero vendor API fees.

## Accuracy, safety and limitations
- pix2tex is an image-to-LaTeX model, not proof of mathematical correctness. Its performance on Vietnamese handwriting, multiple lines and tables is **not yet established** for EduMS.
- Handwriting is rendered on the backend from **PEN** strokes only; `HIGHLIGHTER` marks are ignored.
- Because this provider exposes no calibrated confidence value in the used Python API, EduMS returns `confidence=0` (meaning unknown), not a fabricated high number.
- Keep teacher/guardian consent where relevant when collecting handwriting examples. Collect de-identified expressions, not student names, accounts or full notebooks.
- With only one expression per sample, measure exact LaTeX match, character error rate, model latency, and rate of student corrections in the confirmation dialog. Compare pix2tex and UniMERNet Tiny on the **same** permitted examples before committing to a production model.
- Local models consume RAM, disk and compute; **free software is not free hardware or cloud hosting**.
- Installation may require an older, isolated Python/PyTorch environment due to third-party model dependency compatibility. Do not loosen application security dependencies to make model installation succeed.
- `MATH_OCR_PROVIDER=disabled` remains the safe default. Production mock OCR is forbidden.

## Offline CI
```bash
cd backend
python -m pytest tests/math_solutions/test_local_pix2tex_adapter.py -q
```

CI does not download weights or require a GPU. Raster/prediction tests run when optional Pillow is installed; model accuracy must be validated outside CI on real sample data.
