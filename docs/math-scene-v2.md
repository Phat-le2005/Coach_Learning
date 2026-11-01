# Math View: multi-expression board (V2)

The board helps students compare mathematical relationships and explain what they observe. It renders sampled graphs and regions; it is not a symbolic solver or an assessment engine.

## Classroom workflow

1. Open a student lesson on `http://localhost:3000`, choose **Math View** on the writing toolbar, then **Nhiều biểu thức**. A handwriting selection detected as two to eight equation rows opens the board directly and starts separate recognition. A single row or confirmed formula keeps basic 2D/3D exploration in the single-formula view.
2. Type one expression per row. Enter adds a row. Multiple equations can be pasted with newlines, semicolons or supported LaTeX cases/aligned row separators. A new selected formula/handwriting region replaces the current rows with exactly that selection; old cached rows are not appended. Each handwriting line is sent separately to the existing local recognizer and requires review before saving. A late OCR response cannot replace manual edits.
3. Compare curves using row colors and visibility. **Giao điểm gần đúng** appears below the graph, with numbered markers and coordinate buttons that center the graph on each point. Hidden function definitions remain available to dependent expressions.
4. For inequalities, choose separate shading, **Miền chung** (AND), or **Miền hợp** (OR). These modes apply only to visible inequality rows. Equation rows remain reference curves, not additional filled-region constraints.
5. Choose **2D / 3D** directly above the graph. New selections and reopened editor drafts start in 2D. Choose 3D when needed; its horizontal Oxz floor and upright y axis match the single-formula viewer. Durable snapshots still restore their saved view mode. Explicit curves retain their full height over the selected x domain, so a parabola's legs are not cropped at the survey square. Rotate or pan, choose camera presets, fit/reset and zoom. In 2D, drag to pan, use wheel/pinch/buttons to zoom, and toggle the coordinate axes/grid. Arrow keys pan a focused 2D graph; +/- zoom. Shared parameter sliders update every dependent row.
6. Record an observation and choose **Lưu bảng vào bài học**. A saved board contains all expressions, colors, visibility, region mode, parameter values, domain, camera and note. A teacher with access to the student's class can restore it.
7. Opening a saved board is read-only. **Tiếp tục khám phá** creates a new exploration without changing the original snapshot or attributing unrelated pen strokes to it.

The tab keeps a bounded session-storage draft per attempt/page, including camera and note. Reloading or closing/reopening the panel restores the draft. This is a convenience cache, not a submitted lesson or cross-device backup; use the save button for durable storage. Switching between the board and the single-formula view keeps the board and its camera.

## Supported mathematical language

| Representation | Examples | Meaning |
| --- | --- | --- |
| Explicit curve / bare expression | `y=a*x^2+b`, `sin(x)` | Bare expressions mean `y=...` |
| Implicit planar equation | `x^2+y^2=r^2`, `x*y=1` | Sample the zero set of left minus right |
| Strict / inclusive inequality | `y>x^2`, `x^2+y^2<=r^2` | Strict boundaries are dashed; inclusive boundaries are solid |
| Chained relation | `0<=x<=2`, `-1<y<1` | All comparisons in the row must hold |
| Named unary function | `f(x)=a*x^2+1`, `g(x)=sin(x)` | Definition plots as a reference curve and can be hidden |
| Function composition | `y=f(g(x))`, `y>=f(x)` | Bounded AST substitution; forward references supported |

This is a grammar, not a fixed catalogue of example equations. Arithmetic, powers, implicit multiplication, pi/e, `sin`, `cos`, `tan`, `sqrt`, `abs`, `exp`, `log` and `ln` can be combined. Logs are natural. Unicode ≤/≥, superscripts ²/³, and common LaTeX fractions/roots/comparison signs are normalized. Arbitrary LaTeX is not supported.

