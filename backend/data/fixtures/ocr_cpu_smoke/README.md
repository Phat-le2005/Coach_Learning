# OCR CPU technical smoke images

Five small, self-authored typeset MathText PNGs exercise image decoding and real
ONNX inference. They are **not handwritten** and cannot establish handwriting
accuracy. No student data is present. The images were rendered locally with
Matplotlib's Agg backend from the five mathematical expressions listed in
`manifest.json`; predictions are never generated from those reference strings.

For the handwriting benchmark, place at least 20 permitted, de-identified PNGs
and a manifest in the gitignored repository `.tmp/ocr_math_cpu_handwritten/`
directory. Use the same schema with `group: "HANDWRITTEN"`, a unique ID, formula
group, reviewed `reference_latex`, `reference_verified: true`, `usage_allowed:
true`, an image path relative to the manifest, and a provenance source that
does not identify a student. Capture a cropped formula from the Math Workspace
or a consented handwritten sheet; do not include names or full-page homework.

The benchmark prints literal LaTeX exact match and character error rate. It
does not claim equivalent TeX spellings are the same. Its `exact_mismatch_count`
is a potential correction count; actual human corrections remain unset until
a person reviews the OCR output.
