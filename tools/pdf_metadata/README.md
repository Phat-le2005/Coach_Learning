# PDF metadata pilot

Isolated from the running FastAPI/Next.js app. The source PDF is read-only. Packages, weights, caches, temp files and output are stored on E for the Windows pilot. Native/Paddle and Qwen stages run locally; explicit Gemini actions send selected source images and metadata to Google. No stage writes the production database.

## Start here: give the workflow one PDF

The entry also runs bounded image-to-formula checks and exports a provisional step-checking contract. `process_corpus.ps1` / `.cmd` accepts a folder or ZIP, runs one PDF at a time, preserves checkpoints, and exposes queue progress. Default batch budgets are 100 pages per invocation, 3 Qwen metadata questions and 8 image regions per PDF; 0 removes a particular limit. See `docs/pdf-readiness-batch-core-2026-11-03.md` for commands, actual multi-PDF results and core integration boundaries. The core adapter returns provisional matches, never production scores.

The default entry now completes extraction → text-to-LaTeX → local Qwen review → a consolidated `pdf-final/v1` export. Open each job's **`final.html`**; **`final.json`** identifies `questions.final.jsonl` and its pretty JSON. These contain the immutable source metadata plus LaTeX candidates and machine review. See `docs/pdf-complete-pipeline-2026-11-02.md` for the current workflow, validation and limits. `-ReviewLimit 3` is a short trial; default 0 reviews all discovered questions. `-SkipQwen` still creates the final artifact using rules and marks model review deferred.

Latest source audit: 40 manually source-transcribed formula regions across two PDFs, with 24 development and 16 held-out cases. Source geometry now recovers vector radicals/trailing terms and blocks dropped absolute bars, overlines and subscripts; model formatting cannot override those warnings. The full PDF suite, including progress monitoring, paired-source conversion and the separate calculus grading trial, has 326 passing tests. See `docs/pdf-formula-source-audit-2026-11-02.md` for the split counts and limitations; these are formula-region fidelity results, not full-book grading accuracy.

### Convert adjacent questions and solutions into one readable file

For native-text PDFs with printed question/solution labels, `convert_pairs.ps1` creates one portable HTML containing source images plus searchable lossy text. It then reads metadata directly from that file; it does not OCR the converted file again. The main JSONL includes only occurrences with both question and solution regions. Unpaired occurrences remain separate; repeated printed question numbers are never used alone to join unrelated chapters.

```powershell
.\tools\pdf_metadata\convert_pairs.ps1 'E:\materials\with-solutions.pdf' -Open
```

Each job's `paired.json` points to `questions-and-solutions.html`, `questions.metadata.json`, `questions.metadata.jsonl` and a review queue under `paired/versions/<hash>`. The HTML opens offline with embedded PNGs, while the metadata export has crop paths/hashes and PDF page/bbox provenance. Metadata JSON preserves unpaired records in `unpaired_questions`; JSONL sends them to `questions.unpaired.jsonl`. A moved HTML can recreate its metadata and PNG assets with `python -m pdfmeta.paired metadata --html <file> --output <folder>`.

The probability trial processed all 167 source pages: 508 question occurrences, 251 paired candidates, 257 unpaired occurrences, and 7 paired candidates with a possible following-section boundary. This is source acquisition, not source-mathematics approval or a text-to-LaTeX upgrade. Image-only pages are flagged `OCR_REQUIRED`; this lightweight lane does not load an OCR/LLM model or replace the full PDF workflow. See `docs/pdf-paired-source-conversion-2026-11-03.md`.

The subsequent solved-only export recognizes standalone `Giải` labels and detaches explicitly labelled next sections into context with an audit trail. It finds 253 paired occurrences and 255 unpaired occurrences; all 7 previous boundary warnings and 5 additional transitions are addressed by source-backed rules. `python -m pdfmeta.paired solved-collection --job <job> --output <folder>` physically excludes unpaired records from its HTML/metadata. A separate PDF renderer preserves each question and solution as one source-image region. The delivered PDF has 253 entries, 151 pages and PDF-page/bbox mappings in its companion metadata. This output uses source images, not a new OCR pass or a claim that LaTeX is corrected. See `docs/pdf-solved-only-collection-2026-11-03.md`.

### Separate calculus grading sandbox

`trial_grading.ps1` builds proposed, versioned 10-point rubrics for a manually source-reviewed development cohort of 12 questions from the derivative PDF. Ten can receive sandbox scores; two are held because printed solution claims conflict with independent calculations. The 149 labelled synthetic scenarios cover correct/equivalent work, common errors, missing steps, unsupported inputs and valid polynomial-division/critical-ratio methods. They are regression checks, not measured accuracy on real students or new PDFs.

```powershell
.\tools\pdf_metadata\trial_grading.ps1 -Job '.tmp\pdf-jobs\5db1fc66ab0a42553e882981' -Open
```

The dashboard's **Xem điểm chấm thử** opens source images, rubric weights and criterion feedback. `grading-trial.json` identifies the immutable-version rubric package and results. This command uses existing local Python only: no model inference, cloud request or database write. It does not alter the general extraction pipeline, the final acquisition file, or approval flags. Another PDF needs its own reviewed function/domain/task annotations before this sandbox can grade it. See `docs/pdf-calculus-grading-pilot-2026-11-03.md` for adapter input, evidence and limitations.

