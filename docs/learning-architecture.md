# EduMS — Learning Architecture

> **Document version:** 1.0 · **Last updated:** 2026-09-22

---

## 1. Learning Core Overview

The Learning Core is the heart of EduMS. It is **fully deterministic** — all mastery updates, scoring, and knowledge gap classification are computed from evidence (student attempts), not AI inference.

```
Diagnostic → StudentProblemTypeMastery + StudentConceptMastery
                      │
                      ▼
           Mastery Engine (BKT/DKT)
                      │
                      ├── KnowledgeGapService
                      │         │
                      │         ├── "Dạng bài yếu"  (ProblemType mastery low)
                      │         └── "Concept tiên quyết yếu"  (prerequisite concept mastery low)
                      │
                      ├── RecommendationEngine (next question, ZPD)
                      │
                      └── StudyPlanService (daily tasks)
```

---

## 2. Service Map

| Service | Location | Purpose |
|---------|----------|---------|
| `MasteryEngine` | `app/mastery/engine.py` | Updates `StudentProblemTypeMastery` + `StudentConceptMastery` after each attempt |
| `MasteryQueryService` | `app/mastery/service.py` | Read-only mastery overview with aggregation |
| `MasteryAggregationService` | `app/mastery/aggregation.py` | Computes Chapter/Topic aggregates from ProblemType mastery |
| `KnowledgeGapService` | `app/knowledge_gap/service.py` | Diagnoses gap type: ProblemType weakness vs prerequisite Concept weakness |
| `RecommendationEngine` | `app/recommendation/service.py` | Selects next question from approved bank based on mastery and ZPD |
| `DiagnosticService` | `app/diagnostic/service.py` | Runs initial mastery assessment |
| `StudyPlanService` | `app/planning/study_service.py` | Generates daily learning tasks aligned to TeachingPlan |
| `PracticeService` | `app/practice/service.py` | Manages Quick Check and open practice sessions |
| `HintService` | `app/hints/service.py` | Scaffolded hint delivery (Levels 1–4) |
| `MisconceptionDetector` | `app/misconceptions/` | Classifies recurring error patterns |
| `RepairService` | `app/repair/service.py` | 5-step pedagogical repair sequence |
| `ReviewService` | `app/review/service.py` | Spaced repetition review sessions |

---

## 3. Mastery Model

### 3.1 How Mastery is Updated

After each `QuestionAttempt` is recorded:

1. `MasteryEngine.update_after_attempt(attempt)` is called.
2. It retrieves the question's `QuestionProblemType` and `QuestionConcept` links.
3. Updates `StudentProblemTypeMastery` for each linked ProblemType (weighted by `is_primary`).
4. Updates `StudentConceptMastery` for each linked Concept (weighted by `concept_link.weight`).
5. Both updates committed in a single transaction.

**Formula**: BKT-inspired sigmoid update on `mastery_score` and `confidence`.

### 3.2 Derived Mastery States

`DerivedMasteryState` classifies a `mastery_score`:

| State | Condition |
|-------|-----------|
| `STRONG` | `mastery_score >= 0.75` AND `confidence >= 0.6` |
| `DEVELOPING` | `0.5 <= mastery_score < 0.75` |
| `WEAK` | `mastery_score < 0.5` OR `confidence < 0.4` |
| `REVIEW_DUE` | Strong but not practiced in > N days |
| `NOT_STARTED` | No attempts yet |

### 3.3 Chapter/Topic Aggregation

`MasteryAggregationService.aggregate_topic(topic_id, student_id)`:
- Fetches all `ProblemType` entries under the topic.
- Computes weighted average of `StudentProblemTypeMastery.mastery_score`.
- Returns `TopicMastery(score, state, problem_type_count, weak_count)`.

`aggregate_chapter()` calls `aggregate_topic()` for each topic and averages results.

**No persistent aggregate table.** All values computed on demand.

---

## 4. Distinguishing "Dạng bài yếu" vs "Concept tiên quyết yếu"

This is a **critical semantic distinction** that drives the system's diagnosis and repair flow.

```
                    Student fails a question
                            │
                    KnowledgeGapService.analyze_gap()
                            │
           ┌────────────────┴────────────────┐
           ▼                                 ▼
   ProblemType mastery low           All direct concepts OK,
   (weak on this dạng bài)           but PREREQUISITE concept
                                     mastery is low
           │                                 │
           ▼                                 ▼
   Gap type: PROBLEM_TYPE_WEAKNESS   Gap type: PREREQUISITE_CONCEPT_GAP
           │                                 │
           ▼                                 ▼
   → Practice more questions          → Repair Session targeting
     of this ProblemType                the weak prerequisite Concept
```

### 4.1 KnowledgeGapService Logic

```
1. Load StudentProblemTypeMastery for target problem_type
2. Load direct Concepts (via ProblemTypeConcept)
3. Load StudentConceptMastery for each direct concept
4. Load prerequisite concepts (ConceptRelation WHERE target IN direct_concepts)
5. Load StudentConceptMastery for each prerequisite concept
6. Load active StudentMisconceptions in scope
7. Evaluate deterministic rules:
   - If pt_score < LOW_THRESHOLD (0.50) → PROBLEM_TYPE_WEAKNESS
   - If any prerequisite mastery < LOW_THRESHOLD → PREREQUISITE_CONCEPT_GAP
   - If confirmed misconception exists → MISCONCEPTION
8. If inconclusive AND student provided reasoning text → consult AI (REASONING tier)
9. Backend always classifies final result (AI output is advisory only)
```

