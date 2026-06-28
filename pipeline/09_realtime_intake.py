"""
Stage 9 — Real-time Intake
Processes a single inbound issue immediately without running the full pipeline.
Runs triage (Stage 3 logic) and routing (Stage 7 logic) on one ticket, then
writes the result to outputs/realtime_results.json and — for escalations or
churn-risk tickets — appends to outputs/urgent_escalations.csv.

Designed to be called by watch.py as events arrive, giving 24/7 responsiveness
to new account issues without waiting for the next daily batch run.
"""
import csv
import importlib
import json
from datetime import date, datetime, timezone

import config
from models.schemas import AccountContext, PriorityResult, SupportTicket, TriageResult
from pipeline.utils import get_logger, StageStats

logger = get_logger("09_realtime_intake")

_s3 = importlib.import_module("pipeline.03_inbound_triage")
_s7 = importlib.import_module("pipeline.07_router")

REALTIME_RESULTS_FILE = config.OUTPUTS_DIR / "realtime_results.json"
URGENT_ESCALATIONS_FILE = config.OUTPUTS_DIR / "urgent_escalations.csv"
URGENT_FIELDS = [
    "received_at", "ticket_id", "account_id", "account_name",
    "issue_summary", "severity", "triage_issue_type",
    "churn_risk", "routing_track", "next_step", "owner",
]


def _load_realtime_log() -> list[dict]:
    if REALTIME_RESULTS_FILE.exists():
        with open(REALTIME_RESULTS_FILE) as f:
            return json.load(f)
    return []


def _append_realtime_result(entry: dict) -> None:
    log = _load_realtime_log()
    log.append(entry)
    config.OUTPUTS_DIR.mkdir(exist_ok=True)
    with open(REALTIME_RESULTS_FILE, "w") as f:
        json.dump(log, f, indent=2)


def _append_urgent(entry: dict) -> None:
    exists = URGENT_ESCALATIONS_FILE.exists()
    with open(URGENT_ESCALATIONS_FILE, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=URGENT_FIELDS)
        if not exists:
            w.writeheader()
        w.writerow({k: entry.get(k, "") for k in URGENT_FIELDS})


def _days_to_renewal(renewal_date: str) -> int:
    try:
        return (datetime.strptime(renewal_date, "%Y-%m-%d").date() - date.today()).days
    except ValueError:
        return 999


def process_inbound_issue(
    ticket: SupportTicket,
    ctx: AccountContext,
    priority_tier: str = config.TIER_MONITOR,
) -> dict:
    """
    Triage and route a single inbound issue immediately.

    Args:
        ticket:        The incoming SupportTicket.
        ctx:           Full AccountContext for the account.
        priority_tier: Current priority tier from the latest daily scoring run.

    Returns a result dict and persists it to outputs/.
    """
    stats = StageStats("09_realtime_intake")
    received_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    logger.info(
        f"[REALTIME] Inbound: {ticket.ticket_id} — {ticket.issue_summary[:60]} "
        f"({ticket.severity}/{ticket.customer_sentiment}) for {ctx.account_name}"
    )

    # --- Triage ---
    triage: TriageResult = _s3.triage_ticket(ticket, ctx)
    logger.info(
        f"[REALTIME] Triage: issue_type={triage.issue_type}, churn_risk={triage.churn_risk}"
    )

    # --- Build a PriorityResult using the last known tier so the router has signal ---
    priority = PriorityResult(
        account_id=ctx.account_id,
        account_name=ctx.account_name,
        tier=priority_tier,
        urgency_score=0,
        rationale="Real-time intake — score not recomputed",
        days_to_renewal=_days_to_renewal(ctx.account.renewal_date),
        health_drop=ctx.account.previous_health_score - ctx.account.current_health_score,
    )

    # --- Routing ---
    rule_result = _s7.rule_based_route(ctx, priority)
    if rule_result:
        track, reason = rule_result
        next_step = _s7._default_next_step(track, ctx)
    else:
        try:
            track, reason, next_step = _s7.claude_route(ctx, priority)
        except Exception as e:
            logger.error(f"[REALTIME] Routing failed: {e}. Defaulting to Follow-up.")
            track = config.TRACK_FOLLOW_UP
            reason = f"Routing error: {e}"
            next_step = "Manual review required."

    status = "pending_review" if track == config.TRACK_ESCALATE else "approved"
    logger.info(f"[REALTIME] Routed to: {track} (status={status})")

    entry = {
        "received_at": received_at,
        "ticket_id": ticket.ticket_id,
        "account_id": ctx.account_id,
        "account_name": ctx.account_name,
        "issue_summary": ticket.issue_summary,
        "severity": ticket.severity,
        "triage_issue_type": triage.issue_type,
        "churn_risk": triage.churn_risk,
        "churn_risk_reason": triage.churn_risk_reason,
        "recommended_action": triage.recommended_action,
        "routing_track": track,
        "routing_status": status,
        "reason": reason,
        "next_step": next_step,
        "owner": ctx.account.csm_owner,
        "gap_flag": triage.gap_flag,
    }

    _append_realtime_result(entry)

    if track == config.TRACK_ESCALATE or triage.churn_risk:
        _append_urgent(entry)
        logger.warning(
            f"[REALTIME] ⚠ URGENT — {ctx.account_name} ({ctx.account_id}): "
            f"track={track}, churn_risk={triage.churn_risk}. "
            f"Appended to urgent_escalations.csv."
        )

    stats.ok()
    stats.summary(logger)
    return entry
