# Repository Guidelines

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

The project should use reproducible commands from the repository root:

```bash
python -m pytest
python -m pytest tests/attacks -q
python scripts/reset_db.py
python -m app
```

The first command runs the full suite; the second runs security regression
cases; the third resets the local PostgreSQL fixture; and the last starts the
local application. Document any additional environment variables in
`.env.example`, not in `.env`.

## Coding Style & Naming

Use Python 3.11+ with four-space indentation and type hints. Use `snake_case`
for modules, functions, and variables; `PascalCase` for classes; and uppercase
names for constants. Keep SQL policy checks small and independently testable.
Format and lint changed Python files with the repository’s configured tools
before submitting a change.

## Testing Guidelines

Use `pytest`. Name files `test_*.py` and test functions `test_<behavior>`.
Every new security rule should include both an allowed-query test and a
blocked-query regression test. Tests must use synthetic PostgreSQL fixtures
and must not contact external model providers.

## Security & Configuration

Treat all model output, user text, database content, and schema descriptions
as untrusted input. Generated SQL must pass the SQL gateway before execution.
Default demo connections to read-only roles, log decisions without sensitive
values, and keep Ollama local where possible.

## Commits and Pull Requests

Use concise imperative commit subjects, such as `Add column policy checks`.
Pull requests should describe the threat model, changed security behavior,
test commands and results, and include screenshots or a short recording for
UI changes. Link the related issue or experiment note when available.
