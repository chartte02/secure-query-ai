"""Capture Ollama placement evidence without executing generated SQL."""

from __future__ import annotations

import argparse
import json
import subprocess
import time
from datetime import UTC, datetime


def command(args: list[str]) -> str:
    completed = subprocess.run(args, capture_output=True, text=True, check=False)
    return completed.stdout.strip()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default="qwen2.5-coder:7b")
    parser.add_argument(
        "--smoke",
        action="store_true",
        help="Run one non-SQL local model smoke request.",
    )
    parser.add_argument("--output", help="Write JSON evidence to this path.")
    args = parser.parse_args()

    evidence: dict[str, object] = {
        "captured_at_utc": datetime.now(UTC).isoformat(),
        "model": args.model,
        "gpu": command(
            [
                "nvidia-smi",
                "--query-gpu=name,driver_version,memory.total,memory.used",
                "--format=csv,noheader",
            ]
        ),
        "ollama_version": command(["ollama", "--version"]),
        "ollama_models": command(["ollama", "list"]),
        "samples": [],
    }
    if args.smoke:
        process = subprocess.Popen(
            ["ollama", "run", args.model, "Return only the word READY."],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        samples: list[dict[str, str]] = []
        while process.poll() is None:
            samples.append(
                {
                    "ollama_ps": command(["ollama", "ps"]),
                    "nvidia_compute_apps": command(
                        [
                            "nvidia-smi",
                            "--query-compute-apps=pid,process_name,used_memory",
                            "--format=csv,noheader",
                        ]
                    ),
                }
            )
            time.sleep(1)
        output = process.communicate(timeout=5)[0].strip()
        evidence["smoke_output"] = output[-500:]
        evidence["samples"] = samples
    processors = " ".join(sample["ollama_ps"] for sample in evidence["samples"])  # type: ignore[index]
    evidence["gpu_verified"] = "GPU" in processors and "100% CPU" not in processors
    evidence["cpu_fallback"] = not evidence["gpu_verified"]
    rendered = json.dumps(evidence, ensure_ascii=False, indent=2)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as stream:
            stream.write(rendered + "\n")
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
