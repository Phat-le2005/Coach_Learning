# EduMS — Security Guide

> **Document version:** 1.0 · **Last updated:** 2026-09-22  
> **Classification:** Internal Engineering Reference

---

## 1. Authentication

### 1.1 Token Strategy

EduMS uses a **dual-token, server-side session** model:

| Component | Description |
|-----------|-------------|
| **Access token** | Short-lived JWT (default 15 min). Signed with HS256. Carries `sub` (user_id), `sid` (auth_session_id), `iss`, `aud`, `exp`. |
| **Refresh token** | Opaque random 32-byte URL-safe token. Stored as SHA-256 hash (`refresh_tokens` table). |
| **AuthSession** | Server-side session row. Tracks `revoked_at`, `expires_at`. Every token validation checks the session row. |

**Implementation:** [`app/auth/service.py`](file:///d:/CoachLearning/backend/app/auth/service.py) · [`app/auth/dependencies.py`](file:///d:/CoachLearning/backend/app/auth/dependencies.py)

### 1.2 Token Security Properties

- **Replay attack prevention**: Refresh token rotation with single-use enforcement. If a consumed token is replayed, the entire `AuthSession` is immediately revoked (`revoked_at = now()`).
- **Session invalidation**: Revoking an `AuthSession` invalidates all outstanding access tokens (via server-side session check in `current_user()`).
- **JWT secret**: Required to be ≥ 32 bytes. Validated at startup by Pydantic `field_validator`. Stored in environment variable `JWT_SECRET_KEY`, never hardcoded.
- **Access token expiry**: Configurable via `ACCESS_TOKEN_EXPIRE_MINUTES` (default 15, max 60).
- **Password hashing**: bcrypt via `argon2-cffi` / `passlib`. Auto-rehash on login if cost factor has changed (`check_needs_rehash`).
- **Timing-safe comparison**: Dummy password hash evaluated even when user is not found (prevents user-enumeration timing attacks).

### 1.3 Known Weaknesses

| Severity | Issue | Recommendation |
|----------|-------|----------------|
| **MEDIUM** | In-memory rate limiter resets on server restart; no distributed rate limit on `/auth/login` | Add Redis-backed rate limiting or use a reverse-proxy rule (e.g. nginx limit_req) |
| **LOW** | CORS `frontend_url` is a single allowed origin. Multi-tenant deployments will need `ALLOWED_ORIGINS` list | Add `ALLOWED_ORIGINS` env var as a comma-separated list |

---

## 2. Authorization

### 2.1 Role Model

```
Role.ADMIN    — Full access: curriculum, user management, question approval
Role.TEACHER  — Classroom, TeachingPlan, analytics for own classes
Role.STUDENT  — Own learning data, own attempts, own mastery
Role.PARENT   — Read-only access to linked students' academic summaries
```

**Enforcement:** All endpoints use `Depends(require_role(...))` or `Depends(require_any_role(...))` from [`app/auth/dependencies.py`](file:///d:/CoachLearning/backend/app/auth/dependencies.py). Unauthenticated requests return `401 UNAUTHENTICATED`.

### 2.2 Student Ownership

- Practice sessions, question attempts, mastery records, and diagnostic sessions are keyed to `student_id`.
- The student's `student_id` is resolved from the authenticated `user.id` via `StudentProfile.user_id` — never taken directly from a path parameter without verification.
- Pattern: `student = _student_for_user(user_id)` → `student.id` used for all downstream queries.

### 2.3 Teacher–Class Relationship

- `TeacherStudentAccessService` validates that a teacher has access to a specific student by checking class membership: student must be enrolled in at least one classroom owned by the teacher.
- Teacher analytics, copilot, and mastery views all pass through `_authorize_teacher_student(teacher_user_id, student_id)`.

### 2.4 Parent–Student Relationship

- `ParentDashboardService` verifies the parent-student link via `ParentStudentLink` before returning any data.
- All `/parent/students/{student_id}/*` endpoints call `service.get_student_progress(user.id, student_id)` — the `user.id` (parent) is extracted from the JWT, not the request body.
- Parents cannot access students they are not linked to (returns 403).

### 2.5 Admin-Only Operations

- Curriculum import, question approval/archiving, and user role management are guarded by `require_role(Role.ADMIN)`.
- Public registration (`POST /auth/register`) is restricted to `Role.STUDENT` only.

### 2.6 Known Authorization Gaps

| Severity | Issue | Location |
|----------|-------|----------|
| **MEDIUM** | Teacher can create questions for any `subject_id`, not restricted to subjects in their own classroom | `questions/router.py` |
| **LOW** | No rate limiting on auth `/login` endpoint | `auth/router.py` |

---

## 3. Password Security

- **Algorithm**: bcrypt via `passlib[bcrypt]`.
- **No plaintext passwords** in logs or error messages — Pydantic `SecretStr` used for `LoginRequest.password`.
- **Auto-rehash**: If `password_hasher.check_needs_rehash(hash)` is True at login, the hash is upgraded in-place and committed.
- **Seed demo password**: Minimum 12 characters, validated at startup.

---

## 4. Secrets and Credentials

| Secret | Storage |
|--------|---------|
| `JWT_SECRET_KEY` | `.env` file / environment variable. Min 32 bytes. |
| `DATABASE_PASSWORD` | `.env` / env var. Passed via `SecretStr`. |
| `AI_API_KEY` | `.env` / env var. Passed via `SecretStr`. Never logged. |
| `SEED_DEMO_PASSWORD` | `.env` / env var. Min 12 chars. |

**No secrets are hardcoded** in Python source. The `Settings` class (Pydantic BaseSettings) reads from environment or `.env` file.

> [!CAUTION]
> `Subject.curriculum_version_id` has a hardcoded `LEGACY_CURRICULUM_VERSION_ID` UUID as a column-level default. This is a data default, not a security secret, but it creates a hidden dependency on a seed row being present. See `docs/data-architecture.md` for remediation guidance.

---

## 5. AI Security Guardrails

### 5.1 Prompt Injection Defence

`AIToolPolicy.sanitize_prompt()` scans all user-facing content before injection into prompts for 10 regex patterns:

- `ignore all previous instructions`, `disregard system prompts`, `forget your rules`
- DAN / jailbreak / developer mode phrases
- `<system>` / `[SYSTEM INSTRUCTION]` XML injection attempts
- `reveal system prompt` / `bypass safety filter`

Raises `AIPromptInjectionError` (HTTP 400) in strict mode. RAG document content is wrapped in `<untrusted_rag_data>` delimiters with an explicit security instruction.

### 5.2 AI Zero-Trust Mutations

The following mutations are permanently prohibited for AI processes:

| Prohibited | Reason |
|-----------|--------|
| `StudentConceptMastery` UPDATE | Mastery is deterministic, not AI-driven |
| `StudentProblemTypeMastery` UPDATE | Same |
| Direct score modification on `QuestionAttempt` | Grades must be deterministic |
| User role / permission change | Privilege escalation risk |
| Question status → PUBLISHED directly | Human review required |
| TeachingPlan modification | Teacher-controlled |
| AdmissionRule modification | Official data integrity |
| Canonical curriculum/prerequisite creation | Must be admin-imported |

### 5.3 Tool Allowlist

Each `AITaskType` has an explicit allowlist of tool names in `AIToolPolicy.ALLOWED_TOOLS`. Unknown tools raise `AIUnknownActionError`. Tools not in the task's allowlist raise `AIActionNotAllowedError`.

### 5.4 Output Validation

All AI responses are validated via `AIOutputValidator.validate_structured(raw, SchemaType)` — Pydantic validation. Invalid JSON → `AIInvalidJSONError`. Schema mismatch → `AIOutputValidationError`. Both fail safely without crashing Learning Core.

---

## 6. Privacy

### 6.1 PII Handling

- Student `full_name`, `email`, `date_of_birth`, `school_name` are stored in normalized tables (`users`, `student_profiles`) and are **never logged to AI request logs**.
- `TutorContextBuilder` sends only academic context to AI: mastery scores, concept codes, recent attempt outcomes — never student names or emails.
- Parent AI Summary (`ParentAISummaryService`) uses only learning metrics; private tutor chat content between student and AI is explicitly excluded.

### 6.2 Dataset Exports

- Dataset exports under `data/datasets/` contain **only anonymized, synthetic, or aggregated data**.
- No `name`, `email`, `phone`, `school_specific_id`, or parent data in evaluation datasets.
- All evaluation fixtures use synthetic student identifiers.

### 6.3 Synthetic Data Isolation

- Synthetic student profiles (`is_synthetic=True`) are filtered from all teacher-facing analytics (`include_synthetic=False` parameter in analytics queries).
- DB constraint: `is_synthetic=True` requires `synthetic_profile IS NOT NULL`.

### 6.4 Tutor Memory

- `TutorMemory` stores compact learning summaries (key concepts, recurring errors) — not raw conversation logs.
- Memory items are scoped to `(student_id, subject_id)` and are read-only from the AI's perspective; only the Tutor service can create/update memory via deterministic extraction.

---

## 7. Security Checklist

| Check | Status |
|-------|--------|
| JWT signed with env-variable secret ≥ 32 bytes | ✅ |
| Refresh token rotation + replay revocation | ✅ |
| Password bcrypt hashed, no plaintext in logs | ✅ |
| CORS restricted to configured `FRONTEND_URL` | ✅ |
| Prompt injection scanning on all user inputs | ✅ |
| AI zero-trust mutation guardrails | ✅ |
| Tool allowlist per task type | ✅ |
| Pydantic output validation on all AI responses | ✅ |
| PII excluded from AI request context | ✅ |
| Parent-student relationship verified at service layer | ✅ |
| Teacher-student access verified at service layer | ✅ |
| Admin-only endpoints guarded by require_role(ADMIN) | ✅ |
| Rate limiting on auth /login (distributed) | ⚠️ In-memory only — no Redis |
| No secrets hardcoded in source | ✅ |
