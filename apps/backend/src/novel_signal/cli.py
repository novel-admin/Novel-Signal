"""Small operational commands used by Render Cron and local operators."""

from __future__ import annotations

import argparse
import json
import sys

from novel_signal.config import get_settings
from novel_signal.modules.collection.runner import run_due_collection_jobs


def main() -> int:
    parser = argparse.ArgumentParser(prog="novel-signal")
    subcommands = parser.add_subparsers(dest="command", required=True)
    collect_due = subcommands.add_parser("collect-due", help="Plan and process due collection jobs")
    collect_due.add_argument("--max-jobs", type=int, default=None)
    collect_due.add_argument("--worker-id", default=None)
    args = parser.parse_args()

    if args.command == "collect-due":
        settings = get_settings()
        result = run_due_collection_jobs(
            max_jobs=args.max_jobs or settings.collection_batch_size,
            worker_id=args.worker_id,
        )
        print(json.dumps(result.__dict__, default=list, sort_keys=True))
        return 1 if result.failed else 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
