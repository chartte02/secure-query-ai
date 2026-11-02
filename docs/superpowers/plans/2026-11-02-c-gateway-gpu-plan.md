# C SQL Gateway and GPU Inference Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the in-process C security gateway, connect it to the existing query route and frontend, and make Ollama evaluation prefer and verify GPU inference.

**Architecture:** Keep `SqlGateway.inspect_and_execute(GatewayHandoff) -> GatewayOutcome` as the boundary between A's untrusted model output and B's PostgreSQL. Add focused C modules for SQL policy, execution/result handling, and audit writes; inject one `RealGateway` into the existing FastAPI application. Ollama remains a local provider and never receives database credentials; GPU use is verified by runtime evidence rather than assumed from model availability.

**Tech Stack:** Python 3.11+, FastAPI, Pydantic, SQLGlot 28.6.0, psycopg 3.3.6, PostgreSQL 17, Ollama, pytest, Ruff.

**Spec:** `docs/project-design.md`, `docs/integration.md`, `docs/status.md`, `docs/acceptance-report.md`

## Global Constraints

- Treat model output, user text, database content, and Schema context as untrusted.
- Only the gateway may authorize or execute candidate SQL.
- A's generation service must not receive database credentials or execute SQL.
- `lab_direct` remains a B demonstration executor and must not be renamed as the C gateway.
- Normal query entry uses the fixed hardened profile; baseline and write_lab require explicit lab-only paths.
- All database data remains synthetic; never commit `.env`, credentials, or generated Docker volumes.
- A model rejection is not a security decision; final safety decisions come from gateway policy and PostgreSQL controls.
- GPU use must be verified with `ollama ps` and `nvidia-smi`; CPU fallback must be labeled in evaluation output.

## File Map

- Create: `app/sql_policy.py` for SQLGlot parsing, statement checks, table/column extraction, and policy decisions.
- Create: `app/real_gateway.py` for the async gateway adapter, hardened execution, result limits, masking, and database error mapping.
- Create: `app/audit_writer.py` for append-only `audit.events` writes through `sq_audit_writer`.
- Modify: `app/main.py` to inject `RealGateway` for the formal gateway path without changing the lab switch.
- Modify: `app/config.py` and `pyproject.toml` to define the formal gateway/database extra without adding database access to A-only installs.
- Modify: `app/models.py` only when a missing response field is required by the existing contract.
- Modify: `frontend/index.html`, `frontend/app.js`, and `frontend/styles.css` for the safe-query result panel.
- Create: `tests/test_sql_policy.py`, `tests/test_real_gateway.py`, and `tests/test_audit_writer.py`.
- Modify: `tests/test_query_route.py`, `tests/test_query_lab.py`, and `tests/test_frontend_security.py` for integration coverage.
- Create: `scripts/verify_ollama_gpu.py` or an equivalent documented command if a machine-readable GPU preflight is needed.
- Modify: `docs/status.md`, `docs/integration.md`, `docs/acceptance-report.md`, and `docs/README.md` after each completed milestone.

### Task 1: Freeze the C policy contract

**Files:**
- Modify: `docs/integration.md`
- Modify: `docs/status.md`
- Test: `tests/test_query_route.py`

**Interfaces:**
- Consumes: existing `GatewayHandoff`, `QueryGatewayDecision`, `QueryResult`, `QueryError`, and `QueryResponse`.
- Produces: the exact reason-code and status matrix used by later gateway tasks.

- [ ] **Step 1: Add contract tests for every terminal state**

Add tests for:

```text
ALLOW + result -> executed
MASK + result -> executed
BLOCK + no result -> blocked
ALLOW/MASK + database error -> error with SQLSTATE
RLS-filtered empty result -> executed with row_count=0
gateway unavailable -> 503 unavailable with result=null
```

- [ ] **Step 2: Run the focused route tests**

Run: `.venv/bin/python -m pytest tests/test_query_route.py -q`

Expected: existing tests pass; new tests fail only for the not-yet-implemented `RealGateway` path.

- [ ] **Step 3: Document fixed reason codes**

