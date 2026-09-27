# DATA-MATH12-012 — Curriculum + scoring + trusted QuestionGroup production bridge v0.1

Base commit: `6adfc8f6b24f21edad401242a67572457a9bcce6`

This phase prepares the bridge from the 38-group internal canonical snapshot to the real
Question Bank without prematurely publishing data.

## Key findings

1. The real canonical subject code is `MATH_G12`, while DATA-MATH12-011 snapshot metadata
   says `MATH12`. The importer must normalize to `MATH_G12`; it must not create/query a
   second `MATH12` subject.
2. The canonical Grade 12 curriculum already exists at dataset version `1.1.0`, but its
   derivative taxonomy is broad. The detailed derivative taxonomy is still staging.
3. CurriculumImportService is upsert-only. A safe candidate upgrade therefore preserves
   compatibility codes instead of assuming omitted rows are deleted.
4. All 152 snapshot child statements have exactly one primary ProblemType and every primary
   ProblemType has a staging `default_difficulty`.
5. `exam_weight` has no source-backed per-statement value. This bundle defines a structural
   policy only: child `exam_weight=0.0`, group `exam_weight=1.0`.
6. The current learning/recommendation engine selects APPROVED `Question` rows, not
   `QuestionGroup`. Therefore trusted group import must create **DRAFT only**. Approving
   children now would leak them as standalone T/F questions.

## Candidate curriculum upgrade

Expected merged candidate counts:

- 1 subject
- 6 chapters
- 10 topics
- 30 ProblemTypes
- 41 Concepts
- 18 LearningOutcomes
- 48 ConceptRelations
- 100 ProblemTypeConcept links
- 40 ProblemTypeLearningOutcome links

The candidate must live under staging/non-discoverable paths in this phase. Do not add a
second `manifest.json` with dataset code `MATH_G12_GDPT2018_CORE`, because the current
CurriculumImportService recursively discovers manifests and would report an ambiguous
dataset.

## Scoring candidate

Child difficulty = primary ProblemType `default_difficulty`.
Group difficulty = mean of four child values, rounded to 3 decimals.

This is still `COACH_LEARNING_DERIVED_INITIAL_EXPERT_DIFFICULTY`, not empirical student data
and not Ministry data. It can support DRAFT import and review, not automatic APPROVED release.

## Trusted importer

Importer must be deterministic and idempotent:
- stable child UUID from external child key;
- stable group UUID from external group key;
- one transaction per import batch;
- DRAFT only;
- no API/public asset serving;
- no synthetic explanations/cognitive levels;
- no import of group `0012`.

Raw candidate SHA must remain:
`b627a458e0b18c0a4e0733e18864e0bd83165f94894a7d690e4fc1313f3ed4d5`.

## Taxonomy activation gate

DATA-MATH12-013 adds a full-graph fingerprint and import-history gate. Trusted group
confirmation is allowed only after the exact `MATH_G12_GDPT2018_CORE / 1.2.0`
candidate has been processed by `CurriculumImportService`. The gate does not set
`verified_at`, clear rights, or approve any Question/QuestionGroup row.