Drag a PDF onto `tools/pdf_metadata/process_pdf.cmd`, or run:

```powershell
.\tools\pdf_metadata\process_pdf.ps1 'E:\materials\your-document.pdf'
```

The local progress dashboard starts with each run (normally `http://127.0.0.1:8789/`). Drag/drop or `-Open` opens it immediately: live stages, page/question counts, checkpoint usage, pipeline RAM/CPU, and links to the final viewer/JSONL. Trial Qwen scope is shown separately from the whole document. See `docs/pdf-progress-dashboard-2026-11-02.md`; use `-NoProgress` for console only. The monitor is read-only and does not load inference models.

The workflow chooses an isolated job by PDF hash, routes native versus scanned pages, runs local OCR only as needed, assembles questions/steps, discovers tables, checks supported math and exports metadata plus a review page. It does not need question numbers, page selections, editorial fixtures or a Qwen/Gemini key. Install/model setup happens only when missing and stays on E. A second run resumes valid checkpoints. Renaming an identical PDF reuses the same job; changed PDF bytes create another job.

Open `.tmp/pdf-jobs/review.html` for the processed-document library. The command prints the exact metadata path, and every job has `result.json` with artifact locations. `versions/<fingerprint>/` preserves results across pipeline changes. The stable job-level `review.html` opens the latest version.

This automates **draft acquisition**, not academic approval. Unknown layouts still produce page metadata and a review queue. OCR can lose Vietnamese accents or mathematical notation; inferred section boundaries are flagged and raw text/images remain available. Nothing is imported into production grading automatically. See `docs/pdf-metadata-one-file-workflow-2026-11-02.md` for evidence and supported boundaries.

The commands below are optional development/benchmark tools; normal ingestion uses `process_pdf` above.

### Automatic Qwen review

`process_pdf` now follows extraction with a local Qwen metadata review, one question at a time. OCR runs in a separate process and exits before Qwen loads. The wrapper stops only a Qwen server it started; an already-running server is preserved. Default `-ReviewLimit 0` means all questions; use `-ReviewLimit 3` for a short trial or `-SkipQwen` for extraction only.

Review an already-extracted PDF without running extraction again:

```powershell
.\tools\pdf_metadata\review_pdf.ps1 -Job '.tmp\pdf-jobs\<PDF-hash-prefix>'
```

The wrapper now normalizes LaTeX first and opens stable `final.html`; `qwen-review.html` remains a component viewer. `qwen-review.json` points to the versioned review directory, containing `questions.qwen-reviewed.jsonl`, `machine-cleared.jsonl`, `machine-flagged.jsonl` and `deferred.jsonl`. Question IDs, rather than printed question numbers, key the work. Successful question jobs are cached by source metadata, asset hashes, model weights, prompt/schema and output settings. `-RetryFailed` explicitly retries failed/in-flight jobs; no cloud fallback occurs.

Qwen sees bounded text/OCR and formula candidates, **not PDF images**. `MACHINE_CLEARED` means no issue found within complete metadata plus passing local gates. Existing OCR/math flags, missing source fields, truncated input and model issues prevent clearance. `MACHINE_FLAGGED` is automatically isolated; `DEFERRED` includes model failure, unavailable server and questions beyond a trial limit. All three are machine routing states; source metadata, answers, step boundaries and grading approval are unchanged. Qwen proposals are saved, never silently applied. The small installed model has missed known errors before; machine review is not a correctness benchmark or academic approval.

## Native formula and sign-table refinement

After native/OCR extraction, use `layout-refine` to recover bounded formulas from font size, glyph position and fraction bars, then inspect explicitly selected raster tables. It uses existing local FormulaNet-M weights for small label/number crops, while interval signs and arrow directions come from pixels. A constrained local font matcher can supply an unverified number/infinity candidate when OCR fails; valid disagreements remain queued. Complex/unreadable tables remain in review; this action does not load Qwen or call Gemini.

```powershell
.\tools\pdf_metadata\run.ps1 -Action layout-refine -Questions '151,154,161' -Limit 3

# Broader pilot trial; keep prior artifacts separate.
.\tools\pdf_metadata\run.ps1 -Action layout-refine -Questions '151,154,161,153,159,163' -Limit 6 `
  -TrialOutput 'E:\HocTap\Hackathon-SGU2026\Coach_Learning\.tmp\pdf-metadata-pilot-v1\layout-trial-v2'
```

The sample numbers above belong to the pilot. Another PDF requires its own extracted pilot and explicit `-Pdf`, `-Output`, and question selection. Results include `review.html`, `layout-report.json`, `tables.jsonl`, `review-queue.json` and `questions.math-audit.jsonl`. Existing raw pages, OCR, editorial state and prior benchmark artifacts remain unchanged. See `docs/pdf-metadata-fractions-variation-2026-11-02.md` for the latest measured coverage and limitations; `docs/pdf-metadata-native-layout-2026-11-02.md` describes the earlier single-baseline trial.

For the text-only Qwen experiment use `pilot-trial`; it reviews a bounded subset, not the full document. Its compact metadata results remain unapproved even when JSON and source-reference gates pass. See `docs/pdf-metadata-compact-trial-2026-11-02.md`.

## Default: local Qwen review

The Windows wrapper now defaults to `-Provider local`. The Python entry points read `PDF_REVIEW_PROVIDER=local` from `.env`. There is no automatic cloud fallback. The existing Gemini key is preserved for an explicit future choice and is never sent to the local model server.

```powershell
# Download once to E and verify published SHA-256 digests.
.\tools\pdf_metadata\run.ps1 -Action local-setup