Use stable codes such as `MULTIPLE_STATEMENTS`, `NON_READ_ONLY`, `TABLE_DENIED`, `COLUMN_DENIED`, `IDENTITY_SCOPE_DENIED`, `ROW_LIMIT`, `DATABASE_PERMISSION_DENIED`, and `DATABASE_READ_ONLY`.

- [ ] **Step 4: Commit the contract**

```bash
git add docs/integration.md docs/status.md tests/test_query_route.py
git commit -m "Define C gateway outcome contract"
```

### Task 2: Implement independent SQL parsing and policy checks

**Files:**
- Create: `app/sql_policy.py`
- Test: `tests/test_sql_policy.py`
- Modify: `app/diagnostics.py` only if a shared parser helper is extracted without changing A's response behavior.

**Interfaces:**
- Consumes: `GatewayHandoff(principal_id, candidate_sql, schema_version)`.
- Produces:

```python
@dataclass(frozen=True)
class PolicyDecision:
    decision: Literal["ALLOW", "MASK", "BLOCK"]
    reason_code: str
    tables: tuple[str, ...]
    columns: tuple[str, ...]
    mask_columns: tuple[str, ...]
    normalized_sql: str | None
```

- [ ] **Step 1: Write failing parser tests**

Cover one valid single `SELECT`, two statements separated by `;`, `DROP`, `DELETE`, `UPDATE`, modifying CTEs, comments, invalid SQL, unknown tables, unknown columns, and `SELECT *`.

- [ ] **Step 2: Run the parser tests**

Run: `.venv/bin/python -m pytest tests/test_sql_policy.py -q`

Expected: failures because `parse_candidate_sql()` and `authorize_candidate()` do not exist.

- [ ] **Step 3: Implement strict SQLGlot parsing**

Parse exactly one statement using the PostgreSQL dialect. Reject parse errors, multiple statements, non-`SELECT` roots, modifying CTEs, and statements containing `Insert`, `Update`, `Delete`, `Drop`, `Create`, `Alter`, or `Into` nodes. Never execute the original string before parsing succeeds.

- [ ] **Step 4: Implement explicit policy rules**

Use `campus_lab_v1` and fixed actors:

```text
student_s01/student_s02: own rows only
teacher_t01: rows from taught offerings only
api.my_contact: only masked contact view
academic.students.phone/national_id: denied
academic.grades.grader_note: denied
academic/private_auth/audit base tables: denied to model queries
```

Require explicit columns for sensitive policy review; do not treat `SELECT *` as safe. Return `MASK` only for an approved masked view, never after reading a forbidden base column.

- [ ] **Step 5: Run policy tests and lint**

Run: `.venv/bin/python -m pytest tests/test_sql_policy.py -q`

Expected: all policy cases pass and no policy function performs database I/O.

- [ ] **Step 6: Commit**

```bash
git add app/sql_policy.py tests/test_sql_policy.py
git commit -m "Add independent SQL policy checks"
```

### Task 3: Implement hardened execution, masking, and error mapping

**Files:**
- Create: `app/real_gateway.py`
- Test: `tests/test_real_gateway.py`
- Modify: `app/models.py` only if result metadata cannot represent the existing contract.
- Modify: `requirements-dev.lock` or the project database extra if the runtime install does not expose `psycopg`.

**Interfaces:**
- Consumes: `GatewayHandoff` and `PolicyDecision`.
- Produces:

```python
class RealGateway:
    executor = "gateway"

    async def inspect_and_execute(
        self, handoff: GatewayHandoff
    ) -> GatewayOutcome:
        ...
```

- [ ] **Step 1: Add gateway unit tests with fake connections**

Test allowed queries, blocked queries never opening a cursor, masked views, row limits, empty RLS results, `42501`, `25006`, `57014`, malformed database rows, and unexpected result/error combinations.

- [ ] **Step 2: Run the gateway tests**

Run: `.venv/bin/python -m pytest tests/test_real_gateway.py -q`

Expected: failures only because `RealGateway` is absent.