Conventional positive-integer trig powers are supported in typed and OCR forms: `cos²(x)`, `sin^2(x)` and `\cos^{2}(x)` normalize to powers of the function value, e.g. `(cos(x)^2)`. Nested arguments, adjacent products and further outer powers retain their mathematical grouping. Negative or symbolic exponents before a function argument remain explicit-only, e.g. `(sin(x))^(-1)`, avoiding an implicit choice between reciprocals and inverse trig functions.

Function names and parameters are single letters a–w except e; x/y are planar coordinates. Functions accept one argument and their definitions depend on x and shared parameters. Missing, duplicate and cyclic definitions produce row-specific errors. An undefined inner argument stays undefined even when the outer function is constant: `f(x)=1; y=f(1/x)` excludes x=0.

At most eight rows, 500 input characters per row, six shared parameters, and 600 expanded AST nodes at depth 40 are allowed. Sliders range from -5 to 5; the sampled square is `[-d,d]²`, with d between 1 and 10. Empty editor rows are not stored. Valid rows remain visible while another row is being corrected; saving requires every nonempty row to be valid.

## Scope of 3D

The board's **3D** view renders selected planar relations together on Oxy at z=0, using the same horizontal reference grid, default perspective camera and curve-framing policy as the single-formula viewer. Explicit y=f(x) / f(x)=y curves are sampled over the x domain with full y height; implicit contours, regions and approximate intersections retain the planar worker's survey-square limits. Gaps, colors and original mathematical coordinates remain unchanged. The display mode and active camera are saved/restored in lesson snapshots, including teacher review. Only the active renderer and its sampling worker are mounted.

**Tạo bề mặt kéo dài** sits beside the 2D/3D selector, including while the board is in 2D. Clicking it selects 3D and extends each visible equality path separately along `0 <= z <= scene_depth`, keeping the row color and the original equation. **Về đường cong** returns to ordinary spatial curves. The sidebar's **Độ kéo dài theo z** control sets the extent. Approximate planar intersections at z=0 are retained, with corresponding vertical reference lines in surface mode. This surface workflow does not turn the filled area between two curves into a solid. Earlier snapshots with a positive depth and no surface flag still restore their existing explicit solid model.

**Một công thức** opens the existing single-formula renderer for explicit surfaces, implicit spatial equations, rotation, zoom, sections and parameter animation. A board row containing z offers **Xem 3D** with that formula. Multiple spatial surfaces, their intersection curves and 3D inequality volumes are not supplied by the planar board's camera mode. Parametric/piecewise/vector exploration remains available separately through Math Lab.

## Architecture and data compatibility

```text
Typed / selected formula / local OCR
  -> expression.ts: scalar normalization + bounded mathematical AST
  -> scene.ts: named definitions, relations, row errors, shared parameters
  -> scene.worker.ts: one running request + one latest replacement
  -> scene-geometry.ts: contour segments, region triangles, approximate intersections
  -> GraphSceneView.tsx: Canvas2D camera, drawing and accessible controls
  -> GraphScenePanel.tsx: editor, OCR review, draft and immutable snapshots
  -> existing authenticated BFF and Math Canvas snapshot service
  -> TeacherCanvasReview.tsx: restore scene or legacy Three.js graph
```

No new runtime package is required. Planar drawing uses Canvas2D; the student single-formula Three.js viewport is dynamically imported when used. Sampling runs in a Web Worker, transfers typed buffers, discards superseded responses, and has retry/timeout handling. Contour segments are connected into polylines so dash patterns remain visible across short sampling edges.

The versioned document lives in the existing JSON `settings.scene` field:

```json
{
  "version": 2,
  "dimension": "2D",
  "combine": "AND",
  "rows": [
    {"id": "upper", "expression": "y<=1", "visible": true, "color": "#e05a23"},
    {"id": "lower", "expression": "y>x^2", "visible": true, "color": "#2563eb"}
  ]
}
```

