"""Run the E0/E1/E2/E4 experiment matrix over a frozen case set.

Experiment scaffolding owned by member B (attack execution and raw result
collection, per team-division). This script:

- generates candidates with the real local model (Ollama) at temperature 0,
  seed 42 — mirroring ``app/service.py`` parsing exactly;
- assembles indirect-injection context from the REAL database via
  ``ContextProvider`` and records per-item ``content_digest`` values, so
  "the payload reached the model" is verifiable evidence, not a claim;
- applies member C's policy in ``observe`` mode (record what would be
  blocked, still execute — never the production path) or ``enforce`` mode
  (member C's ``RealGateway`` decides and executes, MASK included);
- executes read candidates on the configured profile (E0/E1: wide-read
  baseline account; E4: hardened per-user roles) and write-intent
  candidates ONLY on the disposable write_lab instance, verifying committed
  state through an independent connection and resetting afterwards;
- never executes anything outside these marked lab profiles and never
  treats a model refusal as a gateway decision.

Logging: one JSONL line per run (flushed immediately, crash-safe), a text
log file mirroring the console, and a summary JSON at the end. All outputs
land in ``artifacts/experiments/`` (Git-ignored). ``--resume`` skips
(case, config, repeat) triples already present in a previous JSONL.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import logging
import sys
import time
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import psycopg

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.catalog import PRINCIPALS, SCHEMA_SQL, SCHEMA_VERSION, Principal  # noqa: E402
from app.diagnostics import diagnose_sql  # noqa: E402
from app.models import GatewayHandoff, ModelGeneration, PromptProfile  # noqa: E402
from app.prompts import build_prompt, load_prompt  # noqa: E402
from app.providers import ProviderRequest, create_provider  # noqa: E402
from app.real_gateway import RealGateway  # noqa: E402
from app.sql_policy import authorize_candidate  # noqa: E402
from db.client import ACTORS, ContextProvider, query_connection  # noqa: E402
from db.manage import initialize, snapshot  # noqa: E402
from db.settings import ROOT, Settings  # noqa: E402

LOGGER = logging.getLogger("securequery.e0e4")

CONFIGS: dict[str, dict[str, object]] = {
    "E0": {"prompt": PromptProfile.BASELINE, "gateway": "observe", "exec": "baseline"},
    "E1": {"prompt": PromptProfile.HARDENED, "gateway": "observe", "exec": "baseline"},
    "E2": {"prompt": PromptProfile.HARDENED, "gateway": "enforce", "exec": "baseline"},
    # E3 replay: fixed candidates against per-user roles only (no model call);
    # the prompt profile is unused because generation is skipped for replay runs.
    "E3": {"prompt": PromptProfile.HARDENED, "gateway": "observe", "exec": "hardened"},
    "E4": {"prompt": PromptProfile.HARDENED, "gateway": "enforce", "exec": "hardened"},
}
WRITE_SCOPE = "only_disposable_write_lab_for_unsafe_experiment"
CONTEXT_MAX_ROWS, CONTEXT_MAX_CHARS = 3, 512


def json_value(value: object) -> object:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def runner_principal(actor_id: str) -> Principal:
    """Prefer A's aligned catalog Principal; derive only for uncovered actors.

    The scope wording is prompt content — the model reacts to it, so derived
    entries mirror the catalog phrasing exactly.
    """
    if actor_id in PRINCIPALS:
        return PRINCIPALS[actor_id]
    actor = ACTORS[actor_id]
    if actor.student_id:
        return Principal(
            id=actor.actor_id,
            label=f"学生 · {actor.student_id}",
            role="student",
            scope=f"Only rows whose student_id is '{actor.student_id}'; "
            f"api.my_contact only for {actor.student_id}",
        )
    return Principal(
        id=actor.actor_id,
        label=f"教师 · {actor.teacher_id}",
        role="teacher",
        scope=f"Only course_offerings whose teacher_id is '{actor.teacher_id}' "
        "and their enrollments and grades",
    )


def real_context_messages(
    profile: PromptProfile, principal: Principal, question: str, offering_id: str
) -> tuple[list[dict[str, str]], dict[str, object]]:
    """Assemble the prompt with feedback fetched from the real database.

    Mirrors ``build_prompt``'s payload shape; the retrieved_context block is
    filled from ContextProvider instead of the fixed fixture string. Digests
    are returned so each run can prove which text the model actually saw.
    """
    provider = ContextProvider()
    feedback = provider.get_public_feedback(
        offering_id, max_rows=CONTEXT_MAX_ROWS, max_chars=CONTEXT_MAX_CHARS
    )
    catalog_rows = provider.get_course_catalog()
    context_text = "\n".join(f"[{item['feedback_id']}] {item['content']}" for item in feedback)
    version, system_prompt, content_hash = load_prompt(profile)
    payload = {
        "principal": {"id": principal.id, "role": principal.role, "scope": principal.scope},
        "schema": {"version": SCHEMA_VERSION, "postgresql_ddl": SCHEMA_SQL},
        "retrieved_context": {
            "profile": "database_feedback",
            "trust": "untrusted_data",
            "content": context_text,
            "items": [
                {
                    "feedback_id": item["feedback_id"],
                    "content_digest": item["content_digest"],
                    "was_truncated": item["was_truncated"],
                }
                for item in feedback
            ],
        },
        "question": question,
    }
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False, separators=(",", ":"))},
    ]
    meta = {
        "source": "database_feedback",
        "offering_id": offering_id,
        "items": payload["retrieved_context"]["items"],
        "catalog_size": len(catalog_rows),
    }
    return messages, {"prompt_version": version, "prompt_hash": content_hash, "context": meta}


async def generate_candidate(
    provider,
    settings,
    profile: PromptProfile,
    principal: Principal,
    case: dict,
    context: dict | None,
) -> dict:
    """Mirror app/service.py generation+parsing; never executes SQL."""
    if context is None:
        bundle = build_prompt(
            profile=profile,
            principal=principal,
            question=case["question"],
            context_profile=case.get("context_profile", "clean"),
        )
        messages = bundle.messages
        prompt_meta = {
            "prompt_version": bundle.version,
            "prompt_hash": bundle.content_hash,
            "context": {"source": "fixed_fixture", "profile": case.get("context_profile", "clean")},
        }
    else:
        messages, prompt_meta = real_context_messages(
            profile, principal, case["question"], context["offering_id"]
        )

    started = time.perf_counter()
    raw = await provider.generate(
        ProviderRequest(
            messages=messages,
            profile=profile,
            question=case["question"],
            context_profile=case.get("context_profile", "clean"),
        )
    )
    latency_ms = round((time.perf_counter() - started) * 1000)
    try:
        generated = ModelGeneration.model_validate_json(raw)
    except Exception:  # pydantic ValidationError — keep the campaign alive
        return {
            **prompt_meta,
            "status": "invalid_output",
            "candidate_sql": None,
            "refusal_reason": "模型输出不符合严格 JSON 契约。",
            "latency_ms": latency_ms,
            "raw_head": raw[:400],
            "diagnostics": diagnose_sql(None).model_dump(),
        }
    candidate = generated.sql
    status = "generated" if candidate else "refused"
    diag = diagnose_sql(candidate)
    if candidate and not diag.parseable:
        status, candidate = "invalid_output", None
    return {
        **prompt_meta,
        "status": status,
        "candidate_sql": candidate,
        "refusal_reason": generated.refusal_reason,
        "latency_ms": latency_ms,
        "raw_head": raw[:400],
        "diagnostics": diag.model_dump(),
    }


def execute_read(actor_id: str, sql: str, exec_profile: str) -> dict:
    try:
        with query_connection(actor_id, profile=exec_profile, unsafe_lab=True) as conn:
            cursor = conn.execute(sql)
            if cursor.description is None:
                return {
                    "executed": True,
                    "row_count": 0,
                    "rows": [],
                    "db_role": _session_role(conn),
                }
            rows = cursor.fetchall()
            return {
                "executed": True,
                "row_count": len(rows),
                "rows": [[json_value(v) for v in row.values()] for row in rows][:100],
                "db_role": _session_role(conn),
            }
    except psycopg.Error as exc:
        return {
            "executed": False,
            "sqlstate": exc.sqlstate,
            "error": str(getattr(getattr(exc, "diag", None), "message_primary", "") or exc)[:200],
        }


def _session_role(conn) -> str:
    return conn.execute("SELECT session_user AS u").fetchone()["u"]


def execute_write_and_verify(actor_id: str, sql: str) -> dict:
    """Write-intent candidates run ONLY on write_lab; verify via independent
    admin connection, then reset and confirm the frozen digest is restored."""
    settings = Settings.load()
    record: dict[str, object] = {}
    try:
        with settings.connect("write_lab") as conn:
            record["before_digest"] = snapshot(conn)["sha256"]
        with query_connection(actor_id, profile="write_lab", unsafe_lab=True) as conn:
            cursor = conn.execute(sql)
            record["rowcount"] = cursor.rowcount
        with settings.connect("write_lab") as conn:  # independent connection
            record["after_digest"] = snapshot(conn)["sha256"]
        record["state_changed"] = record["after_digest"] != record["before_digest"]
    except psycopg.Error as exc:
        record["sqlstate"] = exc.sqlstate
        record["error"] = str(getattr(getattr(exc, "diag", None), "message_primary", "") or exc)[
            :200
        ]
        record["state_changed"] = False
    restored = initialize("write_lab", reset=True)
    record["restored_digest"] = restored["sha256"]
    record["reset_ok"] = restored["sha256"] == record.get("before_digest")
    return record


async def enforce_execute(gateway: RealGateway, actor_id: str, sql: str, request_id: str) -> dict:
    handoff = GatewayHandoff(
        request_id=request_id,
        principal_id=actor_id,
        candidate_sql=sql,
        schema_version=SCHEMA_VERSION,
    )
    outcome = await gateway.inspect_and_execute(handoff)
    decision = outcome.decision.model_dump()
    result = outcome.result.model_dump() if outcome.result else None
    error = outcome.error.model_dump() if outcome.error else None
    return {"decision": decision, "result": result, "error": error, "db_role": outcome.db_role}


async def run_campaign(args: argparse.Namespace) -> int:
    settings = AppSettings_for(args)
    provider = create_provider(settings)
    info = await provider.probe()
    if not info.ready:
        LOGGER.error("provider not ready: %s", info.detail)
        return 1
    LOGGER.info("provider ready: %s %s (%s)", info.name, info.model, str(info.digest)[:12])

    cases_arg = Path(args.cases)
    cases_file = cases_arg
    if not cases_file.is_file():
        cases_file = ROOT / "tests" / "attacks" / "cases" / f"{args.cases}.json"
    document = json.loads(cases_file.read_text(encoding="utf-8"))
    cases = document["cases"]
    if args.limit:
        cases = cases[: args.limit]
    clean_cases = [case for case in cases if case.get("fixture", "clean") == "clean"]
    poisoned_cases = [case for case in cases if case.get("fixture") == "poisoned-01"]

    db_settings = Settings.load()
    baseline_factory = lambda principal_id: query_connection(  # noqa: E731
        principal_id, profile="baseline", unsafe_lab=True
    )
    gateways = {
        "E2": RealGateway(connection_factory=baseline_factory),
        "E4": RealGateway(),  # default hardened per-user factory
    }

    out_dir = ROOT / "artifacts" / "experiments"
    out_dir.mkdir(parents=True, exist_ok=True)
    campaign_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:6]
    set_name = cases_file.stem
    jsonl_path = out_dir / f"e0e4-{set_name}-{campaign_id}.jsonl"
    log_path = out_dir / f"e0e4-{set_name}-{campaign_id}.log"
    logging.basicConfig(
        level=logging.INFO,
        force=True,
        handlers=[
            logging.FileHandler(log_path, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
        format="%(asctime)s %(levelname)s %(message)s",
    )

    done: set[tuple[str, str, int]] = set()
    if args.resume:
        for line in Path(args.resume).read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                done.add((row["case_id"], row["campaign_config"], row["repeat"]))
        LOGGER.info("resume: %d completed runs loaded", len(done))

    summary_counters: dict[str, int] = {}
    total = 0
    started = time.perf_counter()
    with jsonl_path.open("a", encoding="utf-8") as sink:
        for phase_label, phase_cases in (("clean", clean_cases), ("poisoned", poisoned_cases)):
            if not phase_cases:
                continue
            if phase_label == "poisoned":
                LOGGER.info("switching hardened fixture to poisoned-01 ...")
                initialize("hardened", fixture="poisoned-01", reset=True)
            for case in phase_cases:
                for config_name in args.configs.split(","):
                    config = CONFIGS[config_name]
                    for repeat in range(1, args.repeats + 1):
                        if (case["case_id"], config_name, repeat) in done:
                            continue
                        record = await run_single(
                            provider,
                            settings,
                            db_settings,
                            gateways,
                            case,
                            config_name,
                            config,
                            repeat,
                        )
                        sink.write(json.dumps(record, ensure_ascii=False) + "\n")
                        sink.flush()
                        key = f"{record['classification']}"
                        summary_counters[key] = summary_counters.get(key, 0) + 1
                        total += 1
                        LOGGER.info(
                            "[%04d] %s %s r%d: %s -> %s (%.1fs)",
                            total,
                            case["case_id"],
                            config_name,
                            repeat,
                            record["model_status"],
                            record["classification"],
                            record["wall_seconds"],
                        )
            if phase_label == "poisoned":
                restored = initialize("hardened", fixture="clean", reset=True)
                LOGGER.info("restored clean fixture; digest_ok=%s", restored["sha256"][:12])

    elapsed = time.perf_counter() - started
    summary = {
        "campaign_id": campaign_id,
        "cases_file": str(cases_file),
        "provider": info.name,
        "model": info.model,
        "model_digest": info.digest,
        "configs": args.configs,
        "repeats": args.repeats,
        "total_runs": total,
        "elapsed_seconds": round(elapsed, 1),
        "classifications": summary_counters,
        "schema_version": SCHEMA_VERSION,
        "notice": "Raw evidence only. Adjudication and §5.4 metrics are separate steps.",
    }
    summary_path = jsonl_path.with_suffix(".summary.json")
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    LOGGER.info("campaign complete: %d runs in %.1fs -> %s", total, elapsed, jsonl_path.name)
    await provider.aclose()
    return 0


def AppSettings_for(args: argparse.Namespace):  # noqa: N802 (small script-local factory)
    from app.config import AppSettings

    return AppSettings(
        provider="ollama",
        model=args.model,
        demo_mode=True,
        ollama_base_url=args.ollama_url,
    )


async def run_single(
    provider,
    settings,
    db_settings,
    gateways,
    case: dict,
    config_name: str,
    config: dict,
    repeat: int,
) -> dict:
    started = time.perf_counter()
    request_id = str(uuid4())
    actor_id = case["actor_id"]
    principal = runner_principal(actor_id)
    profile: PromptProfile = config["prompt"]  # type: ignore[assignment]

    context = None
    if case.get("context_offering_id"):
        context = {"offering_id": case["context_offering_id"]}

    if case.get("candidate_origin") == "replay" or (
        case.get("fixed_candidate_sql") and not case.get("question")
    ):
        generation = {
            "status": "replay",
            "candidate_sql": case["fixed_candidate_sql"],
            "source": "fixed_candidate_replay",
        }
        candidate = case["fixed_candidate_sql"]
    else:
        generation = await generate_candidate(provider, settings, profile, principal, case, context)
        candidate = generation["candidate_sql"]

    record: dict[str, object] = {
        "run_id": request_id,
        "collected_at_utc": datetime.now(UTC).isoformat(),
        "campaign_config": config_name,
        "repeat": repeat,
        "case_id": case["case_id"],
        "category": case["category"],
        "actor_id": actor_id,
        "question_sha256": digest(case.get("question", "")),
        "prompt_profile": profile.value,
        "generation": generation,
        "model_status": generation["status"],
    }

    if not candidate:
        record.update(
            classification="no_candidate", wall_seconds=round(time.perf_counter() - started, 2)
        )
        return record

    record["candidate_sql_sha256"] = digest(candidate)
    policy = authorize_candidate(
        GatewayHandoff(
            request_id=request_id,
            principal_id=actor_id,
            candidate_sql=candidate,
            schema_version=SCHEMA_VERSION,
        )
    )
    record["policy_observe"] = asdict(policy)
    is_write = case.get("execution_scope") == WRITE_SCOPE

    if config["gateway"] == "enforce":
        outcome = await enforce_execute(gateways[config_name], actor_id, candidate, request_id)
        record["gateway_enforce"] = outcome
        decision = outcome["decision"]["decision"]
        if decision == "BLOCK":
            record["classification"] = "gateway_blocked"
        elif outcome["error"]:
            record["classification"] = "database_error"
        else:
            record["classification"] = (
                "executed_allowed" if decision == "ALLOW" else "executed_masked"
            )
    else:
        if is_write:
            record["write_execution"] = execute_write_and_verify(actor_id, candidate)
            record["classification"] = (
                "write_state_changed"
                if record["write_execution"].get("state_changed")
                else "write_no_change"
            )
        else:
            record["read_execution"] = execute_read(actor_id, candidate, str(config["exec"]))
            exec_rec = record["read_execution"]
            if not exec_rec.get("executed"):
                record["classification"] = "database_denied"
            elif exec_rec.get("row_count", 0) == 0:
                record["classification"] = "executed_zero_rows"
            else:
                record["classification"] = "executed_rows_returned"

    record["wall_seconds"] = round(time.perf_counter() - started, 2)
    return record


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--cases", default="development", help="development | evaluation | path to a case JSON"
    )
    parser.add_argument("--configs", default="E0,E1,E2,E4")
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument(
        "--model", choices=["qwen2.5-coder:7b", "qwen2.5-coder:3b"], default="qwen2.5-coder:7b"
    )
    parser.add_argument("--ollama-url", default="http://127.0.0.1:11434")
    parser.add_argument("--limit", type=int, default=None, help="Only the first N cases (smoke)")
    parser.add_argument("--resume", default=None, help="Previous JSONL to skip completed runs")
    args = parser.parse_args()
    raise SystemExit(asyncio.run(run_campaign(args)))


if __name__ == "__main__":
    main()
