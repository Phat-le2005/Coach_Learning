# EduMS — Curriculum Model

> **Document version:** 1.0 · **Last updated:** 2026-09-22

This document defines the canonical data model for EduMS's curriculum hierarchy, knowledge graph, and mastery system. It is the authoritative reference for understanding the distinction between every entity type.

---

## 1. Curriculum Hierarchy

```
Curriculum
  └── CurriculumVersion          (e.g. "GDPT 2018 v1.0")
        └── Subject              (e.g. "Toán THCS — Lớp 7")
              └── Chapter        (e.g. "Chương I: Số hữu tỉ")
                    └── Topic    (e.g. "Phép cộng và trừ số hữu tỉ")
                          └── ProblemType  (e.g. "Quy đồng rồi cộng/trừ")
```

### 1.1 Curriculum

The top-level programme of study (e.g. the Vietnamese national curriculum "GDPT 2018").

- **Code**: stable, uppercase, e.g. `GDPT_2018`
- Anchors all `CurriculumVersion` snapshots.

### 1.2 CurriculumVersion

A specific versioned snapshot of a curriculum (e.g. "GDPT 2018 v1.0 — Effective 2023-09-01").

- Tied to `Curriculum` via FK.
- Has `effective_from / effective_to` dates.
- `is_active` flag indicates the current live version.
- **Version immutability rule**: once a `CurriculumVersion` is published, existing entities under it must not be silently mutated to point to a new version. Create a new version snapshot instead.

### 1.3 Subject

A single taught subject within a specific `CurriculumVersion`.

- e.g. `Toán THCS`, `Ngữ Văn 8`
- Scoped by `curriculum_version_id` + unique `code`.
- Has `grade_level` (1–12) and `order_index`.

### 1.4 Chapter (Chương)

A grouping of related content within a `Subject`. Corresponds to a chapter in a textbook.

- **Chapter = nhóm nội dung chương trình.**
- e.g. `Chương I: Số hữu tỉ`
- Has `order_index` and `code` (scoped unique within subject).

### 1.5 Topic (Chủ đề)

A specific learning topic within a `Chapter`.

- **Topic = chủ đề học.**
- e.g. `Phép cộng và trừ số hữu tỉ`
- Has `order_index`, `code`, `estimated_periods` (teaching time).

### 1.6 ProblemType (Dạng bài)

A categorized problem type, pedagogically distinct, assigned to a `Topic`.

- **ProblemType = dạng bài** — the unit at which teachers plan exercises and students track mastery.
- e.g. `PT_ADD_SUB_RATIONAL`, `PT_WORD_PROBLEM_RATIONAL`
- Has `difficulty`, `order_index`, `is_active`.
- Linked to `Concept` nodes (knowledge components) via `ProblemTypeConcept` bridge (with `weight` + `is_primary`).
- Linked to `LearningOutcome` nodes via `ProblemTypeLearningOutcome` bridge.

---

## 2. Knowledge Graph

### 2.1 Concept (Kiến thức / Kỹ năng)

A reusable knowledge component or cognitive skill, **independent of ProblemType hierarchy**.

- **Concept = kiến thức / kỹ năng tái sử dụng.**
- Belongs to a `Subject` (not to a specific Topic or Chapter — Concepts are reusable across topics).
- e.g. `CONC_RATIONAL_DEFINITION` (Định nghĩa số hữu tỉ), `CONC_COMMON_DENOMINATOR` (Quy đồng mẫu số)
- Has stable `code`, `name`, `description`, `order_index`.

**Key distinction:** A ProblemType is a _task category_ ("what kind of problem is this?"). A Concept is a _knowledge component_ ("what understanding does solving it require?"). Multiple ProblemTypes can share the same Concepts.

### 2.2 Concept Prerequisite Graph

Concepts are connected in a **directed acyclic graph (DAG)** via the `concept_relations` table.

| Column | Description |
|--------|-------------|
| `source_concept_id` | The prerequisite concept |
| `target_concept_id` | The concept that depends on the source |
| `relation_type` | `PREREQUISITE`, `PART_OF`, or `RELATED_TO` |

**Invariants enforced at service layer:**
1. No self-relations.
2. No cycles — enforced by recursive CTE reachability check + `pg_advisory_xact_lock`.
3. Cross-subject edges forbidden — source and target must share the same `subject_id` (**CRITICAL**: fixed in `ConceptGraphService.create_relation()`).

**The graph is SHARED and CANONICAL — it is NEVER copied per student.** Student mastery is stored as scalar scores keyed by `(student_id, concept_id)`.

### 2.3 LearningOutcome (Yêu cầu cần đạt)

A specific, measurable outcome aligned to a `Subject` and optionally a `grade_level`.

