"""Run deterministic permission tests without contacting any model provider."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", choices=("hardened",), default="hardened")
    parser.parse_args()
    raise SystemExit(
        subprocess.call(
            [sys.executable, "-m", "pytest", "tests/db", "-q"],
            cwd=Path(__file__).resolve().parents[1],
        )
    )


if __name__ == "__main__":
    main()
