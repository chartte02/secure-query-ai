"""Emit the effective local settings for the PowerShell service manager."""

from __future__ import annotations

import hashlib
import json

from app.config import AppSettings


def main() -> None:
    settings = AppSettings()
    fingerprint = hashlib.sha256(
        json.dumps(settings.model_dump(mode="json"), sort_keys=True).encode("utf-8")
    ).hexdigest()
    print(
        json.dumps(
            {
                "provider": settings.provider,
                "model": settings.model,
                "ollama_url": settings.ollama_base_url,
                "demo": settings.demo_mode,
                "config_hash": fingerprint,
            }
        )
    )


if __name__ == "__main__":
    main()
