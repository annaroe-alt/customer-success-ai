"""
Stage 7 — Router
Assigns each account to one of three tracks: Resolve, Follow-up, or Escalate.
Decision is rule-based first; Claude is called for ambiguous accounts.
Writes routing_decisions.csv to outputs/.
"""
import config
from models.schemas import AccountContext, PriorityResult, RoutingDecision
from pipeline.utils import get_logger, call_claude, save_csv_from_dicts, load_prompt, StageStats, validate_claude_enum

logger = get_logger("07_router")

ESCALATE_TIERS = {config.TIER_CRITICAL}

# Keywords in ticket summaries / call notes that force escalation
ESCALATION_KEYWORDS = [
    "sso", "sync fail", "integration fail", "no champion", "no clear champion",
    "roadmap", "executive", "exec sponsor", "implementation block",
]


def _has_escalation_signal(ctx: AccountContext) -> bool:
    combined = " ".join([
        t.issue_summary.lower() for t in ctx.tickets
    ] + [
        (ctx.call_note.risk_or_blocker.lower() if ctx.call_note else "")
    ])
    return any(kw in combined for kw in ESCALATION_KEYWORDS)


def _has_open_follow_up(ctx: AccountContext) -> bool:
    if ctx.call_note and ctx.call_note.follow_up_items:
        return True
    if ctx.checkin:
        return True
    return False


def rule_based_route(
    ctx: AccountContext,
    priority: PriorityResult | None,
) -> tuple[str, str] | None:
    """Returns (track, reason) if a rule fires, else None for Claude to decide."""
    tier = priority.tier if priority else config.TIER_MONITOR

    # Hard escalation: critical tier or explicit escalation keyword
    if tier in ESCALATE_TIERS or _has_escalation_signal(ctx):
        reason = (
            f"Critical priority tier ({tier})" if tier in ESCALATE_TIERS
            else "Escalation signal detected in tickets/call notes"
        )
        return config.TRACK_ESCALATE, reason

    # Low / monitor with no open signals → Resolve
    if tier in {config.TIER_LOW, config.TIER_MONITOR}:
        if not ctx.tickets and not _has_open_follow_up(ctx):
            return config.TRACK_RESOLVE, "Low urgency, no open items."

    return None  # ambiguous — ask Claude


def claude_route(ctx: AccountContext, priority: PriorityResult | None) -> tuple[str, str, str]:
    """Returns (track, reason, next_step) from Claude."""
    a = ctx.account
    tier = priority.tier if priority else "Unknown"
    score = priority.urgency_score if priority else 0
    days = priority.days_to_renewal if priority else 999

    tickets_text = "\n".join(
        f"  [{t.ticket_id}] {t.severity} — {t.issue_summary} ({t.customer_sentiment})"
        for t in ctx.tickets
    ) or "  None."
    call_text = (
        f"  Blocker: {ctx.call_note.risk_or_blocker}\n"
        f"  Follow-up committed: {ctx.call_note.follow_up_items}"
        if ctx.call_note else "  No recent call."
    )

    template = load_prompt("routing")
    prompt = template.format(
        account_name=a.account_name,
        account_id=a.account_id,
        segment=a.segment,
        contract_value=a.contract_value,
        renewal_date=a.renewal_date,
        health_score=a.current_health_score,
        usage_trend=a.product_usage_trend,
        nps=a.nps_score,
        expansion=a.expansion_signal,
        tier=tier,
        urgency_score=score,
        days_to_renewal=days,
        tickets_text=tickets_text,
        call_text=call_text,
        csm_owner=a.csm_owner,
    )
    response = call_claude(prompt, model=config.MODEL_FAST, max_tokens=config.MAX_TOKENS_SHORT)

    _VALID_TRACKS = {config.TRACK_RESOLVE, config.TRACK_FOLLOW_UP, config.TRACK_ESCALATE}
    track = config.TRACK_FOLLOW_UP
    reason = ""
    next_step = ""
    track_found = False
    for line in response.splitlines():
        s = line.strip()
        low = s.lower()
        if low.startswith("track:"):
            raw = s.split(":", 1)[1].strip()
            track = validate_claude_enum(
                raw, _VALID_TRACKS, "track", config.TRACK_FOLLOW_UP, logger, a.account_id
            )
            track_found = True
        elif low.startswith("reason:"):
            reason = s.split(":", 1)[1].strip()
        elif low.startswith("next_step:"):
            next_step = s.split(":", 1)[1].strip()

    if not track_found:
        logger.warning(
            f"{a.account_id}: Claude routing response did not contain a TRACK: line. "
            f"Defaulting to Follow-up. Raw (first 200): {response[:200]!r}"
        )

    return track, reason or response[:200], next_step


