"""Only fixed, loopback lab targets; no caller-supplied reset DSNs."""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
from dataclasses import dataclass
from pathlib import Path
from typing import Literal
from uuid import UUID, uuid4

import psycopg
from dotenv import dotenv_values
from psycopg.rows import dict_row

ROOT = Path(__file__).resolve().parents[1]
Profile = Literal["hardened", "baseline", "write_lab"]
TARGETS = {
    "hardened": (55432, "sq_lab_hardened"),
    "baseline": (55433, "sq_lab_baseline"),
    "write_lab": (55434, "sq_lab_write"),
}
POSTGRES_IMAGE = (
    "postgres:17@sha256:31ba9c94a03ada9988f2bb493a22a75eef3a185884533e5cdbcd498ea835b08f"
)


def ensure_local_config() -> bool:
    """Create secrets only when no local config exists; never print them."""
    path = ROOT / ".env"
    if path.exists():
        return False
    contents = (
        f"SQ_ADMIN_PASSWORD={secrets.token_urlsafe(32)}\n"
        f"SQ_ROLE_SECRET={secrets.token_urlsafe(32)}\n"
        f"SQ_INSTALLATION_ID={uuid4()}\n"
        f"SQ_POSTGRES_IMAGE={POSTGRES_IMAGE}\n"
    )
    with path.open("x", encoding="utf-8") as stream:
        stream.write(contents)
    return True


@dataclass(frozen=True)
class Settings:
    admin_password: str
    role_secret: str
    installation_id: str

    @classmethod
    def load(cls) -> Settings:
        values = {**dotenv_values(ROOT / ".env"), **os.environ}
        keys = ("SQ_ADMIN_PASSWORD", "SQ_ROLE_SECRET", "SQ_INSTALLATION_ID")
        if any(not values.get(key) for key in keys):
            raise RuntimeError("Missing local lab config. Run python scripts/init_db.py.")
        if any(str(values[key]).startswith("replace-") for key in keys):
            raise ValueError("Replace .env.example placeholders or let init_db.py generate .env.")
        UUID(str(values[keys[2]]))
        return cls(*(str(values[key]) for key in keys))

    def role_password(self, role: str) -> str:
        return hmac.new(self.role_secret.encode(), role.encode(), hashlib.sha256).hexdigest()

    def connect(
        self, profile: Profile = "hardened", role: str = "sq_admin", *, autocommit: bool = False
    ) -> psycopg.Connection:
        if profile not in TARGETS:
            raise ValueError(f"Unknown lab profile: {profile}")
        port, database = TARGETS[profile]
        return psycopg.connect(
            host="127.0.0.1",
            port=port,
            dbname=database,
            user=role,
            password=self.admin_password if role == "sq_admin" else self.role_password(role),
            connect_timeout=5,
            application_name="securequery-ai-lab",
            autocommit=autocommit,
            row_factory=dict_row,
        )