The outer snapshot retains `expression: "y=0"` as a compatibility placeholder; for a V2 scene, `settings.scene` is authoritative and the UI displays its actual rows. The server permits AUTO/2D/3D camera modes while requiring planar mathematical definitions, identity outer transforms, exact shared parameter names and independently validated canonical expressions. Extrusion remains rejected. It never evaluates submitted code. Existing snapshots without scenes retain their old rendering and hash/idempotency behavior. Optional AI explanation remains available for the single-formula flow; the board does not offer an AI explanation action.

No database migration is added: the existing Math Canvas migrations and JSON storage are reused. Student ownership, active teacher/class enrollment, CSRF checks, immutable ink and idempotent action IDs remain enforced by the existing routes/service.

## Numerical limits and rollout evidence

Contours use 56 cells per axis and filled regions use a triangulated 72-cell grid. Isolated/tangent points, even-multiplicity zero sets, very thin regions and features smaller than a grid cell may be missed. Numerical intersections are visual hints (up to 50 points), not a complete solution set. Pole crossings and non-finite domains are rejected. Zoom changes the camera, not sampling accuracy. Empty sampled geometry is explicitly described without declaring that an equation has no solutions.

Local verification on 2026-10-29:

- 237 frontend tests and 58 backend Math Canvas/schema-registry tests passed; TypeScript and the Next.js production build passed.
- Tests cover strict/inclusive membership, chained relations, function composition/domain guards, malformed input, complexity bounds, worker transfer, intersections, draft recovery and old snapshots. Region areas are checked against analytic disk and parabola-region areas; AND/OR/hidden-row behavior is checked separately.
- 84 canonical documents emitted by the frontend were accepted by the server validator: `reports/math-scene-parser-parity.json`. This corpus verifies the covered forms, not equivalence of every possible parser input.
- All 16 live BFF checks passed on frontend 3000/backend 8000: save/replay, complete teacher restore, legacy reads, CSRF, role isolation and invalid document rejection. Evidence: `reports/math-scene-smoke.json`.
- Direct desktop UI review verified two curves, strict dashed vs inclusive solid boundaries, common-region shading, shared function/parameter updates, zoom, visibility, draft restoration after reload, and a successful save with a student observation.
- The single-formula view rendered `z=a*(x^2+y^2)` and responded to mouse-wheel zoom and drag rotation. Returning to the board retained its rows, hidden definition, parameter and zoom. Consolidated evidence and remaining gaps: `reports/math-scene-qa.json`.

These checks support a local classroom pilot. Physical tablet/stylus gestures, handwriting recognition accuracy across student samples, school-device/browser performance, accessibility acceptance and teacher-led lesson acceptance still need field validation. No device FPS, universal equation coverage or production deployment claim is made.

Local services remain frontend **3000**, backend **8000**. The frontend API origin is `http://127.0.0.1:8000`; local HTTP login testing uses the development server and preserves production Secure-cookie behavior.

## Multi-line handwriting follow-up: 2026-11-01

- `multi-formula.ts` reuses the fraction-aware page line detector. A separate tall left system brace is excluded from recognition only when the remaining ink forms disjoint, substantial rows. Original strokes, order and saved provenance are retained; superscripts/fractions have regression coverage. An explicit **Thử đọc chung** action remains available for a single expression split by the heuristic.
- The single-formula view hands current typed rows to the board, or asks for line-by-line OCR for a multi-line selection. OCR is sequential, stops scheduling after manual edits, and retains failed rows as independent editable inputs. Editing one recognized row confirms only that row; switching views does not clear outstanding OCR confirmation. Retrying OCR updates the same rows. Equal-looking OCR results retain separate rows so a mistaken duplicate can be corrected.
- Batch imports are atomic at the eight-row limit. Existing formulas are preserved if the whole incoming group cannot fit. No schema, database or assessment changes are required.
- TypeScript and 90 focused Math Canvas/Scene/Lab, page segmentation and handwriting-adapter tests passed. They include typed/LaTeX row splitting, braces/fractions/superscripts, atomic imports, duplicate-row correction, canceled/failed recognition, and three sampled intersections between a cubic and a trigonometric curve. These are synthetic geometry and injected recognizer checks; accuracy on the user's real handwriting has not been established. Browser automation was disabled in Work settings, so the new buttons and live OCR workflow have not been directly verified in the browser.