def route_all(
    contexts: list[AccountContext],
    priority_results: list[PriorityResult],
) -> list[RoutingDecision]:
    stats = StageStats("07_router")
    priority_map = {p.account_id: p for p in priority_results}
    decisions = []

    for ctx in contexts:
        priority = priority_map.get(ctx.account_id)
        result = rule_based_route(ctx, priority)

        if result:
            track, reason = result
            next_step = _default_next_step(track, ctx)
            logger.info(f"{ctx.account_id} ({ctx.account_name}): rule → {track}")
        else:
            try:
                track, reason, next_step = claude_route(ctx, priority)
                logger.info(f"{ctx.account_id} ({ctx.account_name}): Claude → {track}")
            except Exception as e:
                logger.error(
                    f"Routing failed for {ctx.account_id}: {e}. Defaulting to Follow-up."
                )
                track = config.TRACK_FOLLOW_UP
                reason = f"Routing error: {e}"
                next_step = "Manual review required."
                stats.fail(ctx.account_id, str(e))
                decisions.append(RoutingDecision(
                    account_id=ctx.account_id,
                    account_name=ctx.account_name,
                    track=track,
                    reason=reason,
                    owner=ctx.account.csm_owner,
                    next_step=next_step,
                ))
                continue

        stats.ok()
        # Escalations require CSM approval before action; all other tracks are auto-approved.
        status = "pending_review" if track == config.TRACK_ESCALATE else "approved"
        decisions.append(RoutingDecision(
            account_id=ctx.account_id,
            account_name=ctx.account_name,
            track=track,
            reason=reason,
            owner=ctx.account.csm_owner,
            next_step=next_step,
            status=status,
        ))

    rows = [
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
        for d in decisions
    ]
    save_csv_from_dicts(rows, "routing_decisions.csv")

    # Write a focused queue file containing only escalations awaiting review.
    pending = [d for d in decisions if d.status == "pending_review"]
    if pending:
        pending_rows = [
            {
                "account_id": d.account_id,
                "account_name": d.account_name,
                "owner": d.owner,
                "reason": d.reason,
                "next_step": d.next_step,
            }
            for d in pending
        ]
        save_csv_from_dicts(pending_rows, "escalations_pending.csv")
        logger.info(f"{len(pending)} escalation(s) written to escalations_pending.csv — awaiting CSM approval.")

    stats.summary(logger)

    track_counts = {}
    for d in decisions:
        track_counts[d.track] = track_counts.get(d.track, 0) + 1
    logger.info(
        f"Routed {len(decisions)} accounts: "
        + " | ".join(f"{t}={n}" for t, n in sorted(track_counts.items()))
        + ". Saved routing_decisions.csv."
    )
    return decisions


def _default_next_step(track: str, ctx: AccountContext) -> str:
    if track == config.TRACK_ESCALATE:
        return "Escalate to engineering/product/exec — coordinate via CSM."
    if track == config.TRACK_FOLLOW_UP:
        return ctx.call_note.follow_up_items if ctx.call_note else "Schedule follow-up call."
    return "Close open tickets and confirm no further action needed."


if __name__ == "__main__":
    import importlib
    _s1 = importlib.import_module("pipeline.01_account_review")
    _s2 = importlib.import_module("pipeline.02_prioritization")
    # Shadow the module-level call_claude so the mock takes effect in this module's namespace
    call_claude = lambda *a, **kw: (  # noqa: E731
        "TRACK: Follow-up\n"
        "REASON: Account has pending deliverables.\n"
        "NEXT_STEP: Send follow-up email within 48 hours."
    )
    contexts, _ = _s1.build_account_contexts()
    priorities = _s2.prioritize(contexts)
    decisions = route_all(contexts, priorities)
    for t in [config.TRACK_ESCALATE, config.TRACK_FOLLOW_UP, config.TRACK_RESOLVE]:
        n = sum(1 for d in decisions if d.track == t)
        print(f"  {t}: {n}")
