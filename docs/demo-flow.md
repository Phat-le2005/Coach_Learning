# EduMS — Demo Flow

> **Document version:** 1.0 · **Last updated:** 2026-09-22  
> This guide walks through the full EduMS MVP critical path for demonstration purposes.

---

## Prerequisites

```bash
cd backend

# Install dependencies
pip install -r requirements.txt

# Create .env from template
cp .env.example .env
# Edit .env: set DATABASE_*, JWT_SECRET_KEY (≥32 chars), SEED_DEMO_PASSWORD

# Run migrations
alembic upgrade head

# Seed demo data
python -m app.seed

# Start server
uvicorn app.main:app --reload
# → http://localhost:8000
# → Swagger UI: http://localhost:8000/docs
```

---

## Step 1: Admin — Import Curriculum

```http
POST /auth/login
{ "email": "admin@edums.vn", "password": "<SEED_DEMO_PASSWORD>" }
# → access_token (admin)
```

```http
POST /admin/curricula
Authorization: Bearer <admin_token>
{
  "code": "GDPT_2018",
  "name": "Chương trình GDPT 2018",
  "description": "Chương trình giáo dục phổ thông 2018"
}
```

```http
POST /admin/curriculum-versions
{
  "curriculum_id": "<curriculum_id>",
  "code": "GDPT_2018_V1",
  "name": "GDPT 2018 — Phiên bản 1.0",
  "is_active": true,
  "effective_from": "2023-09-01"
}
```

```http
# Create Subject → Chapter → Topic → ProblemType
POST /admin/subjects
POST /admin/chapters
POST /admin/topics
POST /admin/problem-types

# Map ProblemType to Concepts
POST /admin/problem-types/{id}/concepts
# Map ProblemType to LearningOutcomes
POST /admin/problem-types/{id}/learning-outcomes
```

---

## Step 2: Admin — Build Knowledge Graph

```http
# Create Concepts (knowledge components)
POST /admin/concepts
{ "subject_id": "...", "code": "CONC_RATIONAL_DEFINITION", "name": "Định nghĩa số hữu tỉ" }
POST /admin/concepts
{ "subject_id": "...", "code": "CONC_COMMON_DENOMINATOR", "name": "Quy đồng mẫu số" }

# Create prerequisite relationship (CONC_RATIONAL_DEFINITION is prerequisite for CONC_COMMON_DENOMINATOR)
POST /admin/concept-relations
{
  "source_concept_id": "<CONC_RATIONAL_DEFINITION_id>",
  "target_concept_id": "<CONC_COMMON_DENOMINATOR_id>",
  "relation_type": "PREREQUISITE"
}
```

---

## Step 3: Teacher — Set Up Classroom

```http
POST /auth/login
{ "email": "teacher@edums.vn", "password": "<SEED_DEMO_PASSWORD>" }
# → access_token (teacher)

POST /classes
{ "name": "Lớp 7A1", "subject_id": "...", "grade_level": 7 }

POST /classes/{classroom_id}/teaching-plans
{
  "subject_id": "...",
  "start_date": "2026-09-01",
  "status": "ACTIVE"
}

POST /classes/{classroom_id}/teaching-plans/{plan_id}/items
{ "problem_type_id": "...", "priority": 1, "order_index": 1 }
```

---

## Step 4: Student — Join and Set Goal

```http
POST /auth/login
{ "email": "student@edums.vn", "password": "<SEED_DEMO_PASSWORD>" }
# → access_token (student)

POST /classes/{classroom_id}/join
# or teacher: POST /classes/{classroom_id}/members { "student_id": "..." }

POST /students/me/academic-goals
{
  "classroom_id": "...",
  "target_score": 8.0,
  "deadline": "2026-12-01"
}
```

---

## Step 5: Student — Run Diagnostic

```http
POST /diagnostic/start
{ "classroom_id": "..." }
# → diagnostic_session_id, first question

POST /diagnostic/sessions/{id}/answer
{ "question_id": "...", "selected_option": "B" }
# → next question or completion signal

POST /diagnostic/sessions/{id}/complete
# → StudentProblemTypeMastery and StudentConceptMastery created
# → Digital Twin initialized
```

---

## Step 6: Student — View Study Plan and Practice