# On-demand model server: 3 CPU threads, no GPU offload, below-normal priority.
.\tools\pdf_metadata\run.ps1 -Action local-start
.\tools\pdf_metadata\run.ps1 -Action local-preflight

# Review the pilot question with its original images and local step candidates.
.\tools\pdf_metadata\run.ps1 -Action local-review -Questions '152' -Limit 1 -MaxCalls 1 -MaxOutputTokens 4096

# A new corpus gets a separate local output directory.
.\tools\pdf_metadata\run.ps1 -Action corpus-plan -Provider local -CorePages 1 -Overlap 1
.\tools\pdf_metadata\run.ps1 -Action corpus-run -Provider local -Limit 1 -MaxCalls 1 -MaxOutputTokens 4096

# Release the model's memory after a run.
.\tools\pdf_metadata\run.ps1 -Action local-stop
```

Pilot output is `.tmp/pdf-metadata-pilot-v1/local-review/`, viewable at `http://localhost:8787/local-review/review.html` through the existing authoring server. Default local corpus output is `.tmp/toan12-local-corpus/`. Existing Gemini artifacts remain in their old directories.

The initial local model is `ggml-org/Qwen3-VL-2B-Instruct-GGUF` Q8_0, revision `ea6a11058182570be6436b9a2e4ee7f7b49f908d`, with its Q8 vision projector, running the official Windows CPU llama.cpp build `b12032`. About 2.3 GB of downloads are pinned and verified by `local_setup.py`. Runtime, model, projector and local logs live in `.tmp/pdf-pipeline-runtime`; no system-wide Ollama/model install is used. The model is loaded only by `local-start`, not by the web app.

The loopback endpoint accepts only `127.0.0.1`, `localhost` or `::1`, blocks redirects/proxies, and uses a separate local server token file under the ignored runtime directory. Source data does not leave the machine during inference. Downloads from GitHub/Hugging Face happen only during setup. Model fingerprint participates in cache identity. Local token counts measure computation, not a cloud bill; runtime and electricity still have costs.

This small CPU model is a resource-bounded trial, not a claim of Gemini-equivalent math accuracy or practical throughput for all 3,478 pages. Benchmark a few questions and images first. Missing assumptions, OCR mistakes and model additions remain queued; local generation cannot grant academic approval or grading. See `docs/pdf-metadata-local-qwen-2026-11-02.md`.

## Run on Windows

From the repository root, use the project-local environment. `-Install` installs the lightweight dependencies; `-InstallOcr` also installs CPU PaddleOCR dependencies. The environment lives at `.tmp/pdf-pipeline-runtime/.venv`.

```powershell
# Native extraction, source crops and a local review HTML.
.\tools\pdf_metadata\run.ps1 -Action native -Install

# Layout detection + formula crops on the pilot document.
.\tools\pdf_metadata\run.ps1 -Action hybrid -Pages all -InstallOcr

# Attach model evidence and flag discrepancies. Native/source data stays intact.
.\tools\pdf_metadata\run.ps1 -Action enrich

# Read flagged formula regions again with the larger recognizer, then compare.
.\tools\pdf_metadata\run.ps1 -Action fallback
.\tools\pdf_metadata\run.ps1 -Action enrich

# Source-specific regression assertions and generic unit tests.
.\tools\pdf_metadata\run.ps1 -Action check
.\tools\pdf_metadata\run.ps1 -Action test
```

Open `.tmp/pdf-metadata-pilot-v1/review.html`. Each item shows stem/answer/solution source crops, original page links, raw native text, OCR candidates, warnings and reference-step excerpts. Answers/solutions are intentionally visible here: this is an authoring/review artifact, not a student-facing payload.

The optional full-page VLM experiment is significantly slower on this laptop. It is separate from the hybrid pass:

```powershell
.\tools\pdf_metadata\run.ps1 -Action ocr -Pages '1'
.\tools\pdf_metadata\run.ps1 -Action formula
.\tools\pdf_metadata\run.ps1 -Action enrich
```

For another digital, single-column PDF, change source and output explicitly. Run `native`, then `hybrid`, then `enrich` with the same source/output paths. The `check` action is specific to the pilot fixture and must not be applied to another source.

```powershell
.\tools\pdf_metadata\run.ps1 -Action native -Pdf 'E:\materials\another.pdf' -Output 'E:\pdf-pilots\another'
.\tools\pdf_metadata\run.ps1 -Action hybrid -Pages all -Output 'E:\pdf-pilots\another'
.\tools\pdf_metadata\run.ps1 -Action enrich -Output 'E:\pdf-pilots\another'
```

## Output contract

