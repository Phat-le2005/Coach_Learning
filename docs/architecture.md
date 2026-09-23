# EduMS — System Architecture

> **Document version:** 1.0 · **Last updated:** 2026-09-22

---

## 1. High-Level Architecture

```
┌─────────────────────────────────────────────────────────┐
│                     Clients                             │
│   Browser (Next.js 14 App Router)  ·  Future Mobile App │
└──────────────────────┬──────────────────────────────────┘
                       │ HTTPS / REST JSON
                       ▼
┌─────────────────────────────────────────────────────────┐
│                  FastAPI Backend                         │
│                                                         │
│  ┌─────────────┐  ┌──────────────┐  ┌───────────────┐  │
│  │ Auth Layer  │  │ Learning Core│  │   AI Gateway  │  │
│  │  JWT + RBAC │  │ (deterministic│  │ (advisory only│  │
│  └─────────────┘  └──────────────┘  └───────────────┘  │
│                                                         │
│  Domains: curriculum · concepts · questions · mastery   │
│           practice · diagnostic · planning · repair     │
│           classes · exams · admission · parents · RAG   │
└──────────────────────┬──────────────────────────────────┘
                       │ SQLAlchemy 2.x
                       ▼
┌─────────────────────────────────────────────────────────┐
│               PostgreSQL (primary)                       │
│   + pgvector extension (RAG embeddings)                  │
└─────────────────────────────────────────────────────────┘
                       │ Embeddings / Chat
                       ▼
┌─────────────────────────────────────────────────────────┐
│         AI Provider (Gemini / OpenAI / Mock)             │
│   Model tiers: FAST · STANDARD · REASONING               │
└─────────────────────────────────────────────────────────┘
```

---

## 2. Backend Structure

```
backend/
├── app/
│   ├── auth/              # JWT, session, password hashing
│   ├── users/             # User accounts, roles
│   ├── students/          # Student profiles, academic goals
│   ├── teachers/          # Teacher profiles
│   ├── parents/           # Parent portal, AI summary
│   ├── classes/           # Classrooms, TeachingPlan, copilot, analytics
│   ├── curriculum/        # Curriculum hierarchy (Version→Subject→Chapter→Topic→ProblemType)
│   ├── subjects/          # Subject management
│   ├── concepts/          # Knowledge graph nodes (Concept) + edge service
│   ├── questions/         # Question Bank (authoring, import, review workflow)
│   ├── hints/             # Scaffolded hint delivery
│   ├── mastery/           # StudentProblemTypeMastery + StudentConceptMastery + aggregation
│   ├── practice/          # Practice sessions, QuestionAttempt recording
│   ├── diagnostic/        # Diagnostic sessions (initial mastery assessment)
│   ├── planning/          # StudyPlan, AcademicGoal, study explanation
│   ├── recommendation/    # Next-question recommendation engine
│   ├── knowledge_gap/     # Gap diagnosis (ProblemType vs Concept weakness)
│   ├── misconceptions/    # Misconception detection + catalog
│   ├── repair/            # 5-step repair sessions
│   ├── review/            # Spaced repetition review
│   ├── digital_twin/      # Transient student snapshot (read-only composite)
│   ├── exams/             # Blueprint, simulation, scoring, analytics, AI explanation
│   ├── assignments/       # Teacher-assigned homework
│   ├── tutor/             # AI Tutor sessions + memory
│   ├── rag/               # Document ingestion + semantic search
│   ├── admission/         # Admission rules (versioned) + AI assistant
│   ├── documents/         # Reserved stub (RAG lives in app/rag/)
│   ├── ai/                # AIGateway, validator, tool_policy, rate_limiter, context_trimmer
│   ├── evaluate/          # Offline evaluation framework (python -m app.evaluate)
│   ├── core/              # Config (Settings), exceptions, base
│   ├── database/          # SQLAlchemy Base, session, model registry
│   └── api/               # FastAPI app assembly, router registration
├── migrations/            # Alembic migration scripts (sequential)
├── tests/                 # pytest test suite (713 tests)
└── data/                  # Seed data, evaluation datasets
```

---

## 3. API Layer

- **Framework**: FastAPI 0.115+
- **Validation**: Pydantic v2 (all request/response schemas)
- **Auth**: `HTTPBearer` scheme, `Depends(require_role(...))` guards
- **Error format**: Uniform `{"code": "...", "message": "..."}` via `ApplicationError`
- **OpenAPI**: Auto-generated at `/docs` and `/redoc`

### 3.1 Router Registration (`app/api/router.py`)

All domain routers are registered here. Prefix convention:
- `/auth` — Auth endpoints
- `/admin/...` — Admin-only curriculum and user management
- `/students/...` — Student self-service
- `/teachers/...` — Teacher operations
- `/parent/...` (also `/parents/...` alias) — Parent portal
- `/classes/...` — Classroom management
- `/practice/...` — Practice sessions
- `/mastery/...` — Mastery queries
- `/ai/tutor` — AI Tutor interactions
- `/exams/...` — Exam operations

---

## 4. Frontend Structure

```
frontend/
└── src/
    ├── app/              # Next.js 14 App Router pages
    │   ├── (auth)/       # Login / Register pages
    │   ├── (student)/    # Student dashboard, practice, mastery
    │   ├── (teacher)/    # Teacher dashboard, classes, analytics
    │   ├── (parent)/     # Parent portal
    │   └── (admin)/      # Admin curriculum management
    ├── lib/
    │   ├── api/          # API client (fetch wrappers)
    │   ├── auth/         # Auth context, token storage
    │   └── hooks/        # React hooks for data fetching
    └── components/       # Shared UI components
```

**Stack**: Next.js 14, TypeScript, Tailwind CSS, shadcn/ui.

---

## 5. Key Architectural Invariants

| Invariant | Description |
|-----------|-------------|
| **Learning Core immunity** | AI outages cannot block practice sessions, mastery updates, or scoring |
| **Single source of truth** | `StudentProblemTypeMastery` and `StudentConceptMastery` are the only mastery stores; Chapter/Topic aggregates are derived |
| **No giant JSON anti-pattern** | Digital Twin is assembled from normalized tables; no persistent JSON snapshot |
| **AI read-only on academic state** | AI cannot write to mastery, scores, curriculum, or permissions |
| **Concept graph per subject** | Cross-subject concept graph edges are forbidden |
| **Synthetic data isolation** | `is_synthetic=True` profiles are filtered from teacher analytics |
| **Stable codes everywhere** | All curriculum, concept, and question entities have stable uppercase codes |

---

## 6. Deployment Notes

- **Environment**: All secrets via environment variables or `.env` file (never hardcoded).
- **Database**: PostgreSQL 15+ with `pgvector`. SQLite for testing only.
- **Migrations**: Run `alembic upgrade head` before starting the server.
- **AI provider**: Set `AI_PROVIDER=gemini` (or `openai`) and `AI_API_KEY` in production. Defaults to `mock` for local development.
- **Seed data**: Run `python -m app.seed` for development data. `python app/import_curriculum.py` for curriculum fixtures.

---

## 7. Module Naming Ambiguities (Technical Debt)

| Issue | Severity |
|-------|----------|
| `app/diagnostic/` AND `app/diagnostics/` — two directories | MEDIUM |
| `app/recommendation/` AND `app/recommendations/` — two directories | MEDIUM |
| `app/documents/` is an empty stub; RAG documents live in `app/rag/` | LOW |

These dual directories create confusion about canonical import paths. The preferred modules are `app/diagnostic/` and `app/recommendation/`. The plural directories should be merged or clearly documented as deprecated aliases.
