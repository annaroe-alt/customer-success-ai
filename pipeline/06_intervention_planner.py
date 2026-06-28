"""
Stage 6 — Intervention Planner
Generates targeted action plans for accounts that are Critical/High priority
or that have failing junior outputs. Plans are concrete: what, who, when,
and what success looks like.
Writes intervention_plans.json to outputs/.
"""
from models.schemas import (
    AccountContext, PriorityResult, QualityReviewResult, InterventionPlan,
)
from pipeline.utils import get_logger, call_claude, save_json, load_prompt, StageStats
import config

logger = get_logger("06_intervention_planner")

INTERVENTION_TIERS = {config.TIER_CRITICAL, config.TIER_HIGH}


def _needs_intervention(
    ctx: AccountContext,
    priority: PriorityResult | None,
    failed_outputs: list[QualityReviewResult],
) -> bool:
    if priority and priority.tier in INTERVENTION_TIERS:
        return True
    if failed_outputs:
        return True
    return False


def _build_intervention_context(
    ctx: AccountContext,
    priority: PriorityResult | None,
    failed_outputs: list[QualityReviewResult],
    triage_flags: list[dict],
) -> str:
    a = ctx.account

    priority_block = (
        f"Priority tier: {priority.tier} (score {priority.urgency_score})\n"
        f"Days to renewal: {priority.days_to_renewal} | Health drop: {priority.health_drop} pts\n"
        f"Rationale: {priority.rationale}"
        if priority else "Priority not computed."
    )

    tickets_block = "\n".join(
        f"  [{t.ticket_id}] {t.severity.upper()} — {t.issue_summary} ({t.customer_sentiment})"
        for t in ctx.tickets
    ) or "  None."

    call_block = (
        f"  {ctx.call_note.call_date}: {ctx.call_note.summary}\n"
        f"  Blocker: {ctx.call_note.risk_or_blocker}\n"
        f"  Committed follow-up: {ctx.call_note.follow_up_items}"
        if ctx.call_note else "  No recent call."
    )

    failed_block = ""
    for fo in failed_outputs:
        failed_items = [
            f"    {sid}: {v['reason']}"
            for sid, v in fo.standard_results.items()
            if not v["passed"]
        ]
        failed_block += f"  {fo.output_id} ({fo.output_type}):\n" + "\n".join(failed_items) + "\n"
    failed_block = failed_block or "  None."

    churn_flags = [f"  [{f['ticket_id']}] {f['churn_risk_reason']}" for f in triage_flags if f.get("churn_risk")]
    churn_block = "\n".join(churn_flags) or "  No churn flags from triage."

    snapshot = ctx.usage_snapshots[-1] if ctx.usage_snapshots else None
    usage_line = (
        f"{snapshot.active_users} active users, {snapshot.key_feature_users} key-feature users ({snapshot.event_date})"
        if snapshot else "No recent usage data."
    )

    return (
        f"ACCOUNT: {a.account_name} ({a.account_id})\n"
        f"Segment: {a.segment} | CSM: {a.csm_owner} | Contract: ${a.contract_value:,}\n"
        f"Renewal: {a.renewal_date} | NPS: {a.nps_score} | Expansion: {a.expansion_signal}\n"
        f"Usage: {usage_line}\n\n"
        f"PRIORITY:\n{priority_block}\n\n"
        f"OPEN TICKETS:\n{tickets_block}\n\n"
        f"LAST CALL:\n{call_block}\n\n"
        f"FAILED QS OUTPUTS:\n{failed_block}\n\n"
        f"CHURN SIGNALS FROM TRIAGE:\n{churn_block}\n"
    )


