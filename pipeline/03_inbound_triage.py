"""
Stage 3 — Inbound Triage
Classifies each support ticket via Claude: issue type, churn risk,
recommended action. Also detects accounts present in tickets but absent
from the scheduled check-in list (gap accounts).
Writes triage_results.json to outputs/.
"""
from models.schemas import AccountContext, SupportTicket, TriageResult
from pipeline.utils import get_logger, call_claude, save_json, load_prompt, StageStats, validate_claude_enum

logger = get_logger("03_inbound_triage")


def _build_account_summary(ctx: AccountContext) -> str:
    a = ctx.account
    snapshots = ctx.usage_snapshots[-1] if ctx.usage_snapshots else None
    usage_line = (
        f"Latest usage: {snapshots.active_users} active users, "
        f"{snapshots.key_feature_users} key-feature users ({snapshots.event_date})"
        if snapshots else "No recent usage data."
    )
    call_line = (
        f"Last call ({ctx.call_note.call_date}): {ctx.call_note.summary}. "
        f"Risk noted: {ctx.call_note.risk_or_blocker}."
        if ctx.call_note else "No recent call note."
    )
    return (
        f"Account: {a.account_name} ({a.account_id}) | Segment: {a.segment} | "
        f"Contract: ${a.contract_value:,} | Renewal: {a.renewal_date}\n"
        f"Health: {a.current_health_score} (was {a.previous_health_score}) | "
        f"Trend: {a.product_usage_trend} | NPS: {a.nps_score}\n"
        f"{usage_line}\n{call_line}\n"
        f"Check-in scheduled: {'Yes' if ctx.checkin else 'No'}"
    )


def triage_ticket(ticket: SupportTicket, ctx: AccountContext) -> TriageResult:
    try:
        template = load_prompt("triage")
        prompt = template.format(
            account_summary=_build_account_summary(ctx),
            ticket_id=ticket.ticket_id,
            date_received=ticket.date_received,
            issue_summary=ticket.issue_summary,
            severity=ticket.severity,
            sentiment=ticket.customer_sentiment,
            frontline_notes=ticket.frontline_notes,
            status=ticket.current_status,
        )
        response = call_claude(prompt)
        return _parse_triage_response(ticket, ctx, response)
    except Exception as e:
        logger.error(f"Triage failed for {ticket.ticket_id}: {e}")
        return TriageResult(
            ticket_id=ticket.ticket_id,
            account_id=ticket.account_id,
            issue_type="unknown",
            churn_risk=False,
            churn_risk_reason=f"Parse error: {e}",
            recommended_action="manual review",
            gap_flag=ctx.checkin is None,
            gap_note="No check-in scheduled." if ctx.checkin is None else "",
        )


def _parse_triage_response(ticket: SupportTicket, ctx: AccountContext, response: str) -> TriageResult:
    issue_type = "unknown"
    churn_risk = False
    churn_risk_reason = ""
    recommended_action = ""

    _VALID_ISSUE_TYPES = {"technical", "enablement", "strategic", "churn-risk"}

    for line in response.splitlines():
        line = line.strip()
        low = line.lower()
        if low.startswith("issue_type:"):
            raw = line.split(":", 1)[1].strip()
            issue_type = validate_claude_enum(
                raw, _VALID_ISSUE_TYPES, "issue_type", "unknown", logger, ticket.ticket_id
            )
        elif low.startswith("churn_risk:"):
            val = line.split(":", 1)[1].strip().lower()
            churn_risk = val.startswith("yes") or val.startswith("true")
        elif low.startswith("churn_risk_reason:"):
            churn_risk_reason = line.split(":", 1)[1].strip()
        elif low.startswith("recommended_action:"):
            recommended_action = line.split(":", 1)[1].strip()

    # If parsing found nothing structured, the response format was unexpected
    if issue_type == "unknown" and not recommended_action:
        logger.warning(
            f"{ticket.ticket_id}: Claude response did not match expected format. "
            f"Raw response (first 200 chars): {response[:200]!r}"
        )
        recommended_action = response[:300]
    elif not recommended_action:
        recommended_action = response[:300]

    gap_flag = ctx.checkin is None
    gap_note = "No check-in scheduled — account needs to be added to queue." if gap_flag else ""

    return TriageResult(
        ticket_id=ticket.ticket_id,
        account_id=ticket.account_id,
        issue_type=issue_type,
        churn_risk=churn_risk,
        churn_risk_reason=churn_risk_reason,
        recommended_action=recommended_action,
        gap_flag=gap_flag,
        gap_note=gap_note,
    )


def triage_all(contexts: list[AccountContext]) -> list[TriageResult]:
    stats = StageStats("03_inbound_triage")
    results = []

    accounts_with_tickets = [c for c in contexts if c.tickets]
    if not accounts_with_tickets:
        logger.warning("No accounts have tickets — triage stage produced no output.")

    for ctx in contexts:
        if not ctx.tickets:
            continue
        for ticket in ctx.tickets:
            logger.info(
                f"Triaging {ticket.ticket_id} ({ticket.severity}/{ticket.customer_sentiment}) "
                f"for {ctx.account_id} ({ctx.account_name})..."
            )
            result = triage_ticket(ticket, ctx)
            results.append(result)

            if result.issue_type == "unknown":
                stats.fail(ticket.ticket_id, "Claude response did not yield a valid issue_type")
            else:
                stats.ok()
            if result.gap_flag:
                stats.warn(f"{ctx.account_id}: gap account — tickets present but no check-in scheduled")

    serialised = [
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
        for r in results
    ]
    save_json(serialised, "triage_results.json")
    stats.summary(logger)
    logger.info(f"Triaged {len(results)} tickets. Saved triage_results.json.")
    return results


if __name__ == "__main__":
    import importlib
    _s1 = importlib.import_module("pipeline.01_account_review")
    contexts, _ = _s1.build_account_contexts()
    results = triage_all(contexts)
    churn = [r for r in results if r.churn_risk]
    gaps  = [r for r in results if r.gap_flag]
    print(f"\nTriaged {len(results)} tickets | {len(churn)} churn-risk | {len(gaps)} gap accounts")
