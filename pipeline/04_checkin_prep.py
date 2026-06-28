"""
Stage 4 — Check-in Prep
For each scheduled check-in, generates a structured CSM briefing via Claude.
Writes checkin_briefs.json to outputs/.
"""
from models.schemas import AccountContext, CheckIn, CheckInBrief, PriorityResult
from pipeline.utils import get_logger, call_claude, save_json, load_prompt, StageStats

logger = get_logger("04_checkin_prep")


def _build_context_block(ctx: AccountContext, priority: PriorityResult | None) -> str:
    a = ctx.account

    snapshots_text = ""
    for s in ctx.usage_snapshots:
        snapshots_text += f"  {s.event_date}: {s.active_users} active users, {s.key_feature_users} key-feature users\n"

    tickets_text = ""
    for t in ctx.tickets:
        tickets_text += f"  [{t.ticket_id}] {t.severity.upper()} — {t.issue_summary} (sentiment: {t.customer_sentiment})\n"

    call_text = (
        f"  {ctx.call_note.call_date}: {ctx.call_note.summary}\n"
        f"  Goal: {ctx.call_note.customer_goal}\n"
        f"  Blocker: {ctx.call_note.risk_or_blocker}\n"
        f"  Follow-up committed: {ctx.call_note.follow_up_items}"
        if ctx.call_note else "  No recent call notes."
    )

    tier_text = f"{priority.tier} (score {priority.urgency_score})" if priority else "Not scored"

    return (
        f"ACCOUNT: {a.account_name} ({a.account_id})\n"
        f"Segment: {a.segment} | Contract: ${a.contract_value:,} | Renewal: {a.renewal_date}\n"
        f"Health: {a.current_health_score} (prev {a.previous_health_score}) | Trend: {a.product_usage_trend} | NPS: {a.nps_score}\n"
        f"Expansion signal: {a.expansion_signal} | Priority tier: {tier_text}\n"
        f"Notes: {a.notes}\n\n"
        f"USAGE HISTORY:\n{snapshots_text or '  No data.'}\n"
        f"OPEN TICKETS:\n{tickets_text or '  None.'}\n"
        f"LAST CALL:\n{call_text}\n"
    )


def generate_brief(ctx: AccountContext, checkin: CheckIn, priority: PriorityResult | None) -> CheckInBrief:
    try:
        template = load_prompt("checkin_brief")
        prompt = template.format(
            context_block=_build_context_block(ctx, priority),
            checkin_type=checkin.checkin_type,
            scheduled_date=checkin.scheduled_date,
            checkin_priority=checkin.priority,
            topics_to_cover=checkin.topics_to_cover,
        )
        brief_text = call_claude(prompt)
        logger.info(f"Generated brief for {ctx.account_id} ({checkin.checkin_id}).")
    except Exception as e:
        logger.error(f"Brief generation failed for {ctx.account_id}: {e}")
        brief_text = f"Error generating brief: {e}"

    return CheckInBrief(
        checkin_id=checkin.checkin_id,
        account_id=ctx.account_id,
        account_name=ctx.account_name,
        scheduled_date=checkin.scheduled_date,
        brief_text=brief_text,
    )


def prep_all_checkins(
    contexts: list[AccountContext],
    priority_results: list[PriorityResult],
) -> list[CheckInBrief]:
    stats = StageStats("04_checkin_prep")
    priority_map = {p.account_id: p for p in priority_results}

    accounts_with_checkins = [c for c in contexts if c.checkin]
    if not accounts_with_checkins:
        logger.warning("No scheduled check-ins found — check-in prep produced no output.")

    briefs = []
    for ctx in contexts:
        if ctx.checkin is None:
            continue
        logger.info(
            f"Preparing brief for {ctx.account_id} ({ctx.account_name}) — "
            f"{ctx.checkin.checkin_type} on {ctx.checkin.scheduled_date} "
            f"[priority: {ctx.checkin.priority}]"
        )
        priority = priority_map.get(ctx.account_id)
        brief = generate_brief(ctx, ctx.checkin, priority)

        if brief.brief_text.startswith("Error generating brief"):
            stats.fail(ctx.account_id, brief.brief_text)
        else:
            missing_sections = [
                h for h in ["## Situation", "## Open Risks", "## Recommended", "## Suggested Ask"]
                if h not in brief.brief_text
            ]
            if missing_sections:
                stats.warn(
                    f"{ctx.account_id}: brief may be incomplete — "
                    f"missing expected sections: {missing_sections}"
                )
            stats.ok()
        briefs.append(brief)

    serialised = [
        {
            "checkin_id": b.checkin_id,
            "account_id": b.account_id,
            "account_name": b.account_name,
            "scheduled_date": b.scheduled_date,
            "brief_text": b.brief_text,
        }
        for b in briefs
    ]
    save_json(serialised, "checkin_briefs.json")
    stats.summary(logger)
    logger.info(f"Generated {len(briefs)} check-in briefs. Saved checkin_briefs.json.")
    return briefs


if __name__ == "__main__":
    import importlib
    _s1 = importlib.import_module("pipeline.01_account_review")
    _s2 = importlib.import_module("pipeline.02_prioritization")
    # Shadow the module-level call_claude so the mock takes effect in this module's namespace
    call_claude = lambda *a, **kw: (  # noqa: E731
        "## Situation Summary\nTest.\n## Open Risks\n- None.\n"
        "## Committed Follow-ups\nNone.\n## Recommended Talking Points\n- Test.\n"
        "## Suggested Ask\nTest ask."
    )
    contexts, _ = _s1.build_account_contexts()
    priorities = _s2.prioritize(contexts)
    briefs = prep_all_checkins(contexts, priorities)
    print(f"\nGenerated {len(briefs)} check-in briefs (Claude mocked).")