- [ ] **Step 3: Add the database runtime extra**

Keep A-only installation free of database drivers. Define a database installation path such as:

```bash
.venv/bin/python -m pip install -e ".[dev,database]"
```

The extra must provide the pinned psycopg version already used by the lab lock file.

- [ ] **Step 4: Implement the async adapter**

Use `asyncio.to_thread()` around synchronous psycopg work, call `query_connection(handoff.principal_id, profile="hardened")`, set a read-only transaction, execute only `normalized_sql`, fetch at most `MAX_ROWS + 1`, and close the connection in all paths.

- [ ] **Step 5: Implement result conversion**

Convert database columns to `QueryColumn`, JSON-safe cell values to `QueryResult.rows`, set `truncated` when more than `MAX_ROWS` rows exist, and report `execution_ms`. Preserve RLS empty results as a successful empty result.

- [ ] **Step 6: Implement database error conversion**

Map SQLSTATE `42501` to `database_permission_denied`, `25006` to `database_read_only`, `57014` to `database_timeout`, and all other psycopg errors to a stable `database_error`. Do not include raw SQL, credentials, or stack traces in `QueryError.message`.

- [ ] **Step 7: Run real database gateway tests**

Run: `.venv/bin/python -m pytest tests/test_real_gateway.py tests/db tests/attacks -q`

Expected: policy and database tests pass against the fresh Docker lab; no write reaches `hardened`.

- [ ] **Step 8: Commit**

```bash
git add app/real_gateway.py app/models.py pyproject.toml requirements-dev.lock tests/test_real_gateway.py
git commit -m "Implement hardened SQL gateway execution"
```

### Task 4: Add append-only business audit

**Files:**
- Create: `app/audit_writer.py`
- Test: `tests/test_audit_writer.py`
- Modify: `app/query_service.py`
- Modify: `app/main.py`

**Interfaces:**
- Consumes: final `QueryResponse`, request ID, actor ID, database role, decision, reason code, SQL digest.
- Produces:

```python
class AuditWriter(Protocol):
    async def append(
        self,
        *,
        request_id: str,
        actor_id: str,
        db_role: str,
        event_type: str,
        decision: str,
        reason_code: str,
        sql_digest: str,
    ) -> str:
        ...
```

- [ ] **Step 1: Add audit schema contract tests**

Verify one insert into `audit.events`, returned UUID `audit_id`, no readable SQL/question in stored fields, and no read/update/delete capability for the audit writer.

- [ ] **Step 2: Implement parameterized append**

Use `sq_audit_writer`, parameterized SQL, UTC timestamp, and a UUID event ID. Use the existing `audit.events` columns exactly: `event_id`, `run_id`, `actor_id`, `db_role`, `event_type`, `decision`, `reason_code`, `sql_digest`, `occurred_at`.

- [ ] **Step 3: Integrate after gateway outcome validation**

Ensure BLOCK, ERROR, ALLOW, MASK, model refusal, invalid output, and unavailable paths each produce a safe audit event. Keep the existing application log digest behavior as a secondary diagnostic; database audit is the business record.

- [ ] **Step 4: Run audit tests**

Run: `.venv/bin/python -m pytest tests/test_audit_writer.py tests/test_query_route.py tests/db/test_permissions.py -q`

Expected: all outcomes produce the right decision and no sensitive raw SQL is persisted.

- [ ] **Step 5: Commit**

```bash
git add app/audit_writer.py app/query_service.py app/main.py tests/test_audit_writer.py
git commit -m "Persist gateway decisions to audit events"
```

### Task 5: Inject the formal gateway without weakening lab isolation

**Files:**
- Modify: `app/main.py`
- Modify: `app/config.py`
- Test: `tests/test_query_route.py`
- Test: `tests/test_query_lab.py`

**Interfaces:**
- Consumes: `RealGateway`, `LocalLabGateway`, and `NotConnectedGateway`.
- Produces: formal `executor="gateway"` mode and explicit `executor="lab_direct"` mode.

- [ ] **Step 1: Add configuration tests**

