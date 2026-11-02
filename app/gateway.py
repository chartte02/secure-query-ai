"""The only boundary that may authorize or execute candidate SQL.

Member A owns the protocol and the safe default. Member C replaces
``NotConnectedGateway`` with a real parser/policy/executor implementation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.models import GatewayHandoff, QueryError, QueryGatewayDecision, QueryResult


class GatewayUnavailable(Exception):
    """The gateway is not connected or cannot be reached.

    This must never be downgraded into local SQL execution.
    """


@dataclass(frozen=True)
class GatewayOutcome:
    decision: QueryGatewayDecision
    result: QueryResult | None
    error: QueryError | None = None
    db_role: str | None = None


class SqlGateway(Protocol):
    executor: str

    async def inspect_and_execute(self, handoff: GatewayHandoff) -> GatewayOutcome: ...


class NotConnectedGateway:
    """Default until member C provides the real gateway."""

    executor = "gateway"

    async def inspect_and_execute(self, handoff: GatewayHandoff) -> GatewayOutcome:
        raise GatewayUnavailable("sql gateway is not connected")
