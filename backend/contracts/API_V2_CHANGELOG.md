# API v2 changes

## 2026-11-08 — Reviewable logical steps from handwriting OCR

`POST /math-solutions/attempts/{attempt_id}/ocr/recognize` adds `steps` (default
empty) and nullable `segmentation_warning` to the existing OCR response. Each
proposal includes a Vietnamese title, content kind, transcription, suggested
step type and source stroke IDs. Existing whole-page fields are retained.

Gemini proposes logical boundaries from the supplied ink image. The server maps
image boxes back to a disjoint partition of the original pen strokes; invalid
or unsupported proposals leave the original transcription with a warning.
This endpoint does not create solution steps, submit work, grade answers or
update mastery. The student reviews the proposals and explicitly saves them
through the existing ordered, revision-checked step mutations before grading.

API v1 is unchanged. Snapshot and digest: `openapi-v2.json`, `openapi-v2.sha256`.