def generate_plan(
    ctx: AccountContext,
    priority: PriorityResult | None,
    failed_outputs: list[QualityReviewResult],
    triage_flags: list[dict],
) -> InterventionPlan:
    plan_text = ""  # ensure always bound before try/except
    try:
        template = load_prompt("intervention")
        prompt = template.format(
            context_block=_build_intervention_context(ctx, priority, failed_outputs, triage_flags),
            account_name=ctx.account_name,
            csm_owner=ctx.account.csm_owner,
        )
        plan_text = call_claude(prompt)
        logger.info(f"Generated intervention plan for {ctx.account_id}.")
    except Exception as e:
        logger.error(f"Intervention plan failed for {ctx.account_id}: {e}")
        plan_text = f"Error generating plan: {e}"

    return InterventionPlan(
        account_id=ctx.account_id,
        account_name=ctx.account_name,
        priority_tier=priority.tier if priority else "Unknown",
        plan_text=plan_text,
    )


_EXPECTED_PLAN_SECTIONS = [
    "## Situation Assessment",
    "## Immediate Actions",
    "## Communication Plan",
    "## Success Criteria",
    "## Escalation Trigger",
]


def plan_interventions(
    contexts: list[AccountContext],
    priority_results: list[PriorityResult],
    quality_results: list[QualityReviewResult],
    triage_results: list[dict],
) -> list[InterventionPlan]:
    stats = StageStats("06_intervention_planner")
    priority_map = {p.account_id: p for p in priority_results}
    failed_map: dict[str, list[QualityReviewResult]] = {}
    for qr in quality_results:
        if not qr.overall_passed:
            failed_map.setdefault(qr.account_id, []).append(qr)
    triage_map: dict[str, list[dict]] = {}
    for tr in triage_results:
        triage_map.setdefault(tr["account_id"], []).append(tr)

    plans = []
    for ctx in contexts:
        priority = priority_map.get(ctx.account_id)
        failed = failed_map.get(ctx.account_id, [])
        triage_flags = triage_map.get(ctx.account_id, [])

        if not _needs_intervention(ctx, priority, failed):
            logger.info(f"{ctx.account_id}: no intervention needed.")
            continue

        logger.info(
            f"Planning intervention for {ctx.account_id} ({ctx.account_name}) — "
            f"tier={priority.tier if priority else 'unknown'}, "
            f"failed_outputs={len(failed)}"
        )
        plan = generate_plan(ctx, priority, failed, triage_flags)
        plans.append(plan)

        if plan.plan_text.startswith("Error generating plan"):
            stats.fail(ctx.account_id, plan.plan_text)
        else:
            missing = [s for s in _EXPECTED_PLAN_SECTIONS if s not in plan.plan_text]
            if missing:
                stats.warn(f"{ctx.account_id}: plan missing sections {missing}")
            stats.ok()

    serialised = [
        {
            "account_id": p.account_id,
            "account_name": p.account_name,
            "priority_tier": p.priority_tier,
            "plan_text": p.plan_text,
        }
        for p in plans
    ]
    save_json(serialised, "intervention_plans.json")
    stats.summary(logger)
    logger.info(f"Generated {len(plans)} intervention plans. Saved intervention_plans.json.")
    return plans


if __name__ == "__main__":
    import importlib
    _s1 = importlib.import_module("pipeline.01_account_review")
    _s2 = importlib.import_module("pipeline.02_prioritization")

    _MOCK_PLAN = "\n".join([
        "## Situation Assessment\nTest situation.",
        "## Immediate Actions\n1. Action one (CSM, this week).",
        "## Medium-term Actions\n1. Follow up in 30 days.",
        "## Communication Plan\nEmail the exec sponsor.",
        "## Output Quality Fixes\nRewrite O001.",
        "## Success Criteria\n- Metric one.\n- Metric two.",
        "## Escalation Trigger\nIf SSO not resolved by Friday.",
    ])
    # Shadow the module-level call_claude so the mock takes effect in this module's namespace
    call_claude = lambda *a, **kw: _MOCK_PLAN  # noqa: E731

    contexts, _ = _s1.build_account_contexts()
    priorities = _s2.prioritize(contexts)
    plans = plan_interventions(contexts, priorities, [], [])
    print(f"\nGenerated {len(plans)} intervention plans (Claude mocked).")