### Reported eight-fragment correction

- The student's saved 39-stroke layout reproduced the reported eight groups. Center-based page row clustering detached the long y descenders, large parentheses, superscripts and an isolated dot. The system brace then failed the prior exclusion guard because the remaining fragments were not full rows.
- Equation-specific grouping now rejoins neighboring fragments by vertical extent and horizontal proximity after fraction-aware segmentation. A separate left brace is excluded only if it spans at least two resulting substantial rows. The actual saved layout produces two inputs of 15 and 23 strokes, with one system-brace stroke retained on the original page. No saved ink is modified.
- `tests/fixtures/math-canvas/tall-two-equation-layout.json` retains anonymous bounding boxes only; synthetic diagonal strokes reproduce the segmentation failure without copying original identifiers or pen trajectories. The regression failed with `8 !== 2` before the correction and passes afterward. Different writing sizes/translations, three tall equation rows, single-formula tall parentheses, fractions and superscripts are also covered.
- Multi-row selections open the board directly. Per-row handwriting previews are shown during recognition and beside the OCR results, so the grouping can be checked independently from symbol recognition.
- TypeScript and 92 focused tests passed. This establishes grouping on the reported saved layout; live OCR transcription and browser acceptance of the updated automatic entry/preview remain unverified while browser automation is disabled in Work settings.

### Trigonometric power notation correction

- The reported `Hãy viết cos(...) với dấu ngoặc` error was reproduced for `\cos^{2}(x)`: the parser previously expected the opening argument parenthesis immediately after `cos` and rejected the intervening exponent. Shared normalization now handles conventional `sin`/`cos`/`tan` positive-integer powers before the argument and emits the already-supported canonical function-call/power grammar.
- TypeScript and 95 focused tests passed, including typed/LaTeX sine-cosine square identities, nested and outer powers, multiplication/negation, undefined arguments and rejection of ambiguous inverse notation. A two-row cubic plus `sin²(x)+cos²(x)` scene compiled and sampled both paths with three intersections near y=1.
- Six canonical single formulas and the two-row scene passed the existing backend GraphSpec validator without schema changes. Live UI/OCR acceptance was not repeated; the checks establish parsing, sampling and canonical validation for these covered forms.

### Shared 3D camera and selection replacement

- Added an in-board 2D/3D toggle and a lazy Three.js renderer for all selected planar rows together. `useSceneDrawing.ts` shares the existing worker protocol; `scene-spatial.ts` lifts each sampled point to `(x,y,0)` without changing the mathematical relationships or adding per-row depth offsets. One active renderer prevents duplicate canvases and workers. Intersections and coordinate buttons are shared across views.
- A fresh handwriting selection clears stale curves immediately and allocates exactly one row per detected equation, including failed rows that need correction. Completion replaces those rows rather than merging with recovered drafts. Manual Add/Paste remains explicit; saved lesson snapshots are unaffected.
- The backend accepts 3D camera mode for planar scenes. Snapshot replay and teacher restoration retain the active 2D/3D mode and camera; mathematical dimension remains 2D. No migration is needed.
- TypeScript, 97 focused frontend tests, 55 backend Math Canvas tests and the production build passed. Coverage includes replacement counts, duplicate selected equations, 3D path/color/gap/coordinate preservation, draft cameras and backend replay/teacher restore in both modes. Browser automation remained disabled in Work settings, so live WebGL/gesture acceptance is pending.

### Larger 3D viewport and colored interiors

