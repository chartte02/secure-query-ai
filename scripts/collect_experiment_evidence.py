"""Collect fixed-SQL database-control evidence. Never invoke or impersonate an LLM."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import psycopg

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from db.client import query_connection  # noqa: E402
from db.manage import assert_target, snapshot  # noqa: E402
from db.settings import POSTGRES_IMAGE, ROOT, Settings  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", type=Path, default=ROOT / "artifacts" / "database-evidence.json"
    )
    args = parser.parse_args()
    settings = Settings.load()
    candidates = {
        "own_grades": "SELECT student_id, offering_id, score FROM academic.grades "
        "WHERE student_id='S01' ORDER BY offering_id",
        "other_grades": "SELECT student_id, offering_id, score FROM academic.grades "
        "WHERE student_id='S02' ORDER BY offering_id",
        "other_sensitive": "SELECT national_id FROM academic.students WHERE student_id='S02'",
    }
    evidence = {
        "recorded_at_utc": datetime.now(UTC).isoformat(),
        "candidate_origin": "fixed_sql_replay",
        "model_invoked": False,
        "gateway_status": "not_implemented",
        "postgres_image": POSTGRES_IMAGE,
        "profiles": {},
        "results": [],
    }
    for profile in ("hardened", "baseline"):
        with settings.connect(profile) as conn:
            assert_target(conn, profile, settings)
            version = conn.execute("SELECT version() AS v").fetchone()["v"]
            evidence["profiles"][profile] = {"postgres_version": version, **snapshot(conn)}
        for case_id, candidate in candidates.items():
            result = {
                "case_id": case_id,
                "profile": profile,
                "actor_id": "student_s01",
                "candidate_sql": candidate,
                "rows": None,
                "sqlstate": None,
            }
            with query_connection("student_s01", profile=profile, unsafe_lab=True) as conn:
                result["actual_db_role"] = conn.execute("SELECT session_user AS role").fetchone()[
                    "role"
                ]
                try:
                    result["rows"] = conn.execute(candidate).fetchall()
                except psycopg.Error as exc:
                    result["sqlstate"] = exc.sqlstate
                    conn.rollback()
            evidence["results"].append(result)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8"
    )
    print(f"Saved synthetic fixed-SQL evidence: {args.output}")


if __name__ == "__main__":
    main()
