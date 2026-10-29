"""Command-line entry point for the wiki -> Hindsight sync.

Dry-run is the default. Ingestion requires an explicit --apply.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from .engine import Config, apply_run, plan_run
from .manifest import LockHeld, SyncError
from .scope import Scope

DEFAULT_WIKI_ROOT = Path("/home/elvis/wiki")
DEFAULT_ENDPOINT = "https://api.hindsight.vectorize.io"
DEFAULT_NAMESPACE = "noesis-wiki"
DEFAULT_STATE_DIR = Path.home() / ".local/share/noesis/wiki-hindsight-sync"
DEFAULT_SCOPE_FILE = Path(__file__).resolve().parent / "scope.json"


def _load_scope(path: Path) -> Scope:
    """Load the reviewed scope definition.

    The scope file is the unit of review: it lists the exact wiki-relative
    paths that may be ingested, each with a classification and a reason.
    """
    if not path.exists():
        raise SyncError(f"scope file not found: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SyncError(f"scope file {path} is not valid JSON: {exc}") from exc
    entries = [
        (e["path"], e["kind"], e["classification"], e.get("reason", ""))
        for e in data.get("rules", [])
    ]
    event_times = {
        e["path"]: e["event_time"]
        for e in data.get("rules", [])
        if e.get("event_time")
    }
    return Scope.from_rules(
        data.get("namespace", DEFAULT_NAMESPACE),
        entries,
        exclude_sensitive_trees=data.get("exclude_sensitive_trees", True),
        max_bytes=int(data.get("max_bytes", 400_000)),
        reviewed_on=data.get("reviewed_on", ""),
        event_times=event_times,
    )


def _api_key() -> str:
    """Resolve the Hindsight API key from the environment.

    The key is read from HINDSIGHT_API_KEY. It is never written to a log,
    a report, or an error message.
    """
    key = os.environ.get("HINDSIGHT_API_KEY", "").strip()
    if not key:
        raise SyncError(
            "HINDSIGHT_API_KEY is not set. Export it for this run; it is never "
            "written to disk by this tool."
        )
    return key


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="wiki-hindsight-sync",
        description=(
            "One-way sync from the llm-wiki into a Hindsight bank. Dry-run by "
            "default; --apply performs ingestion."
        ),
    )
    parser.add_argument(
        "--wiki-root", type=Path, default=DEFAULT_WIKI_ROOT, help="wiki root directory"
    )
    parser.add_argument("--bank", default="", help="target Hindsight bank id")
    parser.add_argument("--endpoint", default=DEFAULT_ENDPOINT, help="Hindsight API base URL")
    parser.add_argument("--namespace", default="", help="document identity namespace")
    parser.add_argument("--state-dir", type=Path, default=DEFAULT_STATE_DIR)
    parser.add_argument("--scope-file", type=Path, default=DEFAULT_SCOPE_FILE)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="perform ingestion; without this flag the run is a dry-run",
    )
    parser.add_argument(
        "--max-documents",
        type=int,
        default=0,
        help="ceiling on documents ingested in one apply run (0 = no ceiling)",
    )
    parser.add_argument(
        "--max-runtime-s",
        type=float,
        default=0.0,
        help="stop the run after this many seconds (0 = no limit)",
    )
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--max-attempts", type=int, default=3)
    parser.add_argument(
        "--async",
        dest="use_async",
        action="store_true",
        help="use asynchronous retain and wait for the operation to finish",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="emit the run report as JSON on stdout",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    scope = _load_scope(args.scope_file)
    namespace = args.namespace or scope.namespace

    if not args.bank:
        raise SyncError("--bank is required")

    config = Config(
        wiki_root=args.wiki_root,
        bank_id=args.bank,
        endpoint=args.endpoint,
        namespace=namespace,
        state_dir=args.state_dir,
        api_key=_api_key(),
        scope=scope,
        dry_run=not args.apply,
        timeout_s=args.timeout,
        max_attempts=args.max_attempts,
        use_async=args.use_async,
        max_documents=args.max_documents,
        max_runtime_s=args.max_runtime_s,
    )

    if args.apply:
        report = apply_run(config)
    else:
        report = plan_run(config)

    if args.json:
        print(json.dumps(report.to_dict(), indent=2, sort_keys=True))
    else:
        _print_human(report)

    # A run that had errors exits non-zero so a scheduler notices.
    return 1 if report.errors else 0


def _print_human(report) -> None:
    mode = "PLAN (dry-run)" if report.dry_run else "APPLY"
    print(f"== wiki -> hindsight {mode} ==")
    print(f"bank      : {report.bank_id}")
    print(f"endpoint  : {report.endpoint}")
    print(f"namespace : {report.namespace}")
    print(f"wiki root : {report.wiki_root}")
    print(f"started   : {report.started_at}")
    print()
    print("counts:")
    for key in sorted(report.counts):
        print(f"  {key:<10} {report.counts[key]}")
    if report.actions:
        print()
        print("actions:")
        for action in report.actions:
            print(
                f"  {action.action:<7} {action.rel}  ->  {action.document_id}"
                f"  [{action.classification}] {action.detail}"
            )
    if report.review_items:
        print()
        print("review items (not ingested, not deleted):")
        for item in report.review_items:
            print(f"  {item.rel}: {item.detail}")
    if report.excluded:
        print()
        print(f"excluded by scope rules: {len(report.excluded)}")
    if report.errors:
        print()
        print("errors:")
        for err in report.errors:
            print(f"  {err}")
    if report.usage:
        print()
        print("usage:")
        for key in sorted(report.usage):
            print(f"  {key:<20} {report.usage[key]}")


if __name__ == "__main__":  # pragma: no cover
    try:
        sys.exit(main())
    except LockHeld as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(2)
    except SyncError as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(2)
