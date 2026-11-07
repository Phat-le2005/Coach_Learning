> Consolidated checkout: use [LOCAL_SETUP.md](../../LOCAL_SETUP.md) for current setup. Absolute worktree paths/QA sessions below are historical; private fixtures are optional and not distributed.

# OCR V2 Experimental — local MathCanvas vertical slice

This is a development/QA experiment. It does not replace **Trích xuất trang**, write solution steps, update the batch journal, or call the evaluator. Layout regions, recognition scopes, transcription units and grading steps remain distinct.

Dataset generation, visual ground-truth annotation and six-profile Oracle comparison are now available at `/ocr-v2-lab/evaluation`. See [EVALUATION_README.md](EVALUATION_README.md) for the Vietnamese workflow, commands, licensing and measured limitations. The original MathCanvas lab remains available.

## Current checkout and input

Implementation lives in `D:\SGU\DuAn\Coach_Learning_OCR_SLICE34`, branch `feat/tri-ocr-core-transcription-slice`, based on `80140cc`. Existing uncommitted05.4 files are retained. The ordinary `Coach_Learning` checkout is a different branch; do not reset or switch it to run this experiment.

The handoff found locally is `D:\Downloads\CoachLearning_OCR_Handoff_2026-11-03.zip` (without `(1)`). SHA-256: `b28ff8055dacd80c619d918f9b49843d1043b0343f0857cee29c1b2a420e7a74`; all76 manifest entries matched. Its four captures are DEV/DIAGNOSTIC, without independently verified transcripts. No checkpoint or handwriting is committed.

## Setup on Windows / PowerShell

Use Python3.12 and the existing frontend dependencies. A separate venv/cache is created under `.tmp/tri-ocr-v2-runtime`; the application backend environment is not modified.

```powershell
cd D:\SGU\DuAn\Coach_Learning_OCR_SLICE34
powershell -ExecutionPolicy Bypass -File tools/ocr-v2-lab/setup.ps1 -Python D:\SGU\DuAn\Coach_Learning\backend\.venv\Scripts\python.exe
node tools/ocr-v2-lab/manage.cjs start
```

Nếu backend QA đã tắt sau khi khởi động lại máy, bật Docker Desktop và chờ container PostgreSQL hiện có healthy; không tạo lại database/volume. Sau đó chạy:

```powershell
cd D:\SGU\DuAn\Coach_Learning_OCR_SLICE34\frontend
npm run test:compile
cd ..
node tools/ocr-v2-lab/qa-backend.cjs start
node tools/ocr-v2-lab/manage.cjs start
```

`qa-backend.cjs` dùng cấu hình QA private đang có, kiểm tra database bằng `verify-safety` trước khi chạy, chỉ cho `APP_ENV=test` và database QA riêng. Không seed/tạo account/attempt hay thay dữ liệu. Cổng8000 đang bận sẽ bị từ chối và service hiện có được giữ nguyên. Thiết lập mới cần backend dependencies và database/account QA đã được cấp sẵn; script không tự tạo chúng.

Setup downloads dependencies and official PaddlePaddle weights. Inference then uses the local cache; the worker blocks external socket connections. No ink is uploaded to a cloud OCR provider. PP-DocLayout-M is Apache2.0, pinned to official revision `7dbfcce3154a55776dc71ca026a4a2a8388dad8d`; every downloaded file has a SHA-256 manifest, verified on loading. Runtime uses CPU, three threads and MKLDNN disabled, following the existing PDF tools' loading pattern. It does not use the PDF/question content.

The manager checks ports and chooses an available one starting at8014 for the sidecar and3014 for the frontend. It prints the actual URL. Existing services on3000/8000 are preserved. This machine's authorized QA backend is already at `http://127.0.0.1:8000`; another setup may set `$env:API_BASE_URL` before starting. Use a development/QA backend and account that you are authorized to access. This tool does not create/seed users or databases. Credentials remain in the existing gitignored QA configuration, not in this document or exports.

The sidecar requires a local random bearer token stored at `.tmp/tri-ocr-v2-runtime/service-token.txt`. The manager passes it only to the sidecar and Next server. Browser code never receives the token. The same-origin Next proxy checks signed authentication, origin, flag and body size; the sidecar binds only127.0.0.1 and accepts no filesystem path/URL input. Its75-second worker deadline terminates a stuck worker; the browser records errors and uses an explicitly labeled fallback.

## Viết và kiểm tra ngay