- The scene panel now uses up to 1480px width with a narrower expression column. The 3D canvas has a responsive 62dvh height and explicit 440px minimum in its host styles, preventing a missing/stale CSS-module class from leaving it at the browser's 150px canvas default. **Mở rộng đồ thị** uses nearly the whole viewport; **Thu gọn đồ thị** or Escape returns to the panel. Size changes fit the curves again; opening a saved camera does not trigger that size-change fit.
- For exactly two visible explicit `y=f(x)` equations, closed intervals between their sampled intersections receive translucent colored interiors by default in 2D and 3D. **Tô miền giữa 2 đường** toggles them; 3D includes an opacity slider. Equations/rows remain unchanged. These preferences are transient display controls, like grid/axes; the mathematical scene and camera retain their existing snapshot contract.
- `between-curves.ts` refines root hints, samples each closed lobe, clips triangles to the survey square and rejects nonfinite/pole-crossing intervals. It does not fill open strips, coincident curves or infer an inside for arbitrary implicit relations. The work runs in the scene worker and transfers Float32Array buffers. General sampling limitations, including missed tangencies/small features, still apply.
- TypeScript and 99 focused frontend tests passed, including analytic 4/3 and 8/3 area checks, sine lobes, reversed equation orientation, unchanged scene definitions, pole/open/coincident/unsupported cases and the actual worker buffer transfer. The reported cubic/sine pair produced two colored lobes and three intersection markers. The production build passed; live UI sizing, expansion and opacity gestures remain unverified while browser automation is disabled.

### Stored depth-model compatibility: 2026-11-01

- Existing depth models remain restorable. Solids have bottom/top caps and outward side walls; internal triangulation edges are removed from the walls. Standard shaded materials and directional lighting distinguish front, side and top surfaces. New explicit surface mode extends each curve separately instead of creating these solids.
- `settings.scene_depth` defaults to zero for legacy data and is bounded to [0,10]. A positive value requires a scene and explicit 3D mode. It is saved with the rows/camera and restored read-only in student snapshots and teacher review. Session drafts retain `spatialDepth`; original planar rows/parameters and ink remain unchanged. Default depth is omitted from explanation hashes to preserve existing cache identity. No database migration is needed.
- 102 focused frontend tests, 61 backend Math Canvas tests and the production build passed. Verification includes analytic prism/parabola-region volumes, closed-mesh edge pairing, absence of internal walls, domain clipping, separate polyline gaps, bounded drafts and backend save/replay/teacher restore at depth 1.5. Browser automation remains disabled in Work settings, so the actual WebGL appearance and slider/rotation gestures still need live visual acceptance.

### Reference curve presentation: 2026-11-01

- Both 3D viewers use `createReferenceGrid` for the horizontal Oxz floor, with y upright. The multi-expression viewer shares the default camera and long-tail framing policy with the single-formula view. Full curves remain available through **Toàn bộ**; fill and intersection coordinates stay at z=0.
- `scene-curve-sampling.ts` runs inside the scene worker. It resamples explicit equalities, including reversed equations and expanded named functions, with the same 900-interval finite-value/jump policy as the single-formula viewer. The original planar drawing is not mutated. Implicit contours and inequality boundaries are retained; hidden rows remain hidden.
- Untagged older session drafts retain their expressions, parameters, 2D camera and note, but initialize the corrected curve presentation with a fresh spatial camera and zero extrusion. Drafts tagged `spatialStyle: CURVE_3D` keep subsequent camera adjustments. Durable snapshots always restore through their existing explicit path.
- 107 focused frontend tests, TypeScript and the production build passed. Regression coverage includes the reference downward parabola's vertex/complete legs, projected curve height in square/wide viewports, horizontal-floor coordinates, poles/domain guards, hidden definitions, shared coefficients, draft migration and actual worker transfer. Live appearance and pointer interaction remain unverified because local browser use is disabled in Work settings.

### Workspace usability: 2026-11-01

