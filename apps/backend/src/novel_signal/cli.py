"""Small operational commands used by Render Cron and local operators."""

# ruff: noqa: E501, E702

from __future__ import annotations

import argparse
import json
import sys

from novel_signal.config import get_settings
from novel_signal.db import SessionLocal
from novel_signal.modules.actions.models import Action, ChangeEvent, Gap
from novel_signal.modules.alerts.models import AlertEvent, AlertRule
from novel_signal.modules.auth.models import User
from novel_signal.modules.auth.service import password_hash
from novel_signal.modules.collection.runner import run_due_collection_jobs
from novel_signal.modules.scorecards.models import ScorecardCell


def main() -> int:
    parser = argparse.ArgumentParser(prog="novel-signal")
    subcommands = parser.add_subparsers(dest="command", required=True)
    collect_due = subcommands.add_parser("collect-due", help="Plan and process due collection jobs")
    collect_due.add_argument("--max-jobs", type=int, default=None)
    collect_due.add_argument("--worker-id", default=None)
    subcommands.add_parser("seed-demo", help="Seed the demo account and clearly marked sample data")
    args = parser.parse_args()

    if args.command == "collect-due":
        settings = get_settings()
        result = run_due_collection_jobs(
            max_jobs=args.max_jobs or settings.collection_batch_size,
            worker_id=args.worker_id,
        )
        print(json.dumps(result.__dict__, default=list, sort_keys=True))
        return 1 if result.failed else 0
    if args.command == "seed-demo":
        with SessionLocal() as session:
            user = session.query(User).filter_by(email="demo@demo.com").one_or_none()
            if user is None:
                session.add(User(email="demo@demo.com", password_hash=password_hash("demo123")))
            if session.query(ScorecardCell).count() == 0:
                session.add_all([
                    ScorecardCell(level="product", entity_id="demo-novel", dimension="visibility", score=82, band="strong", direction="up", velocity=4.2, confidence="measured", evidence={"demo": True}),
                    ScorecardCell(level="product", entity_id="demo-novel", dimension="content", score=68, band="watch", direction="flat", velocity=0.0, confidence="derived", evidence={"demo": True}),
                    ScorecardCell(level="competitor", entity_id="demo-competitor", dimension="visibility", score=74, band="watch", direction="down", velocity=-2.1, confidence="measured", evidence={"demo": True}),
                ])
            gap = session.query(Gap).filter_by(fingerprint="demo-gap-ranking").one_or_none()
            if gap is None:
                gap = Gap(fingerprint="demo-gap-ranking", dimension="rank_visibility", entity_id="demo-novel", benchmark_value={"rank": 3}, current_value={"rank": 8}, gap_size=5, revenue_at_stake=12500, root_cause="competitor momentum", confidence="derived", evidence={"demo": True})
                session.add(gap); session.flush()
            change = session.query(ChangeEvent).filter_by(fingerprint="demo-change-cpc").one_or_none()
            if change is None:
                change = ChangeEvent(target_type="keyword", target_id="demo-keyword", event_type="cpc_increase", fingerprint="demo-change-cpc", severity="warning", old_value={"cpc": 1.2}, new_value={"cpc": 1.7})
                session.add(change); session.flush()
            if session.query(Action).filter_by(title="Refresh high-value listing content").one_or_none() is None:
                session.add(Action(change_event_id=change.id, gap_id=gap.id, title="Refresh high-value listing content", reason="Demo recommendation backed by the ranking gap.", owner_user_id="demo@demo.com", status="open", playbook_entry="listing-refresh"))
            rule = session.query(AlertRule).filter_by(rule_key="demo-rank-drop").one_or_none()
            if rule is None:
                rule = AlertRule(rule_key="demo-rank-drop", alert_type="rank_drop", version="v1", severity="warning", threshold={"positions": 3})
                session.add(rule); session.flush()
            if session.query(AlertEvent).filter_by(fingerprint="demo-alert-rank-drop").one_or_none() is None:
                session.add(AlertEvent(rule_id=rule.id, alert_type="rank_drop", severity="warning", target_type="keyword", target_id="demo-keyword", title="Novel slipped 5 positions", detail="Demo alert showing the review workflow.", evidence={"demo": True, "previous_rank": 3, "current_rank": 8}, fingerprint="demo-alert-rank-drop"))
            session.commit()
        print(json.dumps({"seeded": True, "email": "demo@demo.com"}))
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
