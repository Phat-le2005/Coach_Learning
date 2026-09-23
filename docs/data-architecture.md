# EduMS — Data Architecture

> **Document version:** 1.0 · **Last updated:** 2026-09-22

---

## 1. Database

- **Primary**: PostgreSQL (psycopg3 driver via SQLAlchemy 2.x)
- **Test**: SQLite (in-memory, via pytest fixtures)
- **ORM**: SQLAlchemy 2.x with typed `Mapped[...]` annotations
- **Migrations**: Alembic (sequential versioned migration scripts)
- **Session management**: `get_db()` dependency (FastAPI, scoped per-request)

---

## 2. Schema Overview

### 2.1 Core Domains

| Domain | Key Tables |
|--------|-----------|
| Auth | `users`, `auth_sessions`, `refresh_tokens` |
| Profiles | `student_profiles`, `teacher_profiles`, `parent_profiles`, `parent_student_links` |
| Curriculum | `curricula`, `curriculum_versions`, `subjects`, `chapters`, `topics`, `problem_types`, `learning_outcomes`, `curriculum_import_history` |
| Knowledge Graph | `concepts`, `concept_relations`, `problem_type_concepts`, `problem_type_learning_outcomes` |
| Question Bank | `questions`, `question_options`, `question_concepts`, `question_problem_types`, `question_learning_outcomes`, `question_hints`, `question_import_batches`, `question_import_rows` |
| Mastery | `student_problem_type_mastery`, `student_concept_mastery` |
| Practice | `practice_sessions`, `question_attempts`, `practice_question_hints` |
| Diagnostic | `diagnostic_sessions`, `diagnostic_question_assignments` |
| Planning | `academic_goals`, `study_plans`, `study_plan_items` |
| Classes | `classrooms`, `classroom_memberships`, `teaching_plans`, `teaching_plan_items` |
| Assignments | `assignments`, `assignment_items`, `assignment_submissions` |
| Misconceptions | `misconception_definitions`, `student_misconceptions` |
| Repair | `repair_sessions`, `repair_steps` |
| Review | `review_sessions`, `review_items` |
| Tutor | `tutor_sessions`, `tutor_messages`, `tutor_memory_items` |
| RAG | `documents`, `document_chunks` |
| Exams | `exam_blueprints`, `exam_instances`, `exam_attempts`, `exam_item_responses` |
| Admission | `admission_rules`, `admission_rule_versions`, `admission_evaluations` |
| AI | `ai_usage_logs` |

---

## 3. Key Design Decisions

### 3.1 Mastery — Single Source of Truth

```
student_problem_type_mastery  (PK: student_id, problem_type_id)
student_concept_mastery        (PK: student_id, concept_id)
```

These two tables are the **only authoritative mastery stores**. Chapter/Topic aggregates are computed on demand.

> [!IMPORTANT]
> There is **no** `student_chapter_mastery` or `student_topic_mastery` table. Storing aggregates in a separate table would create a dual-write inconsistency risk. `MasteryAggregationService` computes these on-the-fly.

### 3.2 Digital Twin — Transient Snapshot

`StudentDigitalTwinService.get_snapshot()` assembles a `StudentDigitalTwinSnapshot` **in-memory** by reading from normalized tables. There is **no persistent `digital_twin` table** storing a giant JSON blob.

The snapshot is computed by joining:
1. `StudentProblemTypeMastery` → problem type mastery
2. `StudentConceptMastery` → concept mastery
3. `concept_relations` → prerequisite graph edges
4. `practice_sessions` + `question_attempts` → recent attempts
5. `student_misconceptions` → active misconceptions
6. `student_profiles` + `users` → basic profile

**Anti-pattern avoided:** Storing a denormalized JSON snapshot that becomes stale and creates a second source of truth.

### 3.3 Knowledge Graph — No Per-Student Copy

The `concept_relations` edge table is global/shared. `StudentConceptMastery` stores only scalar mastery scores per `(student_id, concept_id)` — not graph structure.

### 3.4 Question Content Hashing

SHA-256 hash of normalized (NFKC, casefold, whitespace-collapsed) question content stored in `content_hash`. Used for duplicate detection. Index: `ix_questions_content_hash`.

> [!WARNING]
> `content_hash` has an index but **no database-level UNIQUE constraint**. Duplicate detection is enforced at service layer only (`QuestionService.create()` and `QuestionImportService`). A race condition between concurrent inserts could bypass the service check. Recommend adding `UniqueConstraint("content_hash")` in a future migration (with deduplication of any existing near-duplicates first).

---

## 4. Indexes

### 4.1 Existing Indexes

| Table | Index | Purpose |
|-------|-------|---------|
| `student_concept_mastery` | `ix_student_concept_mastery_concept_student` | Lookup mastery by concept |
| `student_problem_type_mastery` | `ix_student_problem_type_mastery_problem_student` | Lookup mastery by problem type |
| `questions` | `ix_questions_subject_status_type_difficulty` | Filtered question listing |
| `questions` | `ix_questions_content_hash` | Duplicate detection |
| `questions` | `ix_questions_created_by` | Author filtering |