Test that the formal gateway path is explicit and that `SECUREQUERY_LAB_GATEWAY=true` cannot silently select the formal gateway.

- [ ] **Step 2: Inject `RealGateway`**

Use `create_app(..., gateway=...)` for tests. In normal local demo configuration, select `RealGateway` only when the database extra and local lab are available; otherwise retain the safe `NotConnectedGateway` 503 behavior. Keep `lab_gateway` as an explicitly named B-only mode.

- [ ] **Step 3: Add end-to-end status tests**

Verify:

```text
normal own query -> 200 executed / ALLOW
sensitive approved view -> 200 executed / MASK
blocked SQL -> 200 blocked / BLOCK
database permission error -> 200 error / SQLSTATE
gateway unavailable -> 503 unavailable
lab replay -> executor=lab_direct
```

- [ ] **Step 4: Run the integration suite**

Run: `.venv/bin/python -m pytest tests/test_query_route.py tests/test_query_lab.py tests/test_api.py -q`

Expected: formal and lab paths are distinguishable in every response.

- [ ] **Step 5: Commit**

```bash
git add app/main.py app/config.py tests/test_query_route.py tests/test_query_lab.py
git commit -m "Connect formal gateway to query service"
```

### Task 6: Connect the safe-query frontend

**Files:**
- Modify: `frontend/index.html`
- Modify: `frontend/app.js`
- Modify: `frontend/styles.css`
- Test: `tests/test_frontend_security.py`

**Interfaces:**
- Consumes: `POST /api/v1/queries` and the existing catalog response.
- Produces: a separate “安全查询” action and a result panel that never sends user-edited SQL.

- [ ] **Step 1: Add frontend security tests**

Verify all dynamic values use text nodes, no `innerHTML` or dynamic HTML templates are introduced, and the UI distinguishes `executed`, `blocked`, `error`, `unavailable`, and empty results.

- [ ] **Step 2: Add the safe-query action**

Send only `question`, `principal_id`, and `context_profile` to `/api/v1/queries`. Do not send `candidate_sql`, role, DSN, prompt profile, or database URL from the browser.

- [ ] **Step 3: Render decision and result metadata**

Display gateway decision, reason code, policy version, audit ID, database role, row count, truncation, masked columns, SQLSTATE, and safe result cells. Display “查询成功但结果为空” for `executed` with zero rows.

- [ ] **Step 4: Run frontend and API tests**

Run: `.venv/bin/python -m pytest tests/test_frontend_security.py tests/test_query_route.py -q`

Expected: the page renders sanitized results and cannot turn model output into executable browser HTML.

- [ ] **Step 5: Commit**

```bash
git add frontend/index.html frontend/app.js frontend/styles.css tests/test_frontend_security.py
git commit -m "Add safe query result panel"
```

### Task 7: Add GPU-first Ollama verification and evaluation

**Files:**
- Modify: `docs/gpu-inference.md`
- Modify: `docs/local-model-evaluation.md`
- Modify: `scripts/evaluate.py` only if it needs to record processor evidence.
- Create: `scripts/verify_ollama_gpu.py` only if shell-only evidence is insufficient.
- Test: `tests/test_ollama_integration.py`

**Interfaces:**
- Consumes: local Ollama endpoint and selected model.
- Produces: evaluation JSON with model digest, endpoint, processor evidence, latency, and explicit `gpu_verified`/`cpu_fallback` status.

- [ ] **Step 1: Add a GPU preflight check**

Run:

```bash
nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv,noheader
ollama list
ollama run qwen2.5-coder:7b
ollama ps
nvidia-smi
```

The preflight passes only when `ollama ps` reports GPU or CPU/GPU placement and `nvidia-smi` shows Ollama memory use. A CPU-only run is recorded as fallback, not as GPU evidence.

- [ ] **Step 2: Configure the project endpoint**

Use the actual local Ollama port, for example:

```text
SECUREQUERY_PROVIDER=ollama
SECUREQUERY_MODEL=qwen2.5-coder:7b
SECUREQUERY_OLLAMA_BASE_URL=http://127.0.0.1:11434
SECUREQUERY_DEMO_MODE=true
```