1. Mở URL mà manager in ra, thông thường là `http://localhost:3014/ocr-v2-lab`, rồi đăng nhập bằng tài khoản QA local đang có.
2. Viết trực tiếp bằng chuột/touch/stylus trên **MathCanvas** bên trái. Đây là component canvas thật của ứng dụng, giữ tọa độ chuẩn và stroke IDs. Trang lab chỉ giữ nét trong bộ nhớ trình duyệt: **không lưu nét hay lời giải xuống database**.
3. Bấm **Thử OCR V2 toàn trang**. Xem trạng thái detector, nhãn/score thô và các box đánh số. Click box hoặc đơn vị bản chép để highlight các nét được lấy. Mở phần coverage/orphan để kiểm tra IDs.
4. Chế độ mặc định mới là **Hybrid: geometry + Layout-M**. Geometry tạo scope độc lập; box/nhãn model chỉ bổ sung bằng chứng. Detector gán `doc_title` không còn tự chặn một scope có bằng chứng toán phù hợp. TEXT/UNKNOWN thiếu bằng chứng toán vẫn unresolved/manual. Các giả thuyết được hiển thị riêng: box tím là model, scope xanh là geometry; chọn một candidate để xem membership và lý do gộp/tách. Candidate cạnh tranh không sở hữu nét lần nữa và không tự tạo thêm lượt inference.
5. Scope MATH có bằng chứng phù hợp được chạy CoMER thử tự động; raw output luôn cần review. Chỉ có output LaTeX không chứng minh đó là toán hay chép đúng. Muốn chỉ định lại, đổi **Định tuyến** thành MATH rồi bấm **Đọc lại scope toán**. Adapter05.4 hiện chạy một inference với cùng CoMER/`toModelStrokes`/vendor preprocessing, giữ raw trước repair, output sau repair, beams và tensor. Giới hạn12 lần gọi/action; count inference xác minh tách riêng abstention/runtime error. Trường export `wrapperLatex` được giữ cho tương thích, chứa selected text qua cùng kiểm tra KaTeX; không còn gọi wrapper lần thứ hai.
6. Khi thiếu mũ/cận hoặc gộp nhầm, bật **Khoanh nét trong preview**, hoặc click từng nét. Chọn loại nội dung, bấm **Tạo scope từ nét đã chọn** / **Gán nét vào scope đang xem**. Có thể chọn nhiều đơn vị để gộp, hoặc tách bằng vạch ngang do bạn chỉ định. Chỉ scope thử nghiệm thay đổi; bản review/correction trước được giữ trong lịch sử và export.
7. Sửa bản chép, xem KaTeX, xác nhận từng đơn vị. Với cấu trúc, chọn ít nhất hai root units rồi chọn rõ SYSTEM/ALTERNATIVES/FRACTION/INDEPENDENT; UNKNOWN chưa được duyệt. Container không cần chuỗi LaTeX giả. Sửa child sẽ hủy xác nhận parent phụ thuộc. Xác nhận thứ tự đọc riêng bằng các nút Lên/Xuống.
8. Chạy lại CoMER sau correction: raw mới được thêm, nội dung đã sửa vẫn giữ nguyên. Chạy lại perception giữ scope đã review, lưu đề xuất mới để đối chiếu. Viết thêm nét hoặc đổi page/revision làm approval cũ **STALE**, hủy trạng thái duyệt hiện hành và khóa xác nhận cho đến lượt chạy mới.
9. Tick đồng ý lưu/xuất trên máy rồi xuất JSON/CSV/PNG. Package có source ink, ảnh trang/crop, raw regions, mapping, raw/corrected content, IR và lịch sử. Không có cookie, token, `.env` hoặc đáp án đề. File chứa chữ viết tay; chỉ lưu/chia sẻ khi có sự đồng ý.

To use ink already in a saved solution workspace, open that workspace on the experimental frontend and click the floating **Thử OCR V2 toàn trang** button. It receives the current in-memory page and source revision directly, without a save/submit callback. Ordinary workspace writing still has its existing ink autosave; the experimental action itself does not save or grade. The standalone lab is the zero-database-mutation route for writing experiments.

## Comparisons and new data

Import existing `OcrEvalCaptureV1` JSON through **Import capture**. Select HANDOFF_CAPTURE for the four handoff examples, SYNTHETIC_INK for generated/replayed ink, and LIVE_INK for new manual writing. Choose DEV or HOLDOUT, plus an optional pseudonymous writer ID. Do not tune on HOLDOUT. Use15–30 new pages covering two nearby equations, columns, fractions/bounds, braces/brackets, Vietnamese accents and mixed lines; add writers when available.

