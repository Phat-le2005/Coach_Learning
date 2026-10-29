# Math View 3D

Math View extends Math Canvas inside the existing student workspace. Its purpose is to make mathematical relationships visible through exploration. It samples graphs and level sets; it does not solve equations or grade students.

**Current entry point (2026-10-29):** Math View now opens the [V2 multi-expression board](math-scene-v2.md), with planar equations, inequalities, named functions/composition, shared parameters and complete teacher restoration. **Một công thức · 3D** retains the single-formula workflow described below. References below to unsupported systems/inequalities describe that single-formula workflow; the V2 board has its own explicit scope and limits.

## Student flow

1. Open a lesson at `/student/attempts` and choose **Math View 3D** on the writing toolbar.
2. Type a formula, use **Khoanh vùng** around handwriting, or choose **Xem hình 2D/3D** on a confirmed formula step.
3. After a 350 ms typing pause, the panel identifies the mathematical representation, explains the recommended view, and displays it automatically. OCR uses the existing local handwriting recognizer. Original strokes remain visible, and OCR output must be confirmed or manually corrected before saving.
4. Rotate a spatial view, pan a planar view, zoom with the wheel/pinch/buttons, and toggle axes, coordinates, grid, or surface wireframe.
5. Move a parameter slider or choose **Chạy tham số** to see the shape change. One parameter runs at a time, bouncing between -5 and 5. Manual movement stops the animation. Animation pauses while the tab is hidden and stops on formula replacement, snapshot review, saving, or AI requests. Saving records the current values, not an animation.
6. Optionally save the current formula, parameters, camera and orthographic zoom using the existing lesson snapshot API. Teacher review restores the same representation. AI explanation remains optional; classification and rendering run locally.

## Mathematical representations

| Input | Classification | Automatic view | Optional view |
| --- | --- | --- | --- |
| `y=a*sin(x)` or `f(x)=x^2` | Explicit function of one variable | 2D curve | The same curve at z=0 in 3D; separately chosen extrusion |
| `z=a*x^2+b*y^2` or `f(x,y)=sin(x)*cos(y)` | Explicit function of two variables | 3D surface | 2D section at y=y₀ |
| `x^2+y^2=r^2` or `x=2` | Implicit planar equation | 2D contour | The same contour at z=0 in 3D |
| `x^2+y^2+z^2=r^2` or `x+y+z=a` | Implicit spatial equation | 3D level surface | Intersection with y=y₀, displayed using x and z |

Implicit equations are evaluated as `lhs-rhs=0`, retaining both original sides. The presence of z classifies an implicit equation as spatial. Single-letter parameters are discovered separately from x/y/z and the constants pi/e. Bare expressions retain the prior convention: x-only expressions define y=f(x), expressions containing y define z=f(x,y).

Arithmetic, powers, implicit multiplication, common LaTeX fractions/roots/powers, and the existing functions `sin`, `cos`, `tan`, `sqrt`, `abs`, `exp`, `log`, `ln` remain supported. Logs are natural. Only one formula is selected at a time. Inputs have explicit length, depth, token and parameter limits and use a mathematical AST, without executable evaluation.

An input beginning with `y=` or `z=` follows explicit-function rules. A self-referential form such as `y=x+y` must be rewritten with all terms on one side, e.g. `y-x-y=0`. Systems, inequalities, vectors, parametric definitions and arbitrary LaTeX are not supported in this version.

## Architecture and extension points

```text
Typed formula / selected confirmed step / lasso OCR
  -> expression.ts: normalize, bounded AST, kind, coordinates, parameters
  -> presentation.ts: view recommendation and section semantics
  -> explicit curve/surface sampler OR worker + geometry.ts scalar-field sampler
  -> GraphView.tsx: Three.js viewport, axes, camera, controls and disposal
  -> existing snapshots: server AST validation, ownership and teacher review
```

- `MathWorkspace.tsx` loads the panel dynamically, so opening a writing lesson does not eagerly load its Three.js renderer.
- `MathExpression.kind` distinguishes explicit functions and implicit relations. Mathematical dimension stays independent of camera mode.
- `geometry.ts` is independent of Three.js. It returns bounded triangle or segment positions and a truncation flag. Planar fields use triangulated grid contours; spatial fields use marching tetrahedra with a shared cube diagonal. A bracketed root check rejects sign changes across non-finite poles.
- `implicit.worker.ts` runs scalar-field sampling outside the UI thread and transfers a Float32Array buffer to the viewport. `sampling-protocol.ts` bounds the queue to one running job and one replacement; rapid changes replace the queued request, and obsolete results are discarded. `useImplicitGeometry.ts` owns worker creation, teardown, retry and timeout handling. The graph displays an updating state while new geometry is pending.
- `fit-camera.ts` fits the rendered vertices inside wide or narrow viewports, without changing mathematical coordinates. New graphs are fitted once; parameter updates preserve the current camera. **Vừa đồ thị** fits again on demand, and saved snapshots keep their recorded camera. Graphs outside the supported camera bounds display guidance instead of saving invalid camera coordinates.
- The viewport maps mathematical `(x,y,z)` to scene `(x,z,y)` for spatial surfaces, with labels reflecting that mapping. A spatial section displays x horizontally and z vertically. Planar curves use `(x,y,0)`.
- Rendering runs on demand; there is no permanent GPU animation loop. Parameter animation is capped at 20 updates/second for explicit functions and 10 for implicit equations. These are scheduling caps, not measured device frame rates.
- Explicit outer transforms retain their existing meaning. Implicit equations use their own formula parameters, domain and section coordinate; the server rejects function transforms and extrusion for these relations.
- Snapshots reuse the existing JSON settings/camera storage; no new database migration is needed for these extensions. Camera zoom defaults to 1 for older snapshots. Existing Math Canvas migrations are still required on a fresh database.
- **Tiếp tục khám phá** copies a saved equation, current parameters/view, camera and note into a new exploration. Values are copied independently, the prior snapshot remains immutable, and a new save does not attach unrelated current pen strokes. Any recorded AI explanation is cleared when starting the new exploration.