### 4.2 Missing Indexes (Medium Priority)

| Table | Column(s) | Reason |
|-------|-----------|--------|
| `concept_relations` | `(target_concept_id, relation_type)` | KnowledgeGapService prerequisite lookups |
| `question_attempts` | `(student_id, created_at DESC)` | Recent attempt queries in Digital Twin |
| `practice_sessions` | `(student_id, session_type, status)` | Active session lookup |
| `student_misconceptions` | `(student_id, status)` | Active misconception queries |

---

## 5. Constraints & Cascade Policy

### 5.1 Code Normalization Constraints

Every curriculum entity has a DB-level `CheckConstraint`:
```sql
CHECK (code = upper(trim(code)) AND length(code) > 0)
```
Guarantees codes are always uppercase, trimmed, non-empty.

### 5.2 Cascade Policies

| Parent | Child | Policy |
|--------|-------|--------|
| `student_profiles` | `student_concept_mastery` | `CASCADE` — deleting student removes mastery |
| `student_profiles` | `student_problem_type_mastery` | `CASCADE` |
| `student_profiles` | `practice_sessions` | `CASCADE` |
| `concepts` | `student_concept_mastery` | `RESTRICT` — cannot delete concept with student data |
| `problem_types` | `student_problem_type_mastery` | `RESTRICT` |
| `subjects` | `questions` | `RESTRICT` |
| `questions` | `question_options` | `CASCADE` (orphan-remove) |
| `questions` | `question_concepts` | `CASCADE` |
| `questions` | `question_problem_types` | `CASCADE` |
| `classrooms` | `classroom_memberships` | `CASCADE` |

### 5.3 Unique Constraints

| Table | Constraint |
|-------|-----------|
| `subjects` | `(curriculum_version_id, code)` |
| `chapters` | `(subject_id, code)` |
| `topics` | `(chapter_id, code)` |
| `problem_types` | `(topic_id, code)` |
| `concepts` | `(subject_id, code)` |
| `concept_relations` | `(source_concept_id, target_concept_id, relation_type)` |
| `student_concept_mastery` | PK `(student_id, concept_id)` |
| `student_problem_type_mastery` | PK `(student_id, problem_type_id)` |

---

## 6. N+1 Query Risk Areas

| Location | Risk | Mitigation |
|----------|------|-----------|
| `MasteryQueryService._overview()` | Loads all subjects, chapters, topics, problem_types, concepts, and all mastery records as separate queries | Mitigated: each entity type loaded in a single bulk query; joined in memory |
| `KnowledgeGapService.analyze_gap()` | `session.get(StudentConceptMastery, (student_id, cid))` in a loop | **HIGH**: Convert to single bulk `WHERE concept_id IN (...)` query |
| `digital_twin/repository.py` | Prerequisite edges loaded via IN clause — acceptable |  |

> [!CAUTION]
> `KnowledgeGapService` lines 120–148 call `session.get(StudentConceptMastery, ...)` in a Python `for` loop (one DB round-trip per concept). Refactor to a single `WHERE concept_id IN (...)` query to eliminate N+1.

---

## 7. Transaction Boundaries

### 7.1 Correct Transaction Usage

- Auth session creation and refresh token rotation: single `commit()` per operation.
- Mastery Engine updates: `commit()` wrapping both `StudentProblemTypeMastery` and `StudentConceptMastery` updates atomically.
- Concept graph creation: single `commit()` inside pessimistic-lock block.
- Question creation: single `commit()` including all linked entities (options, concepts, problem types, hints).

### 7.2 Gaps

| Location | Issue |
|----------|-------|
| `KnowledgeGapService` | If deterministic rules update and then AI consultation fails mid-flight, the partial state is committed. No explicit transaction wrapping the full analyze_gap operation. |

---

## 8. Known Data Issues

### 8.1 LEGACY_CURRICULUM_VERSION_ID Hardcoded Default

**File**: `app/subjects/models.py`, `app/subjects/schemas.py`  
**Severity**: HIGH  
**Issue**: `Subject.curriculum_version_id` defaults to a hardcoded UUID constant `LEGACY_CURRICULUM_VERSION_ID`. If this seed row is absent from the database (fresh install without running the seed), any default insert will fail with a FK violation.

**Recommendation**: Remove the column-level default. Make `curriculum_version_id` mandatory in `SubjectCreate` schema. Admin must always specify the target version when creating a subject.

### 8.2 Concept Timestamps Missing

**File**: `app/concepts/models.py`  
**Severity**: MEDIUM  
**Issue**: `Concept` and `ConceptRelation` have no `created_at`, `updated_at`, or `created_by` columns. Cannot audit when concepts were added or modified.

**Recommendation**: Add `created_at`, `updated_at`, `created_by` columns in a future migration.

### 8.3 Curriculum Provenance Missing

**Severity**: MEDIUM  
**Issue**: No `created_by` FK on `Curriculum`, `CurriculumVersion`, `Chapter`, `Topic`, `ProblemType`. Cannot determine which admin created each entity.

**Recommendation**: Add `created_by UUID REFERENCES users(id) ON DELETE RESTRICT` to curriculum entities in a future migration.
