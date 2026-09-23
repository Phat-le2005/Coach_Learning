# EduMS — AI Architecture

> **Document version:** 1.0 · **Last updated:** 2026-09-22

---

## 1. Principles

1. **AI is advisory, not authoritative.** The Learning Core (mastery calculation, scoring, knowledge gap detection) runs deterministically. AI augments presentation and explanation — it does not decide mastery scores.
2. **Provider abstraction.** All AI calls pass through `AIGateway`. Domain services never call provider SDKs directly.
3. **Graceful degradation.** AI outages trigger fallback templates. Learning Core continues unaffected.
4. **Context budget enforced.** AI receives only the minimum context needed. Full Digital Twin, full chat history, and full mastery graphs are never sent.
5. **Zero-trust mutations.** AI cannot write to any academic state tables directly.

---

## 2. Provider Abstraction

```
Domain Service
      │
      ▼
  AIGateway   ◄──── ModelRoutingPolicy (FAST / STANDARD / REASONING)
      │
      ▼
  AIProvider (interface)
      │
      ├── GeminiProvider   (production)
      └── MockProvider     (test / offline)
```

**Key files:**
- [`app/ai/gateway.py`](file:///d:/CoachLearning/backend/app/ai/gateway.py) — Central gateway, orchestrates all calls
- [`app/ai/provider.py`](file:///d:/CoachLearning/backend/app/ai/provider.py) — Abstract provider protocol
- [`app/ai/routing_policy.py`](file:///d:/CoachLearning/backend/app/ai/routing_policy.py) — Tier-to-model mapping
- [`app/ai/mock_provider.py`](file:///d:/CoachLearning/backend/app/ai/mock_provider.py) — Test/offline mock

### 2.1 Model Routing Tiers

| Tier | Use Case | Default Model |
|------|----------|---------------|
| `FAST` | Hints, quick feedback, parent summary | `gemini-2.5-flash` |
| `STANDARD` | Tutor Q&A, teacher copilot | `gemini-2.5-standard` |
| `REASONING` | Knowledge gap analysis, misconception | `gemini-2.5-pro` |

All model identifiers are **environment-variable-configured** (`AI_MODEL_FAST`, `AI_MODEL_STANDARD`, `AI_MODEL_REASONING`). Never hardcoded in Python.

---

## 3. Task Types

| AITaskType | Purpose | Tier |
|------------|---------|------|
| `TUTOR` | Interactive tutoring Q&A | STANDARD |
| `HINT` | Scaffolded hint generation | FAST |
| `OPEN_RESPONSE_EVALUATION` | Evaluate free-text answers | REASONING |
| `MISCONCEPTION_ANALYSIS` | Classify student error patterns | REASONING |
| `RAG` | Document retrieval + grounding | FAST |
| `STUDY_PLAN_EXPLANATION` | Explain daily study plan to student | FAST |
| `TEACHER_COPILOT` | Class state analysis for teachers | STANDARD |
| `PARENT_SUMMARY` | Weekly academic summary for parents | FAST |
| `QUESTION_GENERATION` | Draft question suggestions | STANDARD |
| `EXAM_ANALYSIS` | Post-exam explanation | STANDARD |
| `ADMISSION_ASSISTANT` | Admissions fact grounding | STANDARD |
| `MEMORY_EXTRACTION` | Extract compact learning memories | FAST |

---

## 4. Prompt Architecture

### 4.1 Prompt Registry

Prompts are stored in versioned files under `app/ai/prompts/<task_type>/`:

```
app/ai/prompts/
  ├── student_tutor/v1.txt
  ├── misconception_detector/v1.txt
  ├── parent_summary/v1.txt
  ├── teacher_copilot/v1.txt
  ├── study_plan_explainer/v1.txt
  ├── admission_assistant/v1.txt
  ├── exam_explanation/v1.txt
  ├── knowledge_gap_analyzer/v1.txt
  └── memory_extractor/v1.txt
```

`PromptRegistry` loads and caches prompt templates at startup. Version is tracked in the filename. **No prompts are hardcoded inline in Python services.**

### 4.2 Structured Output

All AI calls that require structured data use `AIOutputValidator.validate_structured(raw, PydanticSchema)`:
- Strips markdown fences.
- Parses JSON.
- Validates against a Pydantic schema.
- On failure: raises `AIInvalidJSONError` or `AIOutputValidationError` — never crashes the request handler.

---

## 5. Security Guardrails

### 5.1 Prompt Injection

`AIToolPolicy.sanitize_prompt(text, strict=True)` is called on every user-originating string before prompt assembly. Detects and rejects 10 jailbreak/injection patterns. RAG document content wrapped in `<untrusted_rag_data>` delimiters.

### 5.2 Tool Allowlist

```python
ALLOWED_TOOLS: dict[AITaskType, set[str]] = {
    AITaskType.TUTOR: {"search_relevant_concept", "get_concept_definition",
                       "propose_pedagogical_hint", "get_student_memory"},
    AITaskType.TEACHER_COPILOT: {"propose_teaching_plan_draft", "propose_assignment_draft",
                                  "summarize_class_mastery"},
    ...
}
```

Unknown tools → `AIUnknownActionError`. Unauthorized tools → `AIActionNotAllowedError`.

### 5.3 Prohibited Mutations (Zero-Trust)

AI is permanently blocked from:
- Updating `StudentConceptMastery` or `StudentProblemTypeMastery`
- Modifying exam/attempt scores
- Changing user roles or permissions
- Publishing questions (status = APPROVED)
- Modifying TeachingPlan, AdmissionRule, or canonical curriculum nodes

Enforced by `AIToolPolicy.assert_mutation_allowed()` + `AIForbiddenMutationError`.

### 5.4 Curriculum Code Validation

`AIOutputValidator.validate_curriculum_references(codes, db_session)` verifies that any curriculum/concept codes mentioned in AI output exist in the database. Fake or hallucinated codes raise `AIFakeCurriculumCodeError`.

---

## 6. Context Budget & Trimming

### 6.1 What is sent to AI

**TutorContextBuilder** constructs a lean context (see [`app/ai/tutor_context_builder.py`](file:///d:/CoachLearning/backend/app/ai/tutor_context_builder.py)):

| Included | Not Included |
|----------|-------------|
| Current question + ProblemType | Full Digital Twin |
| Relevant Concepts + prerequisites (scoped) | Full chat history |
| Compact mastery labels (Yếu/Trung bình/Tốt) | Full mastery graph |
| 3 most recent attempts | All QuestionAttempts |
| Session summary (truncated ≤ 500 chars) | Raw DB session objects |
| RAG top-2 relevant chunks | All documents |
| Relevant memory items (≤ 4) | All student memories |

### 6.2 ContextTrimmer

`ContextTrimmer` enforces hard limits:

| Method | Limit |
|--------|-------|
| `trim_text(text, max_chars)` | Word-boundary safe truncation |
| `trim_session_summary(text)` | Max 500 chars |
| `trim_rag_chunks(chunks, top_k=3)` | Max 3 chunks, 500 chars each |
| `trim_items(items, max_items=4)` | Max 4 memory/concept items |

Global limit: `AI_MAX_CONTEXT_CHARS = 3000` (configurable).

### 6.3 RAG Top-K

Default RAG retrieval: `AI_RAG_TOP_K = 3` chunks. Configurable via env var.

---

## 7. Resilience & Failure Handling

### 7.1 Retry Policy

`_execute_with_resilience()` in `AIGateway`:
- **Retries** on: `AIRateLimitError`, `TimeoutError`, `ConnectionError`
- **Max retries**: `AI_MAX_RETRIES = 2` (configurable, max 5)
- **Backoff**: exponential `0.1 * 2^(attempt-1)` seconds
- **Timeout**: `AI_TIMEOUT_SECONDS = 30.0` per call (configurable)

### 7.2 Domain Error Mapping

`AIErrorMapper.map_exception()` maps provider-specific errors to domain exceptions:

| Provider Error | Domain Exception |
|----------------|-----------------|
| HTTP 429 / quota exceeded | `AIRateLimitError` |
| HTTP 503 / network error | `AIServiceUnavailableError` |
| `asyncio.TimeoutError` | `AITimeoutError` |
| Invalid JSON | `AIInvalidJSONError` |

### 7.3 Learning Core Immunity

When AI is unavailable:
- Mastery Engine continues to update scores deterministically from attempts.
- `KnowledgeGapService` uses deterministic rules first; AI consultation is optional.
- `HintService` falls back to pre-authored `QuestionHint` templates.
- `TeacherCopilotService` returns a structured fallback without AI narrative.
- `ParentAISummaryService` returns a template-based summary.

**Core endpoints (`/practice/*`, `/mastery/*`, `/diagnostic/*`) are NEVER blocked by AI quota.**

---

## 8. Rate Limiting

`AIRateLimiter` (in-memory, per-user):

| Limit | Default | Config Var |
|-------|---------|------------|
| Per minute | 20 req/min | `AI_RATE_LIMIT_PER_MINUTE` |
| Per day | 100 req/day | `AI_DAILY_REQUESTS_LIMIT_PER_STUDENT` |

`require_ai_rate_limit` FastAPI dependency applied to all AI endpoints. Core learning endpoints are **excluded** from this limiter.

> [!WARNING]
> Rate limiter is **in-memory only**. In a multi-process/multi-server deployment, limits are not shared across processes. Migrate to Redis-backed rate limiting for production scale.

---

## 9. Usage Tracking

`AIUsageService` records per-request:
- `task_type`, `model`, `prompt_tokens`, `completion_tokens`, `latency_ms`
- `student_id`, `session_id` (optional)
- Stored in `ai_usage_logs` table.

Metrics exposed:
- Average latency per task type
- Tokens per task
- Requests per student per day
- Estimated cost per task (via `app/ai/pricing.py` — model-specific rates)