```http
GET /students/me/study-plan
# → Daily tasks, ordered by TeachingPlan priority + mastery weakness

POST /practice/quick-check
{ "problem_type_id": "...", "classroom_id": "..." }
# → session_id, first question

# Student submits WRONG answer
POST /practice/sessions/{session_id}/submit
{ "question_id": "...", "selected_option": "A" }
# → is_correct: false
# → MasteryEngine reduces mastery_score
# → KnowledgeGapService runs:
#    → Detects: PREREQUISITE_CONCEPT_GAP (CONC_COMMON_DENOMINATOR)
```

---

## Step 7: Student — Request Hint and Trigger Repair

```http
GET /hints/{session_id}/question/{question_id}?level=1
# → Hint Level 1 (directional, no answer spoiler)

# Second wrong attempt on same concept
POST /practice/sessions/{session_id}/submit
{ "question_id": "...", "selected_option": "C" }
# → MisconceptionDetector confirms: CONC_COMMON_DENOMINATOR misconception

POST /repair/start
{ "misconception_definition_id": "...", "student_id": "..." }
# → repair_session_id, Step 1: DIAGNOSE

POST /repair/sessions/{id}/complete-step
{ "step_type": "DIAGNOSE", "response": "..." }
# → Step 2: FOUNDATIONAL
# ... repeat for SCAFFOLDED_STEP, COUNTEREXAMPLE, TRANSFER_CHECK

POST /repair/sessions/{id}/complete
# → MasteryEngine: positive lift on CONC_COMMON_DENOMINATOR
```

---

## Step 8: Teacher — View Analytics and Copilot

```http
GET /classes/{classroom_id}/analytics/heatmap
# → Per-ProblemType mastery heatmap for all students

GET /classes/{classroom_id}/analytics/prerequisite-signals
# → Students with weak prerequisite concepts

GET /classes/{classroom_id}/analytics/intervention-alerts
# → Students needing intervention

POST /classes/{classroom_id}/copilot
{ "question": "Lớp đang gặp khó khăn ở đâu?" }
# → Teacher Copilot AI analysis (read-only, no plan modification)
```

---

## Step 9: Parent — Weekly Dashboard

```http
POST /auth/login
{ "email": "parent@edums.vn", "password": "<SEED_DEMO_PASSWORD>" }

GET /parent/students
# → List of linked students

GET /parent/students/{student_id}/weekly-data
# → Minutes studied, questions completed, accuracy rate

POST /parent/students/{student_id}/ai-summary
# → AI-generated pedagogical weekly summary (no private chat content)
```

---

## Step 10: Student — Exam Simulation

```http
POST /exams/simulate
{ "blueprint_id": "...", "classroom_id": "..." }
# → exam_attempt_id, questions

POST /exams/{attempt_id}/responses/{item_id}
{ "selected_option": "B" }

POST /exams/{attempt_id}/submit
# → Deterministic scoring: total_score, per-question results

GET /exams/{attempt_id}/analytics
# → Breakdown by Chapter / Topic / ProblemType

GET /exams/{attempt_id}/ai-explanation
# → AI explains answers pedagogically (cannot modify total_score)
```

---

## Step 11: Verification Commands

```bash
# Run full integration test (42 milestones)
pytest tests/integration/test_mvp_critical_path.py -v

# Run evaluation framework
python -m app.evaluate

# Run full regression suite
pytest tests/ -q
# → Expected: 713 passed, ~11 skipped, 0 failed
```

---

## Key Demo Assertions

| Assertion | How to verify |
|-----------|--------------|
| AI outage doesn't break learning | Kill AI provider → practice session still works |
| Synthetic data excluded from teacher view | Create synthetic profile, check analytics excludes it |
| AI cannot modify mastery | Directly call `AIToolPolicy.assert_mutation_allowed("STUDENT", "PROBLEM_TYPE_MASTERY_UPDATE")` → raises `AIForbiddenMutationError` |
| Cross-subject concept edges blocked | Attempt to create PREREQUISITE relation between concepts of different subjects → 422 CROSS_SUBJECT_RELATION |
| Exam score unchanged after AI explanation | Check `exam_attempts.total_score` before and after `/ai-explanation` call |
