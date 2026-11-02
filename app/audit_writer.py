"""Append-only database audit writer for formal gateway outcomes."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, Protocol
from uuid import UUID, uuid4


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
    ) -> str: ...


class DatabaseAuditWriter:
    """Write only digests and decisions through the restricted audit role."""

    def __init__(self, connection_factory: Callable[[], Any] | None = None) -> None:
        self._connection_factory = connection_factory or self._default_connection_factory

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
        return await asyncio.to_thread(
            self._append_sync,
            request_id=request_id,
            actor_id=actor_id,
            db_role=db_role,
            event_type=event_type,
            decision=decision,
            reason_code=reason_code,
            sql_digest=sql_digest,
        )

    def _append_sync(
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
        event_id = uuid4()
        run_id = UUID(request_id)
        with self._connection_factory() as connection:
            connection.execute(
                """
                INSERT INTO audit.events
                    (event_id, run_id, actor_id, db_role, event_type,
                     decision, reason_code, sql_digest, occurred_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    event_id,
                    run_id,
                    actor_id,
                    db_role,
                    event_type,
                    decision,
                    reason_code,
                    sql_digest,
                    datetime.now(UTC),
                ),
            )
        return str(event_id)

    @staticmethod
    def _default_connection_factory() -> Any:
        from db.settings import Settings

        return Settings.load().connect("hardened", "sq_audit_writer")