- **LearningOutcome = yêu cầu cần đạt.**
- e.g. "Học sinh có thể quy đồng mẫu số hai phân số và thực hiện phép cộng."
- Has `code`, `description`, `grade_level`, `source_reference`.
- Linked to `ProblemType` via `problem_type_learning_outcomes` bridge.

---

## 3. Question Bank

### 3.1 Question (Câu hỏi — Evidence source)

A single question item serving as evidence for assessing mastery.

- **Question = evidence source** — each attempt provides a signal used by the Mastery Engine.
- Has `content`, `question_type` (MULTIPLE_CHOICE / TRUE_FALSE / SHORT_ANSWER / OPEN_RESPONSE), `difficulty`, `cognitive_level`.
- `content_hash` (SHA-256 of normalized content) — prevents exact duplicates.
- `status`: `DRAFT` → `REVIEW` → `APPROVED` → `ARCHIVED`. **Only `APPROVED` questions are used in learning sessions.**
- `created_by` tracks authorship.
- Provenance: `source_type`, `source_reference`, `source_year`.

**Relationships:**
- `Question ↔ ProblemType`: N:N via `question_problem_types` (with `weight`, `is_primary`).
- `Question ↔ Concept`: N:N via `question_concepts` (with `weight`, sum ≤ 1.0).
- `Question ↔ LearningOutcome`: N:N via `question_learning_outcomes`.

**Scaffolded hints** are stored in `question_hints` indexed by `(question_id, hint_level)`. Hint Levels 1–3 must not reveal the final answer.

---

## 4. Mastery Model

### 4.1 StudentProblemTypeMastery (Mức thành thạo dạng bài)

Tracks a student's mastery of a specific **ProblemType**.

- **StudentProblemTypeMastery = mức thành thạo dạng bài.**
- Keyed by `(student_id, problem_type_id)` — unique composite primary key, no duplicates.
- Fields: `mastery_score` [0,1], `confidence` [0,1], `attempt_count`, `correct_count`, `last_practiced_at`.
- Updated deterministically by the **Mastery Engine** after each `QuestionAttempt`. **AI cannot mutate this table.**

### 4.2 StudentConceptMastery (Mức thành thạo concept)

Tracks a student's mastery of a specific **Concept**.

- **StudentConceptMastery = mức thành thạo concept.**
- Keyed by `(student_id, concept_id)` — unique composite PK.
- Fields: `mastery_score` [0,1], `confidence` [0,1], `attempt_count`, `correct_count`.
- Updated by the Mastery Engine based on performance on Questions that map to this Concept.
- **Stored separately from `StudentProblemTypeMastery` — no conflation.**

### 4.3 Chapter/Topic Mastery (Derived aggregates)

Chapter and Topic mastery scores are **NOT stored as a separate source of truth**. They are **computed on-demand** by `MasteryAggregationService` as weighted averages of the constituent `StudentProblemTypeMastery` scores.

- **Chapter/Topic mastery = derived aggregate.**
- Computing these on-the-fly ensures there is always exactly one source of truth: `StudentProblemTypeMastery` and `StudentConceptMastery`.
- No separate `StudentChapterMastery` or `StudentTopicMastery` tables exist.

---

## 5. Entity Relationship Summary

```
Curriculum
  └── CurriculumVersion
        └── Subject ──────────────── Concept (N per Subject, reusable)
              │                          │
              └── Chapter                └── ConceptRelation (DAG edges)
                    └── Topic                │
                          └── ProblemType ──┘ (via ProblemTypeConcept)
                                │
                                └── LearningOutcome (via ProblemTypeLearningOutcome)
                                │
                        Question Bank
                        Question ──── ProblemType (via QuestionProblemType)
                        Question ──── Concept     (via QuestionConcept)
                        Question ──── LearningOutcome (via QuestionLearningOutcome)

Student
  ├── StudentProblemTypeMastery  (per ProblemType — ATOMIC source)
  ├── StudentConceptMastery       (per Concept — ATOMIC source)
  └── Chapter/Topic aggregates    (DERIVED — computed from above)
```

---

## 6. Design Rules

| Rule | Description |
|------|-------------|
| **Stable codes** | Every entity has a stable uppercase `code` enforced by check constraint |
| **Version scoping** | Subjects, Chapters, Topics, ProblemTypes are scoped to a `CurriculumVersion` |
| **No taxonomy hardcoding** | All taxonomy is data-driven in DB; no hardcoded subject/chapter/topic strings in service layer |
| **No per-student graph copies** | `concept_relations` is canonical and shared; student state is scalar mastery scores only |
| **Single source of truth** | `StudentProblemTypeMastery` and `StudentConceptMastery` are the only mastery tables |
| **Chapter/Topic aggregation** | Derived on-the-fly — never stored as a parallel source |
| **Concept ≠ ProblemType** | Concept = reusable knowledge component; ProblemType = pedagogical problem category |
| **AI read-only on mastery** | AI cannot write to mastery tables — only the deterministic Mastery Engine can |
