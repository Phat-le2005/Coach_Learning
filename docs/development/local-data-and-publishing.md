# Lightweight repository and optional local question data

Runtime code, migrations, tests and the small ten-exercise development pack are
versioned. Models, raw PDFs, full OCR exports, review booklets, databases, recordings
and environment secrets are local assets and must not be included with git add.

The original academic package belongs at
backend/data/Toan12_200_cau_20261104/ and must be obtained separately from the team.
Do not regenerate or edit its JSON/PNG bytes to satisfy a validator. Package tools
validate the pinned source identity before preparing a review; successful technical
validation does not approve academic content or enable production publication.

Optional package commands (from backend):

    python -m app.validate_pdf_handoff_staging
    python -m app.prepare_pdf_handoff_review
    python -m app.seed_derivative_test_pack
    python -m app.seed_derivative_test_pack --apply

The last command is restricted to development/test. Source-package checks skip
explicitly when optional data is absent; math, installation, API and security
tests continue using the small committed pack and isolated test databases.
A missing source package never produces fake questions, grades or runtime data.
Source image/PDF checks require the original package and are separate from CI's
code-only checks.

Local demo recording scripts and synthetic submission seeding helpers are not
application dependencies and are excluded from publication. Configure real API
keys in ignored environment files, never in scripts or .env.example.
