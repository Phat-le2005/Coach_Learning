# DATA-MATH12-033 — Full-Scope Curriculum Alignment Candidate

This dataset defines a non-canonical Grade 12 Math curriculum graph candidate aligned to the five official GDPT 2018 core scopes.

Base repository commit: `de2f935bc88308aaffcb6eef43d4ee9cfd4c67bb`
Input audit: `DATA-MATH12-032`
Input audit aggregate: `ea64fd6dd257d80f4d19477a7708f21229643d87ad7793b22504bb680c7a22e5`

## Candidate graph

- 5 chapters
- 24 topics
- 75 problem types
- 20 official normalized requirements bound to reviewed/derived learning outcomes
- Vector taxonomy is absorbed into Oxyz as a subscope
- Grouped-data statistics receives a dedicated full-scope chapter identity
- Exponential/logarithm is quarantined from Grade-12 core without destructive deletion

All chapter/topic/problem-type/concept/prerequisite structures are Coach Learning derived taxonomy.
They must not be represented as Ministry-issued taxonomy.

## Safety boundary

This candidate is PREVIEW ONLY.

- activation_allowed = false
- database_import_allowed = false
- canonical_write_allowed = false

Oxyz and Probability academic taxonomies currently lack some CurriculumImportService display fields.
DATA-MATH12-033 deliberately reports these as schema enrichment required rather than allowing Codex to invent academic labels.

A later reviewed dataset must enrich those records before any canonical promotion/import.
