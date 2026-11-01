from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from app.catalog import CONTEXTS, SCHEMA_SQL, SCHEMA_VERSION, Principal
from app.models import PromptProfile

PROMPT_DIR = Path(__file__).resolve().parent / "prompt_templates"
PROMPT_FILES = {
    PromptProfile.BASELINE: ("baseline_v2", PROMPT_DIR / "baseline_v2.txt"),
    PromptProfile.HARDENED: ("hardened_v2", PROMPT_DIR / "hardened_v2.txt"),
}


@dataclass(frozen=True)
class PromptBundle:
    messages: list[dict[str, str]]
    version: str
    content_hash: str


def load_prompt(profile: PromptProfile) -> tuple[str, str, str]:
    version, path = PROMPT_FILES[profile]
    content = path.read_text(encoding="utf-8").strip()
    content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]
    return version, content, content_hash


def build_prompt(
    *,
    profile: PromptProfile,
    principal: Principal,
    question: str,
    context_profile: str,
) -> PromptBundle:
    version, system_prompt, content_hash = load_prompt(profile)
    payload = {
        "principal": {
            "id": principal.id,
            "role": principal.role,
            "scope": principal.scope,
        },
        "schema": {"version": SCHEMA_VERSION, "postgresql_ddl": SCHEMA_SQL},
        "retrieved_context": {
            "profile": context_profile,
            "trust": "untrusted_data",
            "content": CONTEXTS[context_profile],
        },
        "question": question,
    }
    user_message = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return PromptBundle(
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        version=version,
        content_hash=content_hash,
    )