For future spatial geometry, add a typed point/line/plane/solid representation and a geometry adapter returning the same primitive contract. Keep construction semantics and object manipulation in that adapter; the camera, controls, parameter UI and snapshot authorization can be reused. Parametric geometry needs its own parameter-domain model and server validation before it is exposed in the UI.

## Sampling limits

Geometry is approximate and clipped to the chosen domain. Implicit spatial sampling uses 28 cells per axis by default; planar contours use 56. Output is bounded to 60,000 triangles. Thin features, tangent/even-multiplicity zero sets such as `(x-1)^2=0`, isolated points, and identities such as `x=x` may not generate geometry. The empty-view message says that no shape was sampled; it never declares that there are no mathematical solutions. Zooming does not increase sampling resolution; narrowing the domain can reveal more detail.

## Validation: 2026-10-28

- Frontend: 216 unit tests passed, including equation preservation, coordinate classification, sphere/plane/circle vertex residuals, sections, parameter changes, poles and empty/degenerate fields. The focused Math Canvas suite has 19 passing tests.
- Backend: 35 Math Canvas tests passed, including implicit schema validation, persistence, teacher restoration, section settings and orthographic zoom, alongside existing ownership and replay checks. The final combined run with the math-solution schema registry suite passed all 40 tests.
- TypeScript checking and the Next.js production build passed.
- Local frontend `http://localhost:3000/login` and Coach Learning backend `http://127.0.0.1:8000/health` and `/ready` returned HTTP 200. Frontend `API_BASE_URL` uses the default backend port 8000; the temporary port 8001 has been removed. This is service availability evidence, not a browser or live-snapshot acceptance test.
- The follow-up live BFF check passed all 14 checks using the local demo accounts: student/teacher login, implicit sphere persistence, idempotent replay, parameter/section/zoom restoration, CSRF enforcement, executable-syntax rejection, role isolation, teacher snapshot restoration and page availability, backend readiness and application identity. The saved example is `x^2+y^2+z^2=r^2`, with r=2, section y=1 and orthographic zoom 1.5. Evidence: `reports/math-view-3d-bff-smoke.json`. This verifies the real HTTP/database path; it does not establish rendered interaction quality.
- For local HTTP testing, run `npm.cmd run dev` on port 3000. The production server sets Secure cookies by design; the HTTP integration client will not resend those cookies. Production cookie security was preserved, and the successful local BFF run used development mode with the existing local configuration.
- Direct browser verification was attempted. Browser-host access was unavailable, then Windows Computer Use stopped because it could not establish the current URL confidently. Visual interaction, real handwriting accuracy and touch-device acceptance remain unverified for this revision. The tests above do not establish those results.

Reference API documentation: [OrbitControls](https://threejs.org/docs/pages/OrbitControls.html), [OrthographicCamera](https://threejs.org/docs/pages/OrthographicCamera.html), [BufferGeometry](https://threejs.org/docs/pages/BufferGeometry.html).

## Follow-up validation: 2026-10-29

- All 222 frontend tests passed. Added cases exercise the actual sampling worker in a separate Node thread through a small browser-worker adapter, sphere/section geometry transfer, rapid-input coalescing, obsolete replies, queue disposal, worker error recovery, camera frustum containment in wide/narrow viewports, and independent snapshot draft values.
- TypeScript checking and the Next.js production build passed. The production output includes a compiled worker implementation and Turbopack worker bootstrap. This verifies bundling and the worker's computational protocol; it does not establish actual browser Web Worker/WebGL acceptance.
- All 15 live HTTP/BFF checks passed on frontend 3000 and Coach Learning backend 8000, including saving a new r=3 exploration while the original r=2 sphere remains unchanged. Evidence: `reports/math-view-3d-bff-smoke-20261029.json`. The previously produced report remains intact.
- Frontend remains in development mode for local HTTP cookie handling. No port 8001 service is used.
- Browser discovery again returned `The browser access host is unavailable`. Direct visual review, continuous interaction timing and real-device acceptance remain unverified; no frame-rate or visual-completion claim is made.

Web Worker implementation reference: [Using Web Workers](https://developer.mozilla.org/en-US/docs/Web/API/Web_Workers_API/Using_web_workers).
