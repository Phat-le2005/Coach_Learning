# Math Lab

Open `/math-lab` for a local exploration without signing in. Inside a lesson,
open Math View and choose **Phòng khám phá mới** to save an exploration using
the existing authenticated Math Canvas API. Free exploration keeps a bounded
draft in session storage; it does not submit a lesson.

## Representations

The gallery is a starting point. All formulas are editable using the existing
bounded scalar grammar, including arithmetic, powers, implicit multiplication,
pi/e, sin/cos/tan, sqrt/abs/exp/log/ln and common LaTeX normalization.

| Representation | Editable data | Exploration |
| --- | --- | --- |
| Piecewise function | Up to six expressions and x conditions | First matching branch, gaps, open/closed boundaries |
| Parametric curve | x(t), y(t), optional z(t), t interval | 2D/3D, moving point, shared parameters |
| Vectors | Origin and u/v components in 2D/3D | Sum, difference, projection, angle, lengths, dot product |
| Calculus | f(x), contact point, bounds, rectangle count | Numerical derivative, tangent, signed integral, midpoint sum |

Each document supports up to six scalar parameters between -5 and 5.
The x sampling domain is between ±1 and ±10. Parametric intervals are bounded
to [-100,100]. The typed document is separate from sampled geometry.

## Mathematical limits

Curves use 720 steps; sampling can miss thin branches and very rapid changes.
Detected discontinuities and non-finite samples are split rather than joined.
Piecewise endpoint markers are numerical approximations, with first-match
precedence if branch conditions overlap.

Derivative estimates compare one-sided slopes; corners and undefined
neighborhoods do not receive a fabricated tangent. Integrals use 1024/2048-step
Simpson estimates with a convergence check. The rectangle sum uses midpoints
and is shown separately. Improper integrals and symbolic antiderivatives are
not supported. Numerical convergence is a practical check, not a mathematical
proof of integrability for every expression.

## Persistence and compatibility

`settings.lab` is a version-1 discriminated document with PIECEWISE, PARAMETRIC,
VECTOR and CALCULUS kinds. The outer expression is the compatibility marker
`y=0`. The document determines the true dimension and renderer. The server
independently validates every scalar and all parameter names, bounds and view
settings without evaluating submitted source code.

Snapshots reuse the existing JSON settings column, ownership, CSRF, replay
protection and teacher enrollment checks. No migration is needed. Existing
single-formula and version-2 scene hashes remain compatible when lab is absent.
Teacher review restores the document, parameters, camera and student note.
Advanced exploration does not change scores, mastery or assessment state.

Sampling runs in a worker with one active request and one latest replacement;
obsolete results are discarded. Three.js renders on demand and disposes geometry,
materials and label textures on replacement. UI checks on a real browser/device
remain distinct from worker, schema, persistence and production-build tests.
