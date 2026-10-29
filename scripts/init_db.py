"""Bootstrap local Docker fixtures; hardened is the default."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from db.manage import initialize, write_seed_manifest  # noqa: E402
from db.settings import ROOT, TARGETS, Settings, ensure_local_config  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", choices=TARGETS, default="hardened")
    parser.add_argument(
        "--all", action="store_true", help="Also start isolated baseline/write labs"
    )
    parser.add_argument(
        "--no-start", action="store_true", help="Use already running lab containers"
    )
    args = parser.parse_args()
    if ensure_local_config():
        print("Generated .env with random local credentials (ignored by Git).")
    settings = Settings.load()
    profiles = list(TARGETS) if args.all else [args.profile]
    if not args.no_start:
        subprocess.run(
            [
                "docker",
                "compose",
                "--profile",
                "lab",
                "up",
                "-d",
                "--wait",
                "--wait-timeout",
                "90",
                *profiles,
            ],
            cwd=ROOT,
            check=True,
        )
    for profile in profiles:
        deadline = time.monotonic() + 45
        while True:
            try:
                with settings.connect(profile):
                    break
            except Exception:
                if time.monotonic() >= deadline:
                    raise RuntimeError(f"Local {profile} database did not become ready.") from None
                time.sleep(1)
        report = initialize(profile)
        if profile == "hardened" and report.get("fixture", "clean") == "clean":
            write_seed_manifest(report)
        print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
