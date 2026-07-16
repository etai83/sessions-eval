"""CLI entry points for the benchmarking suite."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from bench_suite.live import run_live_task
from bench_suite.offline import run_offline_golden_path
from bench_suite.runner import AlreadyEvaluatedError
from bench_suite.pipeline import transcript_to_candidate


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="bench-suite", description="Antigravity Benchmarking Suite")
    sub = parser.add_subparsers(dest="command", required=True)

    offline = sub.add_parser(
        "offline-golden",
        help="Run the offline golden path (fixture → evaluate → registry → dashboard; no API)",
    )
    offline.add_argument("--repo-root", type=Path, default=None)
    offline.add_argument("--fixture", type=Path, default=None)

    live = sub.add_parser(
        "live-run",
        help="Live Gemini run of a task (default: offline golden fixture); uses GEMINI_API_KEY",
    )
    live.add_argument("--repo-root", type=Path, default=None)
    live.add_argument("--task", type=Path, default=None, help="TaskEntry JSON path")
    live.add_argument("--model", default="gemini-2.5-flash")
    live.add_argument(
        "--model-config",
        default='{"thinking_level":"high"}',
        help="JSON object for model_config",
    )
    live.add_argument(
        "--force",
        action="store_true",
        help="Re-run even if registry already has this pair (still appends a new result)",
    )

    classify = sub.add_parser(
        "classify-transcript",
        help="Ingest transcript_full.jsonl and classify into a TaskCandidate (no API)",
    )
    classify.add_argument("transcript", type=Path, help="Path to transcript_full.jsonl")
    classify.add_argument("--repo-root", type=Path, default=None)
    classify.add_argument(
        "--rules",
        type=Path,
        default=None,
        help="Path to classifier_rules.json (default: .scratch/bench-suite/classifier_rules.json)",
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

    if args.command == "live-run":
        model_config = json.loads(args.model_config)
        try:
            result = run_live_task(
                repo_root=args.repo_root,
                task_path=args.task,
                model_name=args.model,
                model_config=model_config,
                force=args.force,
            )
        except AlreadyEvaluatedError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        print(json.dumps({k: v for k, v in result.items() if k != "model_response"}, indent=2))
        print(
            f"\nLive run complete: task={result['task_id']} "
            f"completeness={result['evaluation_result']['completeness_percent']}% "
            f"cost=${result['evaluation_result']['cost_usd']} "
            f"leaderboard={result['leaderboard_path']}",
            file=sys.stderr,
        )
        return 0

    if args.command == "classify-transcript":
        root = args.repo_root or Path.cwd()
        candidate = transcript_to_candidate(
            args.transcript,
            rules_path=args.rules,
            repo_root=root,
        )
        print(json.dumps(candidate, indent=2, ensure_ascii=False))
        print(
            f"\nClassified: conv={candidate['conversation_id']} "
            f"taxonomy={candidate['taxonomy']} domain={candidate['domain']} "
            f"tools={len(candidate['tool_invocations'])}",
            file=sys.stderr,
        )
        return 0

    parser.error(f"Unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