- [ ] **Step 3: Add a short smoke benchmark**

Run one normal and one injection case first. Record warm-up latency separately from steady-state latency. Do not execute any generated SQL during this task.

- [ ] **Step 4: Run the fixed evaluation only after GPU verification**

Run: `SECUREQUERY_OLLAMA_BASE_URL=http://127.0.0.1:11434 .venv/bin/python scripts/evaluate.py --provider ollama --model qwen2.5-coder:7b`

Expected: each record includes provider/model/digest, prompt/schema version, latency, and processor evidence; if the model times out, the report says provider timeout and does not report security success.

- [ ] **Step 5: Commit**

```bash
git add docs/gpu-inference.md docs/local-model-evaluation.md scripts/evaluate.py scripts/verify_ollama_gpu.py tests/test_ollama_integration.py
git commit -m "Record GPU-first Ollama evaluation"
```

### Task 8: Complete acceptance and Pre evidence

**Files:**
- Modify: `docs/acceptance-report.md`
- Modify: `docs/status.md`
- Modify: `docs/README.md`
- Create: `artifacts/experiments/c-gateway-acceptance.json`
- Create: `artifacts/screenshots/c-gateway-*.jpg`

- [ ] **Step 1: Run the complete test matrix**

```bash
.venv/bin/python -m pytest tests/test_api.py tests/test_config.py \
  tests/test_diagnostics.py tests/test_evaluation.py \
  tests/test_frontend_security.py tests/test_prompts.py \
  tests/test_providers.py tests/test_generation_attacks.py \
  tests/test_schema_contract.py tests/test_query_route.py \
  tests/test_real_gateway.py tests/test_audit_writer.py -q
.venv/bin/python -m pytest tests/db tests/attacks -q
```

- [ ] **Step 2: Run the five live acceptance scenarios**

Record responses for own grades, sensitive field, cross-student read, direct/indirect injection, and dangerous write. For each response capture `request_id`, `status`, `gateway.decision`, `reason_code`, `audit_id`, `db_role`, `row_count`, `masked_columns`, and SQLSTATE.

- [ ] **Step 3: Verify non-execution**

Confirm that blocked requests have no result, database state is unchanged, and the write_lab reset digest returns to `63ce8f08...`. Confirm the lab replay remains labeled `model_invoked=false`.

- [ ] **Step 4: Run the GPU-backed model smoke test**

Attach `ollama ps` and `nvidia-smi` evidence to the experiment record. Keep model generation metrics separate from gateway security metrics.

- [ ] **Step 5: Prepare the ten-minute Pre**

Use this order:

```text
1 minute: problem and changed database access path
2 minutes: architecture and trust boundaries
4 minutes: three attack cases before/after gateway
2 minutes: metrics and database evidence
1 minute: limitations, GPU status, and conclusions
```

- [ ] **Step 6: Update the status index**

Mark C items complete only when the corresponding test and artifact exist. Keep `lab_direct`, model refusal, and database permission results explicitly separated.

- [ ] **Step 7: Commit the acceptance record**

```bash
git add docs/acceptance-report.md docs/status.md docs/README.md artifacts
git commit -m "Record C gateway acceptance evidence"
```

## Verification Checklist

- [ ] `RealGateway` is the only formal executor.
- [ ] A cannot provide SQL, role, DSN, or prompt profile through `/api/v1/queries`.
- [ ] Multiple statements and every write/DDL form are blocked before database execution.
- [ ] Table, column, and actor policies are independent of model refusal.
- [ ] RLS empty results are not confused with gateway BLOCK.
- [ ] `42501`, `25006`, and timeout errors retain stable classification.
- [ ] Audit rows contain digest and decision but not raw question or SQL.
- [ ] Frontend renders results as text and shows audit ID.
- [ ] `lab_direct` remains explicitly labeled and isolated.
- [ ] Ollama evaluation records GPU placement or an explicit CPU fallback.
- [ ] Final Pre has reproducible commands, screenshots, and a fallback recording.
