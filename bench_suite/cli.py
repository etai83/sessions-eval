"""CLI entry points for the benchmarking suite."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from bench_suite.offline import run_offline_golden_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="bench-suite", description="Antigravity Benchmarking Suite")
    sub = parser.add_subparsers(dest="command", required=True)

    offline = sub.add_parser(
        "offline-golden",
        help="Run the offline golden path (fixture → evaluate → registry → dashboard; no API)",
    )
    offline.add_argument(
        "--repo-root",
        type=Path,
        default=None,
        help="Repository root (default: current working directory)",
    )
    offline.add_argument(
        "--fixture",
        type=Path,
        default=None,
        help="Path to fixture TaskEntry JSON (default: offline golden fixture)",
    )

    args = parser.parse_args(argv)

    if args.command == "offline-golden":
        result = run_offline_golden_path(repo_root=args.repo_root, fixture_path=args.fixture)
        print(json.dumps(result, indent=2))
        print(
            f"\nOffline golden path complete: task={result['task_id']} "
            f"completeness={result['evaluation_result']['completeness_percent']}% "
            f"leaderboard={result['leaderboard_path']}",
            file=sys.stderr,
        )
        return 0

    parser.error(f"Unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
