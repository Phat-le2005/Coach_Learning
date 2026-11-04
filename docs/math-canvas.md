# Math Canvas

The 2026-10-28 [Math View 3D extension](math-view-3d.md) adds automatic recommendations, implicit equations, parameter animation and labeled coordinate axes. The supported-function boundary and validation results below describe the earlier Math Canvas revision; consult the extension for current capabilities and limits.

Math Canvas extends the existing student handwriting workspace. Open `/student/attempts`, start or reopen a lesson, and select **Khoanh vùng**. Draw a closed freehand region around pen strokes. Selected strokes are highlighted and sent to the existing browser handwriting recognizer. The selection does not create additional ink or delete strokes.

Compare the recognition suggestion with the original ink, correct the formula if necessary, and choose **Phân tích công thức**. Both **View 2D** and **View 3D** actions appear independently of the formula's classification. Direct formula input is available when recognition is unavailable. Examples are explicitly labeled and are never substituted for OCR output.

## Supported functions

- Explicit curves `y=f(x)` and surfaces `z=f(x,y)`, including `z=x²+y²` and `z=a*x²+b*y²`.
- Arithmetic, powers, parentheses, implicit multiplication, numeric constants, `pi`, `e`, and single-letter parameters.
- `sin`, `cos`, `tan`, `sqrt`, `abs`, `exp`, `log`, and `ln` with parentheses. Logarithms are natural logarithms.
- Common LaTeX fractions, square roots, exponents, and Unicode squared/cubed symbols.
- Up to six formula parameters, each between -5 and 5. The display domain is symmetric, adjustable from ±1 to ±10.
- The outer transform is `F(x,y)=s*f(x-h,y-k)+v`; for curves, the second argument is omitted.

Implicit equations, vector fields, parametric surfaces, inequalities, and arbitrary LaTeX commands are outside this version. Expressions use a bounded parser; no JavaScript evaluation or symbolic-code execution is used. Undefined/non-finite values are omitted from sampled geometry, with discontinuity guards. These plots are exploratory visualizations, not proofs or automated grades.

## Interaction and persistence

Function classification and presentation are separate. For `y=1-x²`, **View 3D** places the same curve in space at `z=0`, with orbit and zoom enabled. It does not rewrite the formula as a two-variable surface. Switching views preserves the parameters and outer transforms.

For one-variable functions, **Mở rộng thành bề mặt → Tạo bề mặt kéo dài** explicitly extends `y=F(x)` along the free z axis. For `z=f(x,y)`, **View 2D · Mặt cắt** shows `z=F(x,y₀)`; the `Vị trí mặt cắt y₀` slider chooses the global y coordinate of the cross-section. The mode and slice coordinate are recorded in the existing settings JSON, so no additional database migration is needed. Older snapshots retain their original default view.

Drag the 3D viewport to orbit and use the wheel or pinch to zoom. In 2D, drag to pan. **Đặt lại góc nhìn** restores the initial view, or the recorded camera when reviewing a saved lesson.

**Lưu vào bài học** persists a snapshot linked to the existing solution attempt. It contains:

- Normalized expression and the original/confirmed formula text.
- Formula parameters, outer transformations, domain, camera position, and camera target.
- Display mode (`AUTO`, `2D`, `3D`, or `EXTRUDED`) and cross-section coordinate when applicable. The snapshot `dimension` still describes the mathematical function, not the camera mode.
- Page index, server ink revision, and an immutable copy of the selected pen strokes.
- Student notes and, when available, the server-generated AI explanation.

Snapshots are append-only, bounded to 50 per attempt, and idempotent by client action ID. A changed payload cannot reuse an action ID. Missing/deleted selected strokes cause a conflict instead of silently storing a different selection. Saving a graph does not submit the attempt, assign a grade, or update mastery.

The teacher dashboard links to `/teacher/math-canvas`. This page reads real snapshots, restores their graph settings and camera, displays original ink and notes, and shows the explanation recorded at save time. Access is checked against current active student enrollment and the teacher's classroom assignments. Revoking enrollment removes access on the next API read. Lists are paginated in groups of 20.