- The compact header, formula sidebar and graph area have separate visual roles. The save footer stays outside the scrollable panes, with an explicit readiness/error/OCR-review message. It saves the same existing snapshot contract; Ctrl/Command+S works while focus is inside the panel and respects save, validation and recognition locks.
- Formula rows wrap in textareas, retain per-row colors, provide show/hide and delete buttons, and share quick insertion keys that preserve the active selection/caret. Enter adds a row; Shift+Enter keeps editing the current formula. Re-rendering a row no longer forces focus back from graph controls. OCR remains subject to explicit review before saving.
- The shared 2D/3D toolbar appears above the graph, with zoom, fit, reset and expansion. Rotation/panning are direct controls in 3D; grids, axes, camera presets and applicable fill controls are grouped under **Tùy chỉnh**. Irrelevant fill controls are omitted rather than shown as disabled checkboxes. Both modes support F to fit, R to reset and +/- zoom when the graph has focus. Escape closes an expanded graph.
- **Vừa hình** in 2D centers the actual sampled paths/fills with equal coordinate scale. Shared coefficient sliders and the domain control move to the sidebar with direct numeric entry and per-control reset. Inequality combine modes appear only when relevant. Notes, example choices, selected ink and saved boards use collapsible sections.
- Narrow screens use separate **Công thức / Đồ thị** tabs while preserving the graph and editor state. Touch controls have larger targets, and reduced-motion settings disable decorative transitions/spinners.
- 108 focused frontend tests, TypeScript and the production build passed, including wide/narrow 2D fitting, retained mathematical coordinates, empty geometry and existing 3D/OCR/worker/snapshot-draft checks. The live visual layout, mouse/touch gestures and button workflow still require browser acceptance: local browser use is disabled in Work settings.

### Default view: 2026-11-01

New board exploration, typed handoffs and handwriting recognition start in 2D, including editor draft recovery. The single-formula view also starts in 2D for new formulas; a spatial formula uses its labelled 2D section until the student selects 3D. An explicitly selected view remains active during ordinary edits within the same formula family. Stored snapshots restore their saved mode and camera.

### Discoverable multi-equation surfaces: 2026-11-01

- A visible **Tạo bề mặt kéo dài** action beside 2D/3D operates on the board's current equations without opening single-formula mode, changing the selected rows or automatically confirming OCR. Each equality path retains its own color and becomes an open surface; it remains separate even when the original curves enclose a colored region. The original plane and approximate intersections remain available. Strict/inclusive inequality boundaries stay planar.
- Spatial curve sampling retains full y height over the x domain. Surface extension can preserve that height instead of clipping it to the survey square; nonfinite intervals and separate polyline gaps are never bridged. The z extent is bounded to 0.2–10 units in the editor. Choosing the ordinary 3D tab or **Về đường cong** removes the extension. New panels still begin in 2D.
- `settings.scene_surface` is a strict boolean, defaults to false and is omitted from legacy explanation hashes when false. A true value requires a scene, explicit 3D view and positive scene depth. Student drafts and snapshots, replay and teacher restore retain the flag and extent; the old solid snapshot interpretation remains backward compatible. No database migration is required.
- The focused frontend suite has 109 passing tests, including the two reported equations, separate surface colors, height preservation, z extents, unchanged source geometry, closed-region compatibility and bounded draft data. The full frontend test suite has 395 passing tests. Browser control remains disabled in Work settings, so direct appearance and click acceptance are still pending.

### Git delivery verification: 2026-11-01

- After incorporating the current `origin/main` OCR fixes, an isolated export of the committed frontend passed all 397 frontend tests and the Next.js production build, including TypeScript. Backend Math Canvas, QA fixture safety and prompt-registry checks passed 76 tests. This export excluded local Knowledge Forest changes and later Math View edits still being worked on.
- The local frontend at port 3000 and backend health at port 8000 returned HTTP 200 after dependency synchronization. This is runtime reachability evidence; browser visual/button acceptance remains pending because local browser use is disabled in Work settings. Deployment was not performed.
