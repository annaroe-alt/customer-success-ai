"""
Customer Success AI Pipeline
Orchestrates all 7 stages end-to-end.
"""
import sys
import time
import importlib

import config
from pipeline.utils import get_logger

_stage = lambda name: importlib.import_module(f"pipeline.{name}")
_s1  = _stage("01_account_review")
_s2  = _stage("02_prioritization")
_s3  = _stage("03_inbound_triage")
_s4  = _stage("04_checkin_prep")
_s5  = _stage("05_quality_review")
_s6  = _stage("06_intervention_planner")
_s7  = _stage("07_router")

build_account_contexts = _s1.build_account_contexts
prioritize             = _s2.prioritize
triage_all             = _s3.triage_all
prep_all_checkins      = _s4.prep_all_checkins
review_all_outputs     = _s5.review_all_outputs
plan_interventions     = _s6.plan_interventions
route_all              = _s7.route_all

logger = get_logger("main")


def _banner(stage: int, name: str) -> None:
    logger.info("")
    logger.info(f"{'='*60}")
    logger.info(f"  STAGE {stage}: {name}")
    logger.info(f"{'='*60}")


def run_pipeline() -> None:
    if not config.ANTHROPIC_API_KEY:
        logger.error(
            "ANTHROPIC_API_KEY is not set. "
            "Copy .env.example to .env and add your API key, then retry."
        )
        sys.exit(1)

    config.OUTPUTS_DIR.mkdir(exist_ok=True)
    config.LOGS_DIR.mkdir(exist_ok=True)

    start = time.time()
    logger.info("Starting Customer Success AI pipeline.")

    # Stage 1 — Account Review
    _banner(1, "Account Review")
    contexts, standards = build_account_contexts()

    # Stage 2 — Prioritization
    _banner(2, "Prioritization")
    priority_results = prioritize(contexts)

    # Stage 3 — Inbound Triage
    _banner(3, "Inbound Triage")
    triage_results = triage_all(contexts)
    triage_dicts = [
        {
            "ticket_id": r.ticket_id,
            "account_id": r.account_id,
            "issue_type": r.issue_type,
            "churn_risk": r.churn_risk,
            "churn_risk_reason": r.churn_risk_reason,
            "recommended_action": r.recommended_action,
            "gap_flag": r.gap_flag,
            "gap_note": r.gap_note,
        }
        for r in triage_results
    ]

    # Stage 4 — Check-in Prep
    _banner(4, "Check-in Prep")
    checkin_briefs = prep_all_checkins(contexts, priority_results)

    # Stage 5 — Quality Review
    _banner(5, "Quality Review")
    quality_results = review_all_outputs(contexts, standards)

    # Stage 6 — Intervention Planning
    _banner(6, "Intervention Planning")
    intervention_plans = plan_interventions(
        contexts, priority_results, quality_results, triage_dicts
    )

    # Stage 7 — Routing
    _banner(7, "Routing")
    routing_decisions = route_all(contexts, priority_results)

    elapsed = time.time() - start
    logger.info("")
    logger.info(f"{'='*60}")
    logger.info(f"  PIPELINE COMPLETE in {elapsed:.1f}s")
    logger.info(f"{'='*60}")
    logger.info(f"  Accounts processed:    {len(contexts)}")
    logger.info(f"  Tickets triaged:       {len(triage_results)}")
    logger.info(f"  Check-in briefs:       {len(checkin_briefs)}")
    logger.info(f"  Outputs reviewed:      {len(quality_results)}")
    logger.info(f"  Intervention plans:    {len(intervention_plans)}")
    logger.info(f"  Routing decisions:     {len(routing_decisions)}")
    logger.info(f"  Outputs saved to:      {config.OUTPUTS_DIR}/")
    logger.info(f"  Log file:              {config.LOGS_DIR}/pipeline.log")
    logger.info("")

    # Print routing summary to stdout for quick visibility
    print("\n--- ROUTING SUMMARY ---")
    for d in sorted(routing_decisions, key=lambda x: x.track):
        print(f"  [{d.track:10s}] {d.account_id} — {d.account_name} | {d.next_step[:80]}")


if __name__ == "__main__":
    run_pipeline()