The independent annotation controls let you select source strokes and enter a literal label **before viewing OCR**. The independent-label checkbox is a declaration by the human annotator, not a software guarantee of ground truth. Model output and analyst drafts are not promoted to HUMAN_VERIFIED. Existing `/ocr-diagnostics` also supports separate capture/ground-truth import and validation. All accuracy fields remain NOT_MEASURED unless an independent labeled evaluation is actually performed; observing a large box or passing software tests is insufficient.

Compare **Layout-M cũ** (the original box/label/overlap gate), **V2 baseline**, **Geometry candidates** (independent grouping without model-label evidence), and **Hybrid** on the same source. V1 is also retained. V1/V2 assume math and can misroute prose, so they remain baselines. Hybrid keeps uncertain geometry unresolved and preserves raw proposals when the detector fails. Its bounded candidates retain overlap/boundary evidence; active sibling ownership is unique. No all-page rescue merge is used to inflate recall. Delimiters spanning rows remain relation proposals requiring review; no bbox becomes a grading step. A multi-line page can still be ambiguous or grouped incorrectly: inspect membership and use manual repair.

Import also accepts a lab `ocr-v2-package.json` up to20MB, extracting only its active source ink. Archived predictions are not imported as answers/GT. An exported history may include earlier pages; review privacy before sharing. New native14/71-stroke remediation evidence is local in `.tmp/tri-ocr-v2-remediation/`.

## Commands actually used for verification

```powershell
cd D:\SGU\DuAn\Coach_Learning_OCR_SLICE34\frontend
npm test
npm run typecheck
$env:NEXT_DIST_DIR='.next-ocr-v2-production'
npm run build
cd ..
& .tmp\tri-ocr-v2-runtime\venv\Scripts\python.exe tools/ocr-v2-lab/test_service.py
node tools/ocr-v2-lab/verify.cjs
# Remediation comparison: existing real captures + optional user14/71 recovered inputs
node tools/ocr-v2-lab/verify_remediation.cjs
```

The browser runner uses Chrome, the actual Next application, existing QA authentication, the real loopback detector and actual bundled CoMER/WASM. It requires the four consented captures under `.tmp/tri-ocr-root-cause/` and the existing gitignored `.tmp/tri-ocr-e2e/.qa-e2e.env`. It blocks external browser requests and application mutation routes, except auth and the read-only inference POST. No OCR response is mocked. Test fixtures used only for mapping/IR safety are explicitly synthetic, with no recognition accuracy claim.

Evidence is local in `.tmp/tri-ocr-v2-e2e/`, including source/model manifests, per-profile packages, raw detections, scope mapping, model results, comparison, screenshots and `RESULTS.md`. See [DECISION.md](DECISION.md) for measured outcomes and blockers.

## Stop / troubleshoot

```powershell
node tools/ocr-v2-lab/manage.cjs stop
# Chỉ khi đã dùng qa-backend.cjs để bật backend riêng:
node tools/ocr-v2-lab/qa-backend.cjs stop
```

Stop checks recorded process identity and terminates only the manager's frontend/sidecar process trees. It does not stop the existing backend, database or user's3000 frontend, and does not delete model cache/captures.

- **404:** both server `OCR_V2_EXPERIMENTAL=1` and client `NEXT_PUBLIC_OCR_V2_EXPERIMENTAL=1` must be set before Next dev starts; the manager sets them. Production always returns404 even if those flags are set.
- **401 / login:** sign in to the experimental origin. It uses the application's existing signed session; no public debug bypass is added.
- **SIDECAR_UNAVAILABLE:** check `.tmp/tri-ocr-v2-e2e/sidecar.log` and `.tmp/tri-ocr-v2-runtime/worker.log`, and restart with the manager. Geometry/manual routes remain usable.
- **Pandas/numpy import error:** rerun setup with the pinned requirements; numpy1.26.4 and pandas2.2.3 are intentionally pinned together. The initial unpinned pandas3 environment failed and was corrected before detector inference validation.
- **V3:** official weights revision `241f8bdfc77a7c7bee915a5057aaee58c235a8d3` can be cached using setup `-WithV3`, but the pinned PaddleX3.3 runtime does not register PP-DocLayoutV3. The observed failure is BLOCKED_UNSUPPORTED_RUNTIME, not a model-quality result. Upgrading that optional adapter needs a separate compatibility validation; M/manual/geometry work without it.
- **TEXT:** ANZ's OCeanpaRk-small-v1 is gated and lacks usable public weight/license access in the checked metadata. A second public Vietnamese checkpoint exists but has not had its runtime/diacritic fidelity verified here. Neither is enabled. TEXT uses literal manual transcription, not fake HTR or CoMER.
- **Unsupported graph LaTeX:** this panel only checks KaTeX rendering; Math View graph-parser support is separate from OCR fidelity.