- `manifest.json`: source path/hash, page count, extraction/render information.
- `pages/*.json`: page geometry, raw lines, glyph positions/fonts/colors, image/vector bounds. Coordinates are PDF points from top-left. `pages/*.png` preserve source layout.
- `questions.candidates.jsonl`: native question/answer/solution candidates and grounded step excerpts.
- `questions.enriched.candidates.jsonl`: adds model evidence and discrepancy flags.
- `assets/*.png`: separate source crops for stem, answer and solution.
- `paddle-vl/`: full-page VLM outputs/config/timing when requested.
- `fast-hybrid/`: layout and formula OCR checkpoints for each processed page, model hashes, runtime measurements.
- `formula-probe/`: explicit control experiment; not a generic parser rule.
- `formula-fallback/`: larger-model alternatives for flagged formula regions. Old results and warnings remain available.
- `report.json`, `enrichment-report.json`, `fixture-result.json`: separate structural, source-regression and OCR quality evidence.

Every candidate stays `academic_review=PENDING`, `grading_support=NOT_ASSESSED`, `publishable=false`. JSON Schema validates the acquisition format. It is **not** the existing production Question import format. Authoring a MathSpec, AnswerSpec or rubric, checking taxonomy IDs and performing a reviewed import remain separate tasks.

## Quality boundaries

This pilot's assembler targets digital single-column documents with explicit Câu/Bài, Trả lời, Lời giải and Đáp án markers. Its rules do not contain the pilot's page count, question range or answer values. Specific expectations live in `fixtures/pilot-kntt-v1.json` and are checked only after verifying the PDF hash.

It retains continuation regions across pages, including drawings/tables above the first text line. Short raised math fragments overlapping the next heading are assigned to the next question. Repeated page-margin text is retained in raw records but omitted from question assembly.

The following are **not solved by this prototype**:

- Full mathematical transcription, semantic interpretation of all variation tables/figures, and academic validation of the source solutions.
- Guaranteed question assembly for scans, multiple columns, unfamiliar section conventions or compound OCR blocks. Full-page OCR can produce evidence for these, but the native assembler must be extended/evaluated before claiming support.
- Complete formula detection: detected regions are a subset, and a page with zero detections can still contain many formulas. Source images and native glyphs remain available.
- Semantic step grading. Step groups are grounded source excerpts with candidate kinds; no expression/checker/rubric weight is invented.

Discrepancy rules flag malformed or changed decimals, Latin v/Greek nu substitution, missing derivative marks and strict-boundary changes. Passing these rules does not prove correctness. No confidence score is treated as a calibrated probability.

On the pilot, full-page PaddleOCR-VL misread a coefficient; the small formula recognizer recovered that coefficient in a control crop but lost a derivative mark elsewhere. Keep field-level review and allow a second parser to disagree. Do not automatically accept whichever model ran last.

PP-FormulaNet_plus-M is used as a targeted fallback after the first enrichment pass. An optional four-region control experiment can be run with `python -m pdfmeta.formula_probe --pilot <output> --runtime <runtime> --model PP-FormulaNet_plus-M`. This control crop is specific to the source hash in the fixture. The fallback job handles at most 80 flagged regions unless an explicit limit is supplied; scanned documents should use a separate full-page OCR job.

## Reuse and reproducibility

Models are loaded only by explicit OCR commands; the web app does not load them. Native page caches use source hash/parser/library versions. Hybrid checkpoints include rendered image hash, package versions, weight hashes, crop resolution and threshold. Formula crops are rendered at 240 DPI directly from the original PDF. Raw detector coordinates remain available alongside coordinates converted to PDF points.

The CLI Python modules can run from another OS/notebook with an explicit runtime directory; the PowerShell wrapper enforces E on Windows. For GPU runs, create a separate compatible environment, install the appropriate Paddle GPU wheel in place of the CPU wheel, and preflight hardware/CUDA. `pdfmeta.paddle_probe --device gpu:0` supports that selection, but GPU/Kaggle execution has not been tested in this pilot.

Keep source PDFs, generated crops, models, environments and outputs out of Git. Review/promote a separate versioned release only after content and checker capabilities are verified.

## Editable review and the 20-item authoring batch

The pilot now has a source-specific editorial configuration at `fixtures/pilot20-editorial.json`. Stems and answer crops were visually compared; seven items carry notes about assumptions, wording or source-solution issues. This is separate from academic approval.

```powershell
.\tools\pdf_metadata\run.ps1 -Action recheck
.\tools\pdf_metadata\run.ps1 -Action curate
.\tools\pdf_metadata\run.ps1 -Action enrich
.\tools\pdf_metadata\run.ps1 -Action review
```

Open `http://localhost:8787/review.html`. If a server is already listening on that port, use that page; do not start a duplicate process. The editor shows source images, editable stem/answer/solution, rendered LaTeX and individual OCR-region crops. KaTeX assets are copied from the existing frontend installation to the output on E; no CDN is used. Source text remains readable if these optional assets are unavailable.

Save a draft, flag an item for checking, or confirm that its stem/answer were compared to the source. A reviewer label is required. Editing a field resets its corresponding verification checkbox. Source comparison does not approve the mathematics or enable grading. Formula corrections are saved by their original OCR block ID, leaving model outputs unchanged.

Changes and full revision history live in `reviews/state.json`. Optimistic item revisions reject a stale save from another tab. Restarting the server/reloading the page preserves edits. If candidate content changes, old reviews are marked stale and must be checked again. Only one review server should write a pilot directory.

Click **Xuất bộ 20 bài** after saving edits. It regenerates:

- `exports/pilot20.authoring.jsonl`: 20 versioned authoring records with separate student view, draft AnswerSpec, draft MathSpec, source spans, solution/step candidates and review notes. The export is validated against `schemas/assessment-authoring.v1.schema.json`.
- `exports/pilot20.student-preview.json`: stem text and stem assets only; no answer/spec/solution keys. This remains an authoring preview, not a production exercise response.
- `exports/pilot20.report.json`: source checks, unresolved source issues, export revision and zero counts for academic approval/grading/publication.

The preset batch is specific to this source hash. Another PDF needs its own editorial selection/configuration. The generic extraction pipeline is unchanged. Câu 260 intentionally retains source answer 6 and a separate proposed correction 3: the source stem asks for abscissas but its solution computes ordinates. It must not become a grading reference until the mismatch is resolved by academic review.

### Clean authoring export (v2)

The authored export no longer embeds raw PDF step text. Symbol-font private-use characters are decoded only when the source glyph font supports the mapping. Adobe Symbol mappings are reused from the project's installed pypdf codec in `pdfmeta/_symbol_encoding.py`, with its Unicode copyright notice preserved. Historical private-use bracket pieces are represented by assigned Unicode assembly characters.

Unknown fonts are not assumed to use Symbol encoding: their characters become explicit `U+...` review markers. This matters because the same private code can mean different things in SymbolMT and MT-Extra. Normalized native excerpts are labeled lossy; fractions, superscripts, reading order and mathematical meaning still need source/LaTeX review.

- `exports/pilot20.authoring.jsonl`: machine-readable `assessment-authoring/v2` records, with normalized native excerpts, separate LaTeX candidates and raw-source references.
- `exports/pilot20.authoring.pretty.json`: the same records with indentation for inspection.
- `exports/pilot20.readable.md`: a readable question/answer/excerpt/LaTeX report.
- `exports/pilot20.raw-evidence.jsonl`: deliberately raw PDF evidence, not a grading input.

The v2 schema lives in `schemas/assessment-authoring.v2.schema.json`. Export rejects residual private-use/replacement characters in authored fields. Raw inputs and review history remain unchanged. Successful Unicode normalization does not approve a mathematical expression or enable grading.

### Layout-grounded reasoning-step trial

```powershell
.\tools\pdf_metadata\run.ps1 -Action steps
# http://localhost:8787/steps.html?question=152
```

Run after `enrich`. This lightweight stage uses saved native glyphs and OCR evidence; it does not load models, call inference APIs, or overwrite raw acquisition, review history, or the existing v2 authoring export. `Xem các bước giải` on the regenerated review page opens the trial for that question.

- `steps/questions.steps.jsonl` and `steps/questions.steps.pretty.json`: separate `solution-step-proposals/v1` records; the old `reference_steps` remain acquisition excerpts.
- `steps/report.json`: structural grounding results, candidate kind counts, unresolved/long-step flags and processing time. Counts and a structural PASS are not measured semantic accuracy.
- `steps.html`: read-only comparison of source images, normalized text, and OCR formula alternatives, including graphic-only table continuations across pages.

The proposed boundaries use baseline overlap to attach fractions, language cues to identify new ideas, and explicit top-level separators to separate a derivative calculation from solving its zero equation. Intervals such as `(a;b)` and decimal coefficients such as `0,003` are preserved. Every available normalized source character must be covered exactly once by a text slice. Inline splits can share a full source-line image, explicitly marked. Context crops cannot extend into another question.

The pilot's Câu 152 produces seven proposals without any question number or answer value in the parser. Other solutions can still remain composite or unclassified; the stage flags these for review. Previous-step links record presentation order only. `MODEL_SETUP` is an acquisition category and does not expand the production core's supported rubric kinds. Conditions explicitly found in source text are retained, while missing assumptions such as the sign of `c` remain review notes. No checker, score, rubric weight, academic approval or publication is inferred.

Rerun `steps` after changing formula corrections or regenerating candidates. Do not import this experimental artifact directly into the grading core. See `docs/pdf-metadata-step-segmentation-2026-11-02.md` for the measured trial and limits.

## Gemini review and reusable corpus pipeline

The local extraction stages above remain offline. Only the explicit `gemini-review`, `corpus-run` and `pipeline` actions send selected source images/metadata to Google. `gemini-preflight` lists accessible models without sending document content. Configuration is `tools/pdf_metadata/.env`; `.env.example` is the shareable template, while the actual secret file is ignored by Git. API keys stay out of frontend code, prompts, checkpoints and logs.

```powershell
# 1. Check credentials/model access; no document inference.
.\tools\pdf_metadata\run.ps1 -Action gemini-preflight

# 2. Review existing extracted questions with the matching source crops.
.\tools\pdf_metadata\run.ps1 -Action gemini-review -Questions '151,152,153,154,158,213,260' -Limit 7 -MaxCalls 10 -MaxTotalTokens 150000

# 3. Inventory/plan the entire ZIP for the explicit Gemini route, without inference.
.\tools\pdf_metadata\run.ps1 -Action corpus-plan -Provider gemini -InputPath 'E:\HocTap\Hackathon-SGU2026\Coach_Learning\data\Toan12.zip'

# 4. Process the next bounded set of windows. Repeat to resume.
.\tools\pdf_metadata\run.ps1 -Action corpus-run -Provider gemini -Limit 10 -MaxCalls 12 -MaxTotalTokens 200000

# Or plan + run a bounded set in one command for another PDF/ZIP/directory.
.\tools\pdf_metadata\run.ps1 -Action pipeline -Provider gemini -InputPath 'E:\materials\new-pdfs' -Output 'E:\pdf-output\new-corpus' -Limit 3 -MaxCalls 5

# Read-only corpus viewer, localhost:8788/review.html.
.\tools\pdf_metadata\run.ps1 -Action corpus-review -Provider gemini
```

