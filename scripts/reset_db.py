"""Reset one marked, loopback-only lab target; never accept arbitrary database URLs."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from db.manage import initialize  # noqa: E402
from db.seed import FIXTURES  # noqa: E402
from db.settings import TARGETS  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", choices=TARGETS, default="hardened")
    parser.add_argument("--fixture", choices=FIXTURES, default="clean")
    args = parser.parse_args()
    print(
        json.dumps(
            initialize(args.profile, fixture=args.fixture, reset=True), ensure_ascii=False, indent=2
        )
    )


if __name__ == "__main__":
    main()