The current build does not establish handwritten-layout accuracy, Vietnamese HTR accuracy, automatic mathematical structure understanding or evaluator readiness. Projection stays `PREVIEW_ONLY`, `steps=[]`, `submitPayload=null`, `readyToSubmit=false` after transcription approval too.

## Optional Uni-MuMER local recognizer (research only)

The existing Lab offers **CoMER** (unchanged default), **Uni-MuMER Qwen3.5-2B Q4_K_M**, and **Compare**. Both receive the same selected PEN IDs; model-specific preprocessing differs. Compare keeps the CoMER draft and displays Uni raw output/crop separately. Neither confirms content or submits grading steps. Production gates disable these research routes.

Run from the research worktree in PowerShell. Reuse the existing isolated Python3.12 venv with psutil7.0.0/Pillow11.2.1; no global Python/CUDA/driver install:

```powershell
$ocrPython = '.tmp/tri-ocr-v2-runtime/venv/Scripts/python.exe'
& $ocrPython tools/ocr-v2-lab/unimumer_setup.py
& $ocrPython tools/ocr-v2-lab/unimumer.py start --profile hybrid --layers 12
& $ocrPython tools/ocr-v2-lab/unimumer.py health
node tools/ocr-v2-lab/manage.cjs start
```

Setup downloads only the pinned Q4_K_M model, Q8_0 vision projector and official Windows llama.cpp CPU/CUDA12.4 binaries. Downloads require Internet; inference uses127.0.0.1 only. Hashes/revisions/licenses are recorded in `.tmp/tri-unimumer-lab/download-manifest.json`. Models stay ignored, outside frontend/public. No BF16 model downloaded. The lifecycle helper uses the two Python packages above, already pinned in Lab requirements.

Open the URL printed by the manager (currently `http://localhost:3014/ocr-v2-lab`), sign in with your authorized QA account, write or import ink, choose Geometry/Hybrid and a recognizer, then **Thử OCR V2 toàn trang**. Click a scope to inspect raw results, crop, preview, timing and IDs. Correct/confirm after comparing with the writing. Export uses the existing consent checkbox and preserves raw/model/human evidence. Uni errors never masquerade as CoMER predictions. CoMER mode works with Uni stopped.

```powershell
# Existing frozen native/MathWriting diagnostic inputs, not a new HOLDOUT:
& $ocrPython tools/ocr-v2-lab/unimumer_benchmark.py --smoke --name smoke-local
& $ocrPython tools/ocr-v2-lab/unimumer_benchmark.py --name benchmark-local
node tools/ocr-v2-lab/unimumer_report.cjs
# Arbitrary local PNG, no target LaTeX argument:
& $ocrPython tools/ocr-v2-lab/unimumer.py infer .tmp/tri-unimumer-lab/inputs/user-equation-14.png --prompt strict --output .tmp/tri-unimumer-lab/manual-result.json
# Stop only the identity-checked Uni process:
& $ocrPython tools/ocr-v2-lab/unimumer.py stop
```

To change profile, stop first. `--profile cuda --layers 12` puts vision on GPU and was faster but left little VRAM headroom. `--profile hybrid --layers 8` reduces GPU pressure; `--profile cpu` is the verified CPU fallback. Single slot/context2048/cache RAM0 avoids default large allocations. The Uni helper preserves existing Lab/backend/sidecar services. GPU layers and projector backend are confirmed from runtime logs.

Evidence and eight research reports are in `.tmp/tri-unimumer-lab/`. `BENCHMARK_RESULTS.md` separates native unlabeled, MathWriting authoritative, partial automatic scopes and typeset error checks. The small DEV result does not justify replacing CoMER in production. MathWriting source license is CC-BY-NC-SA-4.0; it is not unrestricted team data. Uni model/quantization metadata is Apache-2.0; llama.cpp is MIT and packaged CUDA terms apply.

UI verification: `node tools/ocr-v2-lab/verify_unimumer.cjs` uses the existing isolated QA environment and actual browser/model inference. Missing QA credentials block only that harness. Keep runtime credentials private; share selected Lab evidence exports instead of the entire private runtime directory.
