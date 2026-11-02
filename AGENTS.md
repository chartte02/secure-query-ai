# Repository Guidelines

This file is the repository's contributor and agent specification. Keep
`docs/README.md` as the canonical documentation index and update it when a
current document is added, renamed, or archived.

## Project Structure

This repository contains a security research demo for a natural-language
database assistant. Keep the project organized as follows:

- `app/`: Web API, Ollama integration, SQL security gateway, and audit logic.
- `frontend/`: Lightweight demo interface.
- `db/`: PostgreSQL schema, seed data, roles, and migration scripts.
- `tests/`: Unit, integration, and attack-regression tests.
- `docs/`: Research notes, threat model, experiment results, and presentation
  material.
- `scripts/`: Repeatable setup, reset, and demo commands.

Keep attack payloads and synthetic data isolated from production-like
configuration. Never commit real student or personal data.

## Build, Test, and Development Commands

Run commands from the repository root. For the complete WSL sequence, use
[`docs/wsl-guide.md`](docs/wsl-guide.md); do not invent a second startup path.

```bash
.venv/bin/python -m pytest -q
.venv/bin/python -m pytest tests/test_frontend_security.py tests/test_sql_policy.py \
  tests/test_real_gateway.py tests/test_audit_writer.py -q
.venv/bin/python -m pytest tests/db tests/attacks -q
.venv/bin/python scripts/init_db.py --all
.venv/bin/python -m app
```

The first command runs the full suite after Docker is healthy; the second is
the C/frontend regression suite; the third is the database/attack suite; the
fourth creates or reuses the three PostgreSQL fixtures; and the last starts
the loopback-only FastAPI app. Install `requirements-database.lock` for C.
Document environment variables in `.env.example`, never commit `.env`.

## Coding Style & Naming

Use Python 3.11+ with four-space indentation and type hints. Use `snake_case`
for modules, functions, and variables; `PascalCase` for classes; and uppercase
names for constants. Keep SQL policy checks small and independently testable.
Format and lint changed Python files with Ruff. The current C gate is the
scoped command in `docs/wsl-guide.md`; do not claim full-repository Ruff
success unless all historical A files also pass.

## Testing Guidelines

Use `pytest`. Name files `test_*.py` and test functions `test_<behavior>`.
Every new security rule should include both an allowed-query test and a
blocked-query regression test. Tests must use synthetic PostgreSQL fixtures
and must not contact external model providers.

Ollama tests are opt-in via `SECUREQUERY_RUN_OLLAMA_TESTS=1`. Database tests
require initialized Docker fixtures. A passing model-generation test is not
evidence that a query was authorized or executed safely.

## Security & Configuration

Treat all model output, user text, database content, and schema descriptions
as untrusted input. Generated SQL must pass the SQL gateway before execution.
Default demo connections to read-only roles, log decisions without sensitive
values, and keep Ollama local where possible.

`lab_direct` is only a fixed database-control demonstration. The formal
path requires `SECUREQUERY_FORMAL_GATEWAY=true` and uses `RealGateway`.
Never commit credentials, real personal data, generated local `.env` files,
or unreproducible security claims.

## Commits and Pull Requests

Use concise imperative commit subjects, such as `Add column policy checks`.
Commit each complete feature or documentation function separately; verify
tests and `git diff --check` before committing. Push only after the complete
stage is verified and the worktree is clean.
Pull requests should describe the threat model, changed security behavior,
test commands and results, and include screenshots or a short recording for
UI changes. Link the related issue or experiment note when available.
