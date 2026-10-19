# Local handwritten OCR benchmark dataset

This directory documents the manifest format; it contains **no student images**.
Keep the real dataset under the repository's gitignored `.tmp/ocr_math_cpu_handwritten/`
directory. Copy `manifest.example.json` there as `manifest.json`, then add at
least 20 PNGs captured from consenting authors. A sample can be a cropped image
of a formula saved from the Math Workspace ink canvas. Review each image and its
LaTeX reference independently before setting `reference_verified` to `true`.

Each row needs a unique anonymous `id`, `group: "HANDWRITTEN"`, relative PNG
`image` path, `reference_latex`, `reference_verified: true`, a non-identifying
`source`, and `usage_allowed: true`. Do not include names, school identifiers,
faces, or other personal information in images or metadata. Never commit the
real manifest or images. The benchmark refuses unverified or unauthorized rows.

The five self-rendered smoke images in `../ocr_cpu_smoke/` check the pipeline;
they do not count toward the 20 handwritten samples or prove OCR accuracy.