**Key invariant**: The gap type is based on **separate mastery tables** — `StudentProblemTypeMastery` for problem type weakness, `StudentConceptMastery` for concept/prerequisite weakness. They are never conflated.

---

## 5. Practice Flow

```
POST /practice/quick-check          → PracticeService.start_quick_check()
                                       Creates PracticeSession (type=QUICK_CHECK, status=ACTIVE)
                                       RecommendationEngine.next_question()
                                       Returns question to student

POST /practice/sessions/{id}/submit → PracticeService.submit_answer()
                                       Records QuestionAttempt
                                       MasteryEngine.update_after_attempt()
                                       KnowledgeGapService.analyze_gap() [if incorrect]
                                       Returns attempt result

GET /hints/{session_id}/question/{question_id}
                                    → HintService.get_hint(level)
                                       Validates session ACTIVE
                                       Checks QuestionAttempt not yet submitted
                                       Returns Hint Level 1/2/3/4
```

**Replay prevention**: `HintService._current_question()` raises `409 QUESTION_ALREADY_ANSWERED` if a `QuestionAttempt` exists for the question in the current session before the hint is requested.

---

## 6. Diagnostic Flow

```
POST /diagnostic/start              → DiagnosticService.start()
                                       Creates DiagnosticSession
                                       Selects initial questions via adaptive selection

POST /diagnostic/sessions/{id}/answer
                                    → DiagnosticService.record_answer()
                                       Records DiagnosticQuestionAssignment result
                                       Adaptive question selection for next question

POST /diagnostic/sessions/{id}/complete
                                    → DiagnosticService.complete()
                                       Creates StudentProblemTypeMastery records
                                       Creates StudentConceptMastery records
                                       Returns initial mastery summary
```

---

## 7. Repair Session (5-Step Pedagogical Sequence)

Triggered when `KnowledgeGapService` confirms a `PREREQUISITE_CONCEPT_GAP` or `MISCONCEPTION`.

```
Step 1: DIAGNOSE          — Confirm the specific weak concept or misconception
Step 2: FOUNDATIONAL      — Review foundational knowledge (pre-authored content)
Step 3: SCAFFOLDED_STEP   — Guided worked example with scaffolded hints
Step 4: COUNTEREXAMPLE    — Expose the misconception via targeted counterexample
Step 5: TRANSFER_CHECK    — Verify concept transfer to a new context
```

On repair completion, `MasteryEngine.record_repair_outcome()` applies a positive lift to the target concept's mastery score.

---

## 8. Study Plan

`StudyPlanService.generate_plan(student_id, classroom_id)`:

1. Reads active `TeachingPlan` for the classroom.
2. Reads student's `AcademicGoal` (target score, deadline).
3. Identifies weak `ProblemType` entries from `StudentProblemTypeMastery`.
4. Prioritizes according to `TeachingPlanItem.priority` + `order_index`.
5. Creates `StudyPlan` with `StudyPlanItem` daily tasks, each targeting a specific `ProblemType`.

The plan is regenerated or updated when mastery changes significantly (threshold-based).

---

## 9. Exam

### 9.1 Scoring

`ExamScoringService` is **fully deterministic**:
- Scores multiple-choice answers by exact match against `correct_answer`.
- Weights by `exam_weight` per question.
- Stores raw scores in `exam_item_responses`.
- Aggregates `total_score` in `exam_attempts`.

**AI cannot modify `total_score` or individual scores.** AI Exam Explanation (post-exam) is read-only — it reads the attempt and provides pedagogical commentary only.

### 9.2 Analytics

`ExamAnalyticsService` provides breakdown by:
- Chapter performance (average score per chapter)
- Topic performance
- ProblemType performance (per-type accuracy)
- Concept evidence (concepts covered by attempted questions)

### 9.3 Simulation Policies

`ExamSimulationService` draws from APPROVED questions using blueprint:
- `ExamBlueprint` specifies target `ProblemType` distribution.
- Questions selected deterministically from approved bank.
- No AI question generation in simulation (only human-approved questions).

---

## 10. Recommendation Engine

`RecommendationEngine.next_question(student_id, problem_type_id, session)`:

1. Fetches APPROVED questions for the target ProblemType.
2. Filters out recently attempted questions.
3. Scores by: difficulty alignment to student mastery (ZPD targeting), recency of last attempt.
4. Returns the best-matching question.

**No AI involved in question selection.** Pure deterministic scoring.

---

## 11. Technical Debt in Learning Core

| Severity | Issue | Location |
|----------|-------|----------|
| **HIGH** | `KnowledgeGapService` calls `session.get(StudentConceptMastery, ...)` in a loop — N+1 query for each concept | `knowledge_gap/service.py` L120–148 |
| **MEDIUM** | `diagnostic` and `diagnostics` are two separate directories — potential confusion | `app/diagnostic/`, `app/diagnostics/` |
| **MEDIUM** | `recommendation` and `recommendations` are two separate directories | `app/recommendation/`, `app/recommendations/` |
| **LOW** | Chapter/Topic aggregate computation re-queries all mastery on every snapshot — consider caching for high-load | `mastery/aggregation.py` |
