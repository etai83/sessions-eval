"""CLI entry points for the benchmarking suite."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from bench_suite.live import run_live_task
from bench_suite.offline import run_offline_golden_path
from bench_suite.runner import AlreadyEvaluatedError
from bench_suite.pipeline import (
    batch_eval,
    promote_task,
    refresh_corpus,
    sample_and_write_pending,
    transcript_to_candidate,
)


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
    live.add_argument(
        "--task-id",
        default=None,
        help="Load TaskEntry from dataset/tasks by id (e.g. trading_btc_backtest_01)",
    )
    live.add_argument(
        "--model",
        default=None,
        help="Gemini model id (default: config default_model, currently gemini-3.5-flash)",
    )
    live.add_argument(
        "--model-config",
        default=None,
        help='JSON object for model_config (default: config default_model_config)',
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

    sample = sub.add_parser(
        "sample",
        help="Stratified-sample a pool of transcripts into pending-review (no API)",
    )
    sample.add_argument(
        "transcripts",
        nargs="+",
        type=Path,
        help="Paths to transcript_full.jsonl files",
    )
    sample.add_argument("--repo-root", type=Path, default=None)
    sample.add_argument(
        "--rules",
        type=Path,
        default=None,
        help="Path to classifier_rules.json",
    )
    sample.add_argument(
        "--target",
        type=int,
        default=20,
        help="Target total tasks (default: 20)",
    )

    promote = sub.add_parser(
        "promote",
        help="Promote a human-reviewed pending-review JSON into dataset/tasks/",
    )
    promote.add_argument(
        "pending_file",
        type=Path,
        help="Path to candidate_<conv-id>.json in pending-review/",
    )
    promote.add_argument("--repo-root", type=Path, default=None)

    batch = sub.add_parser(
        "batch-eval",
        help="Live-eval every dataset task for one model×config; skip registry hits",
    )
    batch.add_argument("--repo-root", type=Path, default=None)
    batch.add_argument(
        "--model",
        default=None,
        help="Gemini model id (default: config default_model)",
    )
    batch.add_argument(
        "--model-config",
        default=None,
        help="JSON object for model_config (default: config default_model_config)",
    )
    batch.add_argument(
        "--force",
        action="store_true",
        help="Re-run pairs already in the registry (still appends new results)",
    )

    refresh = sub.add_parser(
        "refresh",
        help="Discover transcripts → classify → stratified sample into pending-review (additive)",
    )
    refresh.add_argument("--repo-root", type=Path, default=None)
    refresh.add_argument(
        "--transcripts-root",
        type=Path,
        default=None,
        help="Directory to scan recursively for transcript_full.jsonl",
    )
    refresh.add_argument(
        "transcripts",
        nargs="*",
        type=Path,
        help="Optional explicit transcript_full.jsonl paths",
    )
    refresh.add_argument(
        "--rules",
        type=Path,
        default=None,
        help="Path to classifier_rules.json",
    )
    refresh.add_argument(
        "--target",
        type=int,
        default=20,
        help="Dataset capacity target (default: 20); only remaining slots are filled",
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
        model_config = json.loads(args.model_config) if args.model_config else None
        try:
            result = run_live_task(
                repo_root=args.repo_root,
                task_path=args.task,
                task_id=args.task_id,
                model_name=args.model,
                model_config=model_config,
                force=args.force,
            )
        except AlreadyEvaluatedError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        except (ValueError, FileNotFoundError, RuntimeError) as exc:
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

    if args.command == "sample":
        root = args.repo_root or Path.cwd()
        from bench_suite.config import load_config
        config = load_config(repo_root=root)
        paths = config["_resolved_paths"]
        from bench_suite.store import DatasetStore
        store = DatasetStore(
            Path(paths["dataset_tasks"]),
            Path(paths["schema"]),
        )
        existing_ids = {t["source"]["conversation_id"] for t in store.list_tasks()}
        result = sample_and_write_pending(
            args.transcripts,
            rules_path=args.rules,
            pending_dir=paths["pending_review"],
            existing_ids=existing_ids,
            target_total=args.target,
            repo_root=root,
        )
        print(json.dumps(result, indent=2))
        print(
            f"\nSampled: ingested={result['candidates_ingested']} "
            f"selected={result['candidates_selected']} "
            f"written={len(result['paths_written'])} "
            f"pending-review={paths['pending_review']}",
            file=sys.stderr,
        )
        return 0

    if args.command == "promote":
        try:
            result = promote_task(args.pending_file, repo_root=args.repo_root)
        except FileExistsError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        print(json.dumps(result, indent=2))
        print(f"\nPromoted: task_id={result['task_id']} → {result['dataset_path']}", file=sys.stderr)
        return 0

    if args.command == "batch-eval":
        model_config = json.loads(args.model_config) if args.model_config else None
        try:
            result = batch_eval(
                repo_root=args.repo_root,
                model_name=args.model,
                model_config=model_config,
                force=args.force,
            )
        except RuntimeError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        print(json.dumps(result, indent=2))
        print(
            f"\nBatch eval complete: ran={result['ran']} skipped={result['skipped']} "
            f"failed={result['failed']} total={result['tasks_total']} "
            f"leaderboard={result['leaderboard_path']}",
            file=sys.stderr,
        )
        return 1 if result["failed"] else 0

    if args.command == "refresh":
        if not args.transcripts and not args.transcripts_root:
            print(
                "refresh requires --transcripts-root and/or explicit transcript paths",
                file=sys.stderr,
            )
            return 2
        try:
            result = refresh_corpus(
                repo_root=args.repo_root,
                transcripts_root=args.transcripts_root,
                transcript_paths=args.transcripts or None,
                rules_path=args.rules,
                target_total=args.target,
            )
        except FileNotFoundError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        print(json.dumps(result, indent=2))
        print(
            f"\nRefresh complete: discovered={result['transcripts_discovered']} "
            f"selected={result['candidates_selected']} "
            f"target_new={result['target_new']} "
            f"pending-review={result['pending_review']}",
            file=sys.stderr,
        )
        return 0

    parser.error(f"Unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
