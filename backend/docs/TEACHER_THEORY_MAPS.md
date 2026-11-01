# Teacher theory maps

This class-scoped workflow is a source-first theory library. Teachers upload a PDF, inspect it, and share the original with actively enrolled students. An optional reviewed mind map can be published separately. It does not create Questions, modify curriculum, or publish to the public Knowledge Forest.

## Source-first library

- Migration `0053_theory_source_library` adds `source_published_at`. Sharing the original PDF is independent of `TheoryMapStatus.PUBLISHED`; it never approves draft nodes, formulas, or extraction output.
- `/teacher/theory` offers one-click share/unshare of the original PDF after upload. `/student/theory` presents the PDF as the primary lesson, with page controls, exact-heading page links, and an optional reviewed map. Heading links are navigation only; generic theorem labels and unreviewed mathematical content are not presented as lessons. Teacher editing remains under an advanced disclosure.
- `GET /api/v2/student/theory/{id}/source` requires an active class enrollment and a shared source. The bytes are verified against the stored SHA-256 on share and on read. Unreviewed nodes are removed from student read responses even when the source is shared.
- A valid PDF with scanned or textless pages can be uploaded and shared without Docling. Local OCR is only needed if a teacher elects to build a cited mind map from those pages. The browser currently uses its native PDF renderer; a dedicated PDF.js viewer is a future enhancement for consistent mobile page navigation.
- For Math PDFs with font-encoded symbols, the original page is authoritative. Neither pypdf nor a heading-only Markmap is treated as a verified formula or worked example. Reviewed formula cards and interactive mathematics should be added only from reliable source-backed content.

1. Apply migrations through `0053_theory_source_library` (`alembic upgrade head`). Teachers open `/teacher/theory`, select a class and subject, and upload a PDF of at most 80 pages and `TEACHER_MATERIAL_MAX_BYTES` bytes (25 MiB by default).
2. Upload validates the PDF and reads any native text layer. Textless pages do not block source sharing. If a teacher later generates a map, textless pages may be processed by optional local Docling OCR (`pip install -r requirements-docling.txt`); without it, map generation fails explicitly while the shared original remains available. Do not treat OCR output as verified mathematics.
3. **Create local draft** uses source headings (chapter, theory section, definition/theorem, and exercise type) rather than turning arbitrary text blocks into concepts. It skips contents-page exercise entries, prose fragments after note/example labels, exercise examples, and font-encoded mathematical glyphs. Numbered sections attach only to a matching numbered ancestor; if an intermediate heading is missing from extraction, they attach to the nearest matching ancestor. Explicit, unambiguous `Bước 01/02…` runs are copied into the related `Dạng` with a PDF page and exact text quote. When a line ends before encoded math, only its readable prefix is copied and `□` marks the teacher correction. Repeated numbering and example solutions are not copied. It does not call Gemini, invent explanations, or convert arbitrary formulas to LaTeX. The draft supports 400 nodes; teachers can edit or add up to 500 nodes. If a dense PDF exceeds either limit, split it rather than silently omitting content.
4. Every node has a source page and quote checked against the stored extracted page text. Pages with replacement characters or many private-use font glyphs are flagged in the teacher UI. Citation matching proves extraction provenance, not mathematical correctness; the original PDF is authoritative. All generated nodes begin unreviewed, and teachers must fill or correct theorem content and formulas themselves when extraction is unreliable.
5. The teacher reviews the prefilled steps, fixes any `□`, and supplies a short explanation (`body`) or optional key formula (`latex`) only where extraction is incomplete. Each copied step has a source page and exact quote checked against the stored PDF text. Formula input has a live preview and common-symbol buttons. Generated content is never auto-reviewed. Any edit clears that node's reviewed flag. `POST /api/v2/teacher/theory/{id}/prefill` enriches existing drafts without replacing teacher changes; it is idempotent and revision-checked. Regeneration is rejected if a draft has changed from the generated outline.
6. The teacher marks each node reviewed, saves the revision, then publishes the optional map. Publication rejects empty definition/theorem/note content, exercise-type branches without learning steps, and final branches with no learning content. Revision conflicts return `409`. Student access is limited to actively enrolled students in that class; they see reviewed map content only when published, and the original PDF only when explicitly shared.
7. The viewer uses Markmap's interactive SVG and opens one major branch by default for large maps. Labels are HTML-escaped before rendering, while student-facing content appears in a separate accessible reading panel. An HTML branch list provides keyboard selection. The teacher editor shows one selected node at a time. Editing a published map returns it to draft and removes student access until republished.
8. A teacher can explicitly regenerate an unreviewed draft using the improved outline parser. This replaces draft nodes after confirmation and increments the revision; it never overwrites a reviewed or published map.

Gemini is not used by this workflow. The rest of the project's AI gateway is unchanged.

## Student math notebook from the original PDF

The default theory view is a source-faithful notebook, generated locally when a
teacher or authorized student opens a document. It needs no Gemini call and no
manual node entry. PDFium detects source headings and divides each page into
small visual cards: theory, notes, methods, examples, and continuations. The
index groups these cards under the source's chapter and exercise-type headings.
Cards show rendered regions of the original PDF, preserving mathematical
symbols, diagrams, and worked steps even when the embedded font produces
unreliable text extraction. No extracted formula is silently rewritten as
LaTeX or treated as reviewed academic content.

Teachers see the notebook immediately after uploading a PDF. They can inspect
the original PDF in the collapsible source viewer and share the source with
their class using the existing explicit action. Students can read the notebook
only when actively enrolled in that class and the source has been shared.
Sharing the source does not publish an unreviewed mind map. The advanced
editable map remains a separate, reviewed view.

The backend verifies the stored PDF's SHA-256 before returning either the
notebook index or a PNG card. The BFF enforces student/teacher role checks and
only forwards allowlisted notebook paths. All notebook responses are private
and non-cacheable. Install the normal backend dependencies to provide
pypdfium2; missing renderer produces a clear service error rather than a
fabricated lesson.