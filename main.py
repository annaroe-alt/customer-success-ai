"""
Customer Success AI Pipeline
Orchestrates all 8 stages end-to-end.
"""
import sys
import time
import importlib

import config
from pipeline.utils import get_logger, TOKEN_USAGE

_stage = lambda name: importlib.import_module(f"pipeline.{name}")
_s0  = _stage("00_validate_inputs")
_s1  = _stage("01_account_review")
_s2  = _stage("02_prioritization")
_s3  = _stage("03_inbound_triage")
_s4  = _stage("04_checkin_prep")
_s5  = _stage("05_quality_review")
_s7  = _stage("07_router")
_s8  = _stage("08_approval_gate")
_s6  = _stage("06_intervention_planner")
_s11 = _stage("11_followup_tracker")

validate_inputs        = _s0.validate_inputs
build_account_contexts = _s1.build_account_contexts
prioritize             = _s2.prioritize
triage_all             = _s3.triage_all
prep_all_checkins      = _s4.prep_all_checkins
review_all_outputs     = _s5.review_all_outputs
route_all              = _s7.route_all
run_approval_gate      = _s8.run_approval_gate
plan_interventions     = _s6.plan_interventions
run_followup_tracker   = _s11.run_followup_tracker

logger = get_logger("main")


def _banner(stage: int | str, name: str) -> None:
    logger.info("")
    logger.info(f"{'='*60}")
    logger.info(f"  STAGE {stage}: {name}")
    logger.info(f"{'='*60}")


def run_pipeline(auto_approve: bool = False) -> None:
    """
    Run the full pipeline.

    Args:
        auto_approve: If True, all pending escalations are approved automatically
                      without prompting (useful for CI / non-interactive runs).
    """
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

    # Stage 0 — Input Validation (abort if any CSV is missing or malformed)
    _banner(0, "Input Validation")
    if not validate_inputs():
        logger.error("Input validation failed. Fix the errors above before running the pipeline.")
        sys.exit(1)

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

    # Stage 11 — Follow-up Tracker (runs before prep so open items feed into briefs)
    _banner(11, "Follow-up Tracker")
    open_items_by_account = run_followup_tracker()

    # Stage 4 — Check-in Prep (receives open items for continuity)
    _banner(4, "Check-in Prep")
    checkin_briefs = prep_all_checkins(contexts, priority_results, open_items_by_account)

    # Stage 5 — Quality Review
    _banner(5, "Quality Review")
    quality_results = review_all_outputs(contexts, standards)

    # Stage 7 — Routing (before intervention planning so approval can gate plans)
    _banner(7, "Routing")
    routing_decisions = route_all(contexts, priority_results)

    # Stage 8 — Escalation Approval Gate
    # Pauses for CSM review of any pending escalations before intervention plans
    # are generated for those accounts. Denied escalations are excluded from
    # intervention planning; still-pending ones are treated as denied for this run.
    _banner(8, "Escalation Approval Gate")
    routing_decisions = run_approval_gate(routing_decisions, auto_approve=auto_approve)

    approved_escalation_ids = {
        d.account_id for d in routing_decisions
        if d.track == config.TRACK_ESCALATE and d.status == "approved"
    }

    # Stage 6 — Intervention Planning
    # Runs after approval so plans are only generated for escalations that a CSM
    # has signed off on, plus any Critical/High accounts that aren't being escalated.
    _banner(6, "Intervention Planning")
    intervention_plans = plan_interventions(
        contexts, priority_results, quality_results, triage_dicts,
        approved_escalation_ids=approved_escalation_ids,
    )

    elapsed = time.time() - start
    logger.info("")
    logger.info(f"{'='*60}")
    logger.info(f"  PIPELINE COMPLETE in {elapsed:.1f}s")
    logger.info(f"{'='*60}")
    logger.info(f"  Accounts processed:    {len(contexts)}")
    logger.info(f"  Tickets triaged:       {len(triage_results)}")
    logger.info(f"    - churn-risk flags:  {sum(1 for r in triage_results if r.churn_risk)}")
    logger.info(f"    - gap accounts:      {sum(1 for r in triage_results if r.gap_flag)}")
    logger.info(f"  Check-in briefs:       {len(checkin_briefs)}")
    logger.info(f"  Outputs reviewed:      {len(quality_results)}")
    logger.info(f"    - passed:            {sum(1 for r in quality_results if r.overall_passed)}")
    logger.info(f"    - failed:            {sum(1 for r in quality_results if not r.overall_passed)}")
    logger.info(f"  Routing decisions:     {len(routing_decisions)}")
    for track in [config.TRACK_ESCALATE, config.TRACK_FOLLOW_UP, config.TRACK_RESOLVE]:
        n = sum(1 for d in routing_decisions if d.track == track)
        logger.info(f"    - {track:12s}:  {n}")
    escalations = [d for d in routing_decisions if d.track == config.TRACK_ESCALATE]
    if escalations:
        approved_n  = sum(1 for d in escalations if d.status == "approved")
        denied_n    = sum(1 for d in escalations if d.status == "denied")
        pending_n   = sum(1 for d in escalations if d.status == "pending_review")
        logger.info(f"      approved:         {approved_n}")
        logger.info(f"      denied:           {denied_n}")
        logger.info(f"      still pending:    {pending_n}")
    logger.info(f"  Intervention plans:    {len(intervention_plans)}")
    logger.info(f"  Outputs saved to:      {config.OUTPUTS_DIR}/")
    logger.info(f"  Log file:              {config.LOGS_DIR}/pipeline.log")
    logger.info("")
    logger.info("--- TOKEN USAGE & COST ---")
    logger.info(f"  Claude API calls:      {TOKEN_USAGE.calls}")
    logger.info(f"  Input tokens:          {TOKEN_USAGE.input_tokens:,}")
    logger.info(f"  Output tokens:         {TOKEN_USAGE.output_tokens:,}")
    logger.info(f"  Total tokens:          {TOKEN_USAGE.total_tokens:,}")
    logger.info(f"  Estimated cost:        ${TOKEN_USAGE.cost_usd:.4f}")
    haiku_stages_note = "Stages 2/3/7 use claude-haiku-4-5; stages 4/5/6 use claude-sonnet-4-6"
    logger.info(f"  Model note:            {haiku_stages_note}")
    logger.info("")

    print("\n--- ROUTING SUMMARY ---")
    for d in sorted(routing_decisions, key=lambda x: (x.track, x.account_id)):
        status_tag = f" [{d.status}]" if d.track == config.TRACK_ESCALATE else ""
        print(f"  [{d.track:10s}{status_tag}] {d.account_id} — {d.account_name} | {d.next_step[:70]}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Customer Success AI Pipeline")
    parser.add_argument(
        "--auto-approve",
        action="store_true",
        help="Approve all escalations automatically (non-interactive / CI mode)",
    )
    args = parser.parse_args()
    run_pipeline(auto_approve=args.auto_approve)
