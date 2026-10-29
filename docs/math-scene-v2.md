# Math View: multi-expression board (V2)

The board helps students compare mathematical relationships and explain what they observe. It renders sampled graphs and regions; it is not a symbolic solver or an assessment engine.

## Classroom workflow

1. Open a student lesson on `http://localhost:3000`, then choose **Math View 3D** on the writing toolbar. The multi-expression board opens first.
2. Type one expression per row. Enter adds a row. A selected confirmed formula is appended to the draft; lasso handwriting uses the existing local recognizer and requires review before saving. A late OCR response cannot replace manual edits.
3. Compare curves using row colors and visibility. Hidden function definitions remain available to dependent expressions.
4. For inequalities, choose separate shading, **Miền chung** (AND), or **Miền hợp** (OR). These modes apply only to visible inequality rows. Equation rows remain reference curves, not additional filled-region constraints.
5. Drag to pan, use wheel/pinch/buttons to zoom, and toggle the coordinate axes/grid. Arrow keys pan a focused graph; +/- zoom. Shared parameter sliders update every dependent row.
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

Function names and parameters are single letters a–w except e; x/y are planar coordinates. Functions accept one argument and their definitions depend on x and shared parameters. Missing, duplicate and cyclic definitions produce row-specific errors. An undefined inner argument stays undefined even when the outer function is constant: `f(x)=1; y=f(1/x)` excludes x=0.

At most eight rows, 500 input characters per row, six shared parameters, and 600 expanded AST nodes at depth 40 are allowed. Sliders range from -5 to 5; the sampled square is `[-d,d]²`, with d between 1 and 10. Empty editor rows are not stored. Valid rows remain visible while another row is being corrected; saving requires every nonempty row to be valid.

## Scope of 3D

**Một công thức · 3D** opens the existing renderer for explicit surfaces, implicit spatial equations, rotation, zoom, sections and parameter animation. A board row containing z offers **Xem 3D** with that formula.

The V2 multi-expression board is planar. Multiple spatial surfaces, their intersection curves, 3D inequality volumes, parametric curves, piecewise functions and geometric constructions are not implemented by this revision. These require additional typed representations and geometry adapters; they should not be silently projected into a planar result.

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

The outer snapshot retains `expression: "y=0"` as a compatibility placeholder; for a V2 scene, `settings.scene` is authoritative and the UI displays its actual rows. The server requires planar view settings, identity outer transforms, exact shared parameter names and independently validated canonical expressions. It never evaluates submitted code. Existing snapshots without scenes retain their old rendering and hash/idempotency behavior. Optional AI explanation remains available for the single-formula flow; the board does not offer an AI explanation action.

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