The pilot viewer is `http://localhost:8787/gemini/review.html` when the existing authoring server is running. Corpus viewing is separate because its output root is different. HTTP checks do not establish visual quality. If the pipeline generated the review files but the browser tool is disabled, inspect the source images and JSON separately and leave browser validation explicitly pending.

### What happens in the corpus route

1. Hash/inventory input PDF files. ZIP entries are copied to E under their content hash; archive paths are never trusted as extraction destinations. Original sources are unchanged.
2. Plan windows with two owner pages and one context page on each side (at most four images per request). Each page belongs to exactly one owner window. Context helps finish a question starting on an owner page; questions starting outside that window are not exported again.
3. Render selected pages at 160 DPI and retain native text as a lossy helper. Image-only pages use the same visual route. No Paddle model is loaded by this route; it is the multimodal fallback for the mixed corpus, separate from the pilot's native/Paddle question extraction.
4. Gemini extracts question/knowledge units, printed source numbers, options, source answer/solution, candidate reasoning steps and issues. It must separate visible source text from proposed corrections and added assumptions.
5. Local validation checks strict JSON, owner-page boundaries, evidence IDs, step order and publication gates. This verifies structure/provenance, not general mathematical truth or complete source coverage. Missing answers/solutions, MCQ/true-false leakage risks, incomplete boundaries, uncertain steps and duplicate content go to a queue.
6. Export versioned staging with source hashes, stable job IDs and images. `AI_REVIEWED` means an AI review ran and local gates passed; academic/grading/publication remain unapproved. No production database, grading score, rubric or mastery state is mutated.

### Outputs and limits

- Pilot: `.tmp/pdf-metadata-pilot-v1/gemini/questions.reviewed.jsonl`, readable pretty JSON, `review-queue.json`, `review.html`, `report.json`, `runs/` and `usage.jsonl`.
- Corpus: `.tmp/toan12-gemini-corpus/plan.json`, `active-jobs.json`, `staging/content.jsonl`, `staging/content.pretty.json`, `staging/review-queue.json`, `review.html`, `report.json`, `runs/`, `pages/` and immutable hashed `jobs/` checkpoints.
- Contracts: `gemini-question-review.v1.schema.json`, `gemini-window-extraction.v1.schema.json`, `math-content-staging.v1.schema.json`. Provider requests use a portable schema subset (explicit enum types); the full strict schemas are enforced locally.
- `-Limit` bounds new corpus jobs. Complete cached jobs do not consume that limit. `-MaxCalls` bounds generation attempts including HTTP retries. `-MaxTotalTokens` is a stop threshold based on returned usage plus output reservation, **not a hard billing cap**; input costs and timed-out requests can be unknown. Token limits reset per invocation; there is no automatic unlimited loop.
- 429/temporary server errors have bounded retries. Timeouts are recorded as unknown remote state and are not automatically replayed. Review failures or unknown remote jobs require `-RetryFailed` after checking their state; this can incur another charge. Never treat a timeout as proof of zero usage.
- A changed image, package, schema, prompt, model or adapter creates a new cache key. Raw old jobs remain; active staging exports only the current corpus generation, avoiding mixed-model duplicates. A single-writer lock prevents competing processes. After a crash, verify the recorded PID is stopped before removing only that output's `.writer.lock`; unknown in-flight calls still need explicit retry.
- `-Revalidate` rechecks a failed saved corpus response locally without resending images. Context-page units returned despite the prompt are excluded from staging and retained in `normalization_audit`; unknown/out-of-range page references still fail. `-RetryFailed` has a different meaning: it may request new inference and incur usage again.
- Full-window output truncation or a question longer than the available context is not silently accepted. Retry with a smaller owner window in a **new output directory**, e.g. Python `pdfmeta.corpus plan --core-pages 1 --overlap 2`, or review the flagged source. The bounded native pilot assembler is not claimed to parse all layouts.

Use `-Documents '<document_id>'` or `-Jobs '<document_id>:p0003,...'` from `plan.json` for representative tests. `-SamplePerDocument` interleaves documents to avoid testing only the first PDF. The Python entry points run on other hosts with explicit paths/env secrets; PowerShell enforces E-drive outputs on this Windows machine. No GPU/Kaggle execution or full-corpus quality benchmark has been claimed.

See `docs/pdf-metadata-gemini-pipeline-2026-11-02.md` for the tested cases, known model failures and rollout instructions.

## Local collection of questions with printed solutions, across all Toan12 chapters

`collect_solved.ps1` is the source-image collection route. It inventories every
PDF in a ZIP/folder, keeps its own page cache and processes documents sequentially.
It does not call Gemini or Qwen, approve mathematics, build grading rubrics or
write to the production database. The established pilot/math-transcription route
is separate.