## AI configuration

The explanation endpoint uses the existing AI gateway and per-user rate limits. Configure `AI_PROVIDER=gemini` and a valid `AI_API_KEY` in `backend/.env`, with a model supported by that account. Restart the backend after changing environment settings.

Mock output is not displayed as an AI explanation. Missing configuration or provider failure returns an explicit unavailable state while graphs and saving remain usable. Explanations are bound to the expression and parameter settings on the server. Changing parameters clears the displayed explanation; a stale explanation cannot be attached to a new snapshot. AI explanations do not affect scores, permissions, or mastery.

## API and database

Migration: `0049_math_canvas`, following `0048_math_ink_retention_index`. Run `python -m alembic upgrade head` from the backend virtual environment.

| Method | API v3 path | Access |
| --- | --- | --- |
| GET / POST | `/api/v3/math-canvas/attempts/{id}/snapshots` | Attempt owner |
| POST | `/api/v3/math-canvas/attempts/{id}/explain` | Attempt owner |
| GET | `/api/v3/math-canvas/teacher/snapshots?offset=0` | Teacher's current students |

The Next.js proxy allows only these paths and methods, checks the signed session, applies CSRF protection to writes, and keeps bearer tokens server-side. The existing API v1/v2 endpoints and frozen contract artifacts are unchanged.

## Validation on 2026-10-26

- All 191 frontend unit tests, TypeScript checking, and production build passed. New tests cover mathematical classification/evaluation, malformed expressions, undefined domains, parameter transforms, lasso intersection, and proxy role/path restrictions.
- All 21 focused backend tests passed (Math Canvas, schema registry, and ink service). The full mathematics suite finished with 187 passed, 10 skipped, and one existing contract-description mismatch described below. Tests cover snapshot replay, ownership, active teacher enrollment, immutable source ink, server-bound explanations, and separation from learning state.
- PostgreSQL local was upgraded to `0049_math_canvas`; `/health` and `/ready` returned HTTP 200.
- A live local API smoke saved a snapshot, replayed the same action without duplication, reloaded it, and confirmed access through the demo teacher account. The report is `reports/math-canvas-smoke.json`.
- The explicit paraboloid example was visually observed inside the student workspace. Handwriting recognition accuracy across real student handwriting and full touch-device acceptance have not been benchmarked.
- OCR encoder, decoder, vocabulary, and local browser runtime are present in `frontend/public/ocr`; recognition uses the existing CoMER integration. End-to-end freehand recognition and teacher-page visual acceptance remain separate from the verified mathematical parser, lasso geometry, and live save/review APIs.
- Local AI was configured as `mock` with no API key, so the live explanation request correctly returned 503. Provider success is covered by controlled service tests and remains to be verified with a real configured key.
- The installed Python/FastAPI combination emits HTTP 422 descriptions as `Unprocessable Content`; frozen API v1/v2 snapshots use `Unprocessable Entity`. The exact snapshot checks report this description-only difference (194 v1 paths and 19 v2 paths). Contract files were not re-frozen.

Useful commands, run from the appropriate project directory:

```powershell
# frontend
npm.cmd test
npm.cmd run typecheck
npm.cmd run build

# backend; use a repository-local temp directory on Windows when system temp is restricted
New-Item -ItemType Directory -Path .tmp -Force | Out-Null
.\.venv\Scripts\python.exe -m pytest tests/math_solutions/ --basetemp=.tmp/math-canvas-validation -q
```

### Flexible-view follow-up

The follow-up passed all 195 frontend tests, TypeScript checking, production build, and all 23 Math Canvas backend tests. Added coverage verifies that a one-variable curve retains its values and original equation in a spatial view, explicit extension preserves the curve along the free axis, two-variable cross-sections sample the chosen y coordinate, saved modes are restored for teachers, and default presentation remains compatible with legacy explanation hashes. The running backend exposes the new settings fields. Visual testing of the updated controls was stopped by the user with Escape; it is not reported as completed.
