"""
Stage 8 — Escalation Approval Gate
Presents each pending escalation to a CSM for approval or denial.
Only approved escalations proceed to action; denied ones are logged and
held. Updates routing_decisions.csv with final statuses.

Modes:
  interactive (default) — prompts the CSM at the terminal for each escalation.
  auto_approve=True     — approves all pending escalations without prompting
                          (useful for automated testing or non-interactive runs).
"""
import sys
from datetime import datetime, timezone

import config
from models.schemas import RoutingDecision
from pipeline.utils import get_logger, save_csv_from_dicts, StageStats

logger = get_logger("08_approval_gate")


def _display_escalation(decision: RoutingDecision, index: int, total: int) -> None:
    print()
    print(f"{'─' * 60}")
    print(f"  ESCALATION {index}/{total}  —  pending CSM review")
    print(f"{'─' * 60}")
    print(f"  Account:    {decision.account_name} ({decision.account_id})")
    print(f"  Owner:      {decision.owner}")
    print(f"  Reason:     {decision.reason}")
    print(f"  Next step:  {decision.next_step}")
    print(f"{'─' * 60}")


def _prompt_decision(decision: RoutingDecision, index: int, total: int) -> tuple[str, str, str]:
    """
    Returns (status, reviewed_by, denial_reason).
    Loops until the CSM enters a valid choice.
    """
    _display_escalation(decision, index, total)
    while True:
        choice = input("  Approve [a] / Deny [d] / Skip for now [s]: ").strip().lower()
        if choice in ("a", "approve"):
            reviewer = input("  Your name (for audit log): ").strip() or "CSM"
            return "approved", reviewer, ""
        if choice in ("d", "deny"):
            reviewer = input("  Your name (for audit log): ").strip() or "CSM"
            denial_reason = input("  Brief reason for denial: ").strip()
            return "denied", reviewer, denial_reason
        if choice in ("s", "skip", ""):
            logger.info(f"  {decision.account_id}: skipped — remains pending_review.")
            return "pending_review", "", ""
        print("  Please enter 'a', 'd', or 's'.")


def run_approval_gate(
    routing_decisions: list[RoutingDecision],
    auto_approve: bool = False,
    reviewer_name: str = "auto",
) -> list[RoutingDecision]:
    """
    Review all pending escalations and return the updated decision list.

    Args:
        routing_decisions: Full list of routing decisions from Stage 7.
        auto_approve: If True, approve all pending escalations without prompting.
        reviewer_name: Name recorded in the audit log when auto_approve=True.
    """
    stats = StageStats("08_approval_gate")

    pending = [d for d in routing_decisions if d.status == "pending_review"]

    if not pending:
        logger.info("No escalations pending review — approval gate complete.")
        _write_outputs(routing_decisions)
        return routing_decisions

    logger.info(f"{len(pending)} escalation(s) require CSM review.")

    if auto_approve:
        logger.info(f"auto_approve=True — approving all {len(pending)} escalation(s) as '{reviewer_name}'.")

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    total = len(pending)

    for i, decision in enumerate(pending, start=1):
        if auto_approve:
            decision.status = "approved"
            decision.reviewed_by = reviewer_name
            decision.reviewed_at = now
            logger.info(f"  {decision.account_id} ({decision.account_name}): auto-approved.")
            stats.ok()
            continue

        status, reviewed_by, denial_reason = _prompt_decision(decision, i, total)
        decision.status = status
        decision.reviewed_by = reviewed_by
        decision.reviewed_at = now if status != "pending_review" else ""
        decision.denial_reason = denial_reason

        if status == "approved":
            logger.info(f"  {decision.account_id}: APPROVED by {reviewed_by}.")
            stats.ok()
        elif status == "denied":
            logger.info(f"  {decision.account_id}: DENIED by {reviewed_by}. Reason: {denial_reason}")
            stats.ok()
        else:
            logger.info(f"  {decision.account_id}: skipped, still pending.")
            stats.warn(f"{decision.account_id} remains pending after review session.")

    _write_outputs(routing_decisions)
    stats.summary(logger)

    approved = [d for d in routing_decisions if d.track == config.TRACK_ESCALATE and d.status == "approved"]
    denied = [d for d in routing_decisions if d.track == config.TRACK_ESCALATE and d.status == "denied"]
    still_pending = [d for d in routing_decisions if d.status == "pending_review"]

    logger.info(
        f"Escalation review complete: "
        f"{len(approved)} approved, {len(denied)} denied, {len(still_pending)} still pending."
    )

    if denied:
        logger.info("Denied escalations — intervention plan placed on hold:")
        for d in denied:
            logger.info(f"  {d.account_id} ({d.account_name}): {d.denial_reason or 'no reason given'}")

    return routing_decisions


def _write_outputs(routing_decisions: list[RoutingDecision]) -> None:
    """Persist the final routing decisions and split escalation outcome files."""
    all_rows = [
        {
            "account_id": d.account_id,
            "account_name": d.account_name,
            "track": d.track,
            "status": d.status,
            "reason": d.reason,
            "owner": d.owner,
            "next_step": d.next_step,
            "reviewed_by": d.reviewed_by,
            "reviewed_at": d.reviewed_at,
            "denial_reason": d.denial_reason,
        }
        for d in routing_decisions
    ]
    save_csv_from_dicts(all_rows, "routing_decisions.csv")

    approved = [
        d for d in routing_decisions
        if d.track == config.TRACK_ESCALATE and d.status == "approved"
    ]
    if approved:
        save_csv_from_dicts(
            [{"account_id": d.account_id, "account_name": d.account_name,
              "owner": d.owner, "next_step": d.next_step,
              "reviewed_by": d.reviewed_by, "reviewed_at": d.reviewed_at}
             for d in approved],
            "escalations_approved.csv",
        )
        logger.info(f"Saved {len(approved)} approved escalation(s) to escalations_approved.csv.")

    denied = [
        d for d in routing_decisions
        if d.track == config.TRACK_ESCALATE and d.status == "denied"
    ]
    if denied:
        save_csv_from_dicts(
            [{"account_id": d.account_id, "account_name": d.account_name,
              "owner": d.owner, "reason": d.reason,
              "reviewed_by": d.reviewed_by, "reviewed_at": d.reviewed_at,
              "denial_reason": d.denial_reason}
             for d in denied],
            "escalations_denied.csv",
        )
        logger.info(f"Saved {len(denied)} denied escalation(s) to escalations_denied.csv.")