```powershell
# A new collection. Keep source, model cache and output storage on E.
.\tools\pdf_metadata\collect_solved.ps1 `
  -InputPath 'E:\HocTap\Hackathon-SGU2026\Coach_Learning\data\Toan12.zip' `
  -Archive 'E:\HocTap\Hackathon-SGU2026\Coach_Learning\data\Toan12.zip' `
  -Work 'E:\CoachLearningPdf\solved-toan12' `
  -Output 'E:\CoachLearningPdf\solved-toan12\export' `
  -Storage 'E:\HocTap\Hackathon-SGU2026\Coach_Learning\.tmp' `
  -PdfPython 'C:\Users\ADMIN\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
```

Rerun the same command to resume. To resume an existing `profile.json` without
inventorying/extracting the ZIP again, omit `-InputPath`. A single unfamiliar PDF
needs `-Chapter integrals` (or another listed chapter); an unknown topic is not
silently assigned. This adapter currently groups derivative applications,
integrals, grouped statistics and conditional probability.

Outputs include `Toan12_Cau_hoi_co_loi_giai.pdf`,
`cau-hoi-co-loi-giai.metadata.jsonl` (with collection PDF page mappings),
`index.html`, `report.json`, `review-queue.jsonl`, and
`page-review-queue.jsonl`. Supply `-PdfPython` with ReportLab and Pillow to export
the PDF; otherwise metadata is saved and PDF export is explicitly pending.
That Python also needs pypdf for the automatic structural verification step.
The PDF uses JPEG quality-94 derivatives to limit file size; the metadata/viewer
retain the original PNG source crops for comparison.

Question IDs bind the PDF hash to the printed number and occurrence, since book
sections restart numbering. The count is source occurrences, not deduplicated
unique problems. Each exported question retains its real PDF name/hash, physical
page, PDF-point bbox, source block IDs and crop hash. ZIP identity is recorded
separately. Two detected source columns are cropped separately and uncertain
cross-column regions go to the review queue.

A printed “Lời giải” followed only by writing lines does not qualify as a solved
item. Explicit following-section labels detach unrelated lesson material; removed
blocks remain in the document audit. Missing solutions, uncertain layouts, OCR
failures and pages without accepted pairs remain accounted for in queues. Pairs
whose question, answer or solution spans depend on unverified OCR are also held for source review,
since a missed question heading can attach the next exercise as a solution. Text is
only a lossy search helper; source images preserve the printed math. This does not
establish complete extraction recall or mathematical correctness.

`controller.json` and per-document `worker.log` show progress. The worker uses
BelowNormal priority and the local OCR adapter uses three CPU threads. Page/image
hashes and adapter identity are checked for resume. Any failed document blocks
the combined export instead of silently disappearing.

For independent structural verification after export, run `collection_check.py`
with `--metadata <output>/cau-hoi-co-loi-giai.metadata.json` and
`--report <output>/verification.json` using Python with pypdf. It checks PDF page
mapping, bookmarks, image hashes, bounds and overlaps. Visual QA and mathematical
review are separate checks.

### Readable metadata

JSONL keeps one complete question on each line for streaming imports. To inspect
the same data, open `metadata.html` in the local artifact viewer. It separates
question, solution, source pages and review state; source images and full JSON
have their own tabs. It supports chapter/document filters, a download for one
question, and a two-space-indented JSON array for the full collection.

```powershell
$env:PYTHONPATH = 'E:\HocTap\Hackathon-SGU2026\Coach_Learning\tools\pdf_metadata'
& '.\.tmp\pdf-pipeline-runtime\.venv\Scripts\python.exe' -B -m pdfmeta.paired.metadata_readable `
  --input 'E:\HocTap\Hackathon-SGU2026\Coach_Learning\.tmp\pdf-jobs\4ebd40c425c242baa4faf416\corpus\cau-hoi-co-loi-giai.metadata.jsonl'
```

This writes `cau-hoi-co-loi-giai.metadata.pretty.json`, `metadata.html`, a compact
`metadata-catalog.json`, individual JSON files under `metadata-records/`, and
`metadata-format.json` with source/output hashes. Only the selected record loads
in the viewer; opening it does not load the entire JSON array or the large PDF.
The formatting stage uses no inference, preserves every original field value,
and never upgrades review/grading states. Both the metadata-only workflow and
the standalone PDF exporter now generate this presentation automatically.

The readable viewer detects unmapped private-use/replacement characters. For a
damaged record it shows the source crops first and collapses the damaged helper
text. The JSON download still contains the original values. This is a display
safeguard; absence of these characters does not establish correct math layout.

### Recover formula candidates from the original source

`pdfmeta.paired.math_recovery` adds a separate, bounded recovery trial for 1–40
explicit collection numbers. It reopens the hash-matched original PDF with real
font/glyph coordinates, finds assignment/integral anchors, includes floating
fraction glyphs, and reads 288-DPI formula crops with local PP-FormulaNet_plus-M.
PDFium helper text is never passed to the formula recognizer. Use installed local
weights under the E-drive runtime; the stage refuses missing weights rather than
starting a download. CPU inference uses three threads and BelowNormal priority.

```powershell
$env:PYTHONPATH = 'E:\HocTap\Hackathon-SGU2026\Coach_Learning\tools\pdf_metadata'
$env:PYTHONUTF8 = '1'
& 'E:\HocTap\Hackathon-SGU2026\Coach_Learning\.tmp\pdf-pipeline-runtime\.venv\Scripts\python.exe' -B -m pdfmeta.paired.math_recovery `
  --input 'E:\HocTap\Hackathon-SGU2026\Coach_Learning\.tmp\pdf-jobs\4ebd40c425c242baa4faf416\corpus\cau-hoi-co-loi-giai.metadata.jsonl' `
  --plan 'E:\HocTap\Hackathon-SGU2026\Coach_Learning\.tmp\toan12-local-corpus\plan.json' `
  --output 'E:\HocTap\Hackathon-SGU2026\Coach_Learning\.tmp\pdf-jobs\4ebd40c425c242baa4faf416\latex-recovery-20261103' `
  --runtime 'E:\HocTap\Hackathon-SGU2026\Coach_Learning\.tmp\pdf-pipeline-runtime' `
  --numbers 1461 `
  --katex 'E:\HocTap\Hackathon-SGU2026\Coach_Learning\frontend\node_modules\katex\dist'
