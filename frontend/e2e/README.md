# Coach Learning — Real-Browser E2E QA Harness & Dedicated QA Database Setup

This directory contains the Playwright real-browser E2E acceptance and regression suite (`01-ocr-and-ink.spec.ts` through `05-concurrency-and-faults.spec.ts`) and its isolated database fixture helper (`qa_db_helper.py`).

## Safety Guarantees (Fail-Closed)

1. **No Hardcoded Credentials**:
   - `helpers.ts` and `qa_db_helper.py` require `QA_E2E_PASSWORD` (>= 12 characters) from the environment or the local untracked file `.tmp/tri-ocr-e2e/.qa-e2e.env`.
   - Missing or empty `QA_E2E_PASSWORD` fails immediately with `QA_E2E_CONFIG_ERROR`.
2. **Production Rejection**:
   - Setting `APP_ENV=production` (in process env or backend `Settings`) is unconditionally rejected with `QA_E2E_SAFETY_ERROR`.
3. **Dedicated QA Database Enforcement**:
   - `QA_E2E_DATABASE_NAME` must be explicitly configured and must name a dedicated QA database containing a `qa` token (e.g. `edums_qa_e2e`).
   - Ordinary development or shared databases (`edums`, `postgres`, `main`, `dev`, `development`, `staging`, `production`, `prod`) are strictly forbidden.
   - Before any fixture operation, `qa_db_helper.py` verifies that:
     1. `QA_E2E_DATABASE_NAME == Settings.database_name` (`DATABASE_NAME`)
     2. `SELECT current_database()` on the active PostgreSQL connection equals `QA_E2E_DATABASE_NAME`
4. **QA-Owned Record Scope**:
   - Mutations (`create-attempt`, `bump-revision`) only operate on records owned by `qa.ocr.e2e.isolated@edums.edu.vn` and question fixtures tagged with `source_type = "QA_ISOLATED_FIXTURE"`.

---

## Step-by-Step Local Dedicated QA Database Setup

### 1. Create the untracked local QA configuration file

Create `.tmp/tri-ocr-e2e/.qa-e2e.env` (which is ignored by Git via `.tmp/`):

```ini
APP_ENV=test
DATABASE_NAME=edums_qa_e2e
QA_E2E_DATABASE_NAME=edums_qa_e2e
QA_E2E_PASSWORD=<choose-a-local-12+-char-qa-password>
```

### 2. Bootstrap and migrate the dedicated `edums_qa_e2e` database

Run `qa_db_helper.py bootstrap-qa-db` using the backend Python environment. This creates `edums_qa_e2e` if it does not exist, enables `pgvector`, applies all Alembic migrations, and seeds the isolated `MATH_G12` subject and QA student without touching the normal `edums` development database:

```powershell
backend\.venv\Scripts\python.exe frontend\e2e\qa_db_helper.py bootstrap-qa-db
```

### 3. Start the FastAPI backend connected to `edums_qa_e2e`

Start the backend with `APP_ENV=test` and `DATABASE_NAME=edums_qa_e2e` so all browser BFF requests during E2E runs target `edums_qa_e2e`:

```powershell
$env:APP_ENV = "test"
$env:DATABASE_NAME = "edums_qa_e2e"
Set-Location backend
..\.tmp\py312\python.exe -m app
```

### 4. Run the Playwright E2E Suite

```powershell
Set-Location frontend
npx playwright test --config playwright.config.ts
```