```

Outputs: `formula-candidates.json`, true-font `font-pages/`, source crops, an OCR
cache bound to image/weight/package/adapter hashes, `report.json`, and an offline
KaTeX `review.html` when `--katex` is supplied. There are no cloud calls. The
canonical metadata is unchanged and academic/grading states remain pending.

Coverage is deliberately `PARTIAL_ANCHORED_FORMULAS_ONLY`. Standalone
non-assignment expressions, full Vietnamese prose, tables, figures, unrecognized
fonts, and scanned pages need additional extraction paths. Native/model agreement
checks transcription consistency; it does not verify mathematical truth or approve
an item for grading. Different choices must remain different even when some are
mathematically wrong. Do not promote an OCR-only reading because it renders in
KaTeX or because algebraically equivalent output can be parsed.

### Chapter-balanced text and LaTeX trial

`transcribe_corpus.ps1` processes a fixed, reproducible sample from paired-corpus
metadata. The current 100-record trial uses 25 records per chapter, round-robins
over all 12 contributing PDFs, and fixes 40 evaluation records before inference.
The inventoried PDF with no selected solved items is not silently counted as a
contributing source. This is a balanced diagnostic sample, not a corpus-weighted
accuracy estimate or a manually transcribed gold dataset.

```powershell
& 'E:\HocTap\Hackathon-SGU2026\Coach_Learning\tools\pdf_metadata\transcribe_corpus.ps1' `
  -Metadata 'E:\HocTap\Hackathon-SGU2026\Coach_Learning\.tmp\pdf-jobs\4ebd40c425c242baa4faf416\corpus\cau-hoi-co-loi-giai.metadata.jsonl' `
  -Plan 'E:\HocTap\Hackathon-SGU2026\Coach_Learning\.tmp\toan12-local-corpus\plan.json' `
  -Output 'E:\HocTap\Hackathon-SGU2026\Coach_Learning\.tmp\pdf-jobs\4ebd40c425c242baa4faf416\transcription-100-20261103' `
  -Count 100 -Workers 2 -Open
```

All models and environments stay on E. No new weights are downloaded. There are
at most two resident OCR workers, three CPU threads each, BelowNormal priority.
Native unambiguous single-baseline notation avoids unnecessary image inference.
Complex formulas use local PP-FormulaNet_plus-M and S. Their notation agreement,
source digit/sign preservation, source structure guards and local KaTeX syntax
checks control whether the main Markdown shows a formula or its source crop.
Agreement remains a draft consistency check, never academic approval. Tables,
figures, unmapped rows and unresolved formula regions retain source images.

Every record has a source/checkpoint/pipeline identity. Rerunning the same command
reuses completed matching records; one failed question gets a failure record and
does not discard the other questions. Changing input, code, model weights or
library identity invalidates the relevant record checkpoint. The source corpus
is never overwritten. Concurrent publishers use distinct temporary files and
retry brief Windows reader locks.

Outputs include `metadata.transcribed.draft.jsonl`, its `.pretty.json` counterpart,
one JSON file per record, source/formula PNGs, `selection.json`, runtime telemetry,
and a live `review.html`. The structured draft keeps `parts.question.markdown`,
separate choices where one A–D set is recognized, `parts.solution.markdown`,
explicit answer text, original raw text and source spans. Repeated choice groups
remain inline, preserving their source order. The schema requires pending review,
unassessed grading support and `publishable=false`.

Qwen local reviews the fixed evaluation subset as text-only advisory triage; its
results explicitly say that source images were not provided. It cannot clear a
truncated input or mark content academically approved. `evaluation-40.json`,
`reference-checks.jsonl` and `quality-summary.json` distinguish syntax, held image
regions, model disagreements, source glyph warnings and numeric equality
inconsistency candidates in solutions. False answer alternatives are preserved.
Full formula recall, full transcription accuracy and whole-solution mathematical
correctness are not established by this trial. These drafts must not be directly
ingested into the grading core.

If a model returns an invalid/oversize output, `transcript_rescue` retains the
failed question as `SOURCE_IMAGE_ONLY_EXTRACTION_FAILED`, with original images,
the failure record/hash and `math_transcription_completed=false`. This is counted
separately from transcribed drafts. It performs no new inference and does not
claim a known total for model calls made by the failed attempt. A normal resume
retries extraction for this record. Failed Qwen responses can be retried with
`transcript_triage --retry-failed`; the old failed response is retained in history.
