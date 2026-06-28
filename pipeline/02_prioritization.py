"""
Stage 2 — Prioritization
Scores and ranks all accounts using deterministic signals. Borderline cases
(score within 5 points of a tier boundary) are validated by Claude.
Writes priority_rankings.csv to outputs/.
"""
from datetime import date, datetime

import config
from models.schemas import AccountContext, PriorityResult
from pipeline.utils import get_logger, call_claude, save_csv_from_dicts, load_prompt

logger = get_logger("02_prioritization")

# Tier boundaries (higher score = more urgent)
TIER_BOUNDARIES = [
    (80, config.TIER_CRITICAL),
    (55, config.TIER_HIGH),
    (35, config.TIER_MEDIUM),
    (15, config.TIER_LOW),
    (0,  config.TIER_MONITOR),
]

BORDERLINE_MARGIN = 5


def days_until(date_str: str) -> int:
    try:
        renewal = datetime.strptime(date_str, "%Y-%m-%d").date()
        return (renewal - date.today()).days
    except ValueError:
        return 999


def renewal_score(days: int) -> float:
    if days <= config.RENEWAL_CRITICAL_DAYS:
        return 40
    if days <= config.RENEWAL_HIGH_DAYS:
        return 25
    if days <= config.RENEWAL_MEDIUM_DAYS:
        return 10
    return 0


def health_drop_score(drop: int) -> float:
    if drop >= config.HEALTH_DROP_CRITICAL:
        return 25
    if drop >= config.HEALTH_DROP_HIGH:
        return 15
    if drop > 0:
        return 8
    return 0


def usage_trend_score(trend: str) -> float:
    return {"declining": 15, "flat": 5, "growing": 0}.get(trend.lower(), 5)


def ticket_score(count: int, severity: str) -> float:
    base = min(count * 2, 12)
    severity_bonus = {"high": 8, "medium": 4, "low": 0}.get(severity.lower(), 0)
    return base + severity_bonus


def nps_score_component(nps: int) -> float:
    if nps <= 3:
        return 10
    if nps <= 5:
        return 5
    return 0


def expansion_discount(signal: str) -> float:
    # Positive expansion tempers urgency slightly
    return {"high": -5, "medium": -2, "low": 0}.get(signal.lower(), 0)


def compute_score(ctx: AccountContext) -> tuple[float, int, int]:
    days = days_until(ctx.account.renewal_date)
    drop = ctx.account.previous_health_score - ctx.account.current_health_score

    # Determine worst ticket severity for this account
    severities = [t.severity for t in ctx.tickets]
    worst = "low"
    for sev in ["high", "medium", "low"]:
        if sev in [s.lower() for s in severities]:
            worst = sev
            break

    score = (
        renewal_score(days)
        + health_drop_score(drop)
        + usage_trend_score(ctx.account.product_usage_trend)
        + ticket_score(len(ctx.tickets), worst)
        + nps_score_component(ctx.account.nps_score)
        + expansion_discount(ctx.account.expansion_signal)
    )
    return max(score, 0), days, drop


def score_to_tier(score: float) -> str:
    for threshold, tier in TIER_BOUNDARIES:
        if score >= threshold:
            return tier
    return config.TIER_MONITOR


def is_borderline(score: float) -> bool:
    for threshold, _ in TIER_BOUNDARIES:
        if abs(score - threshold) <= BORDERLINE_MARGIN:
            return True
    return False


def claude_validate_tier(ctx: AccountContext, score: float, tier: str) -> tuple[str, str]:
    """Ask Claude to confirm or adjust the tier for borderline accounts."""
    try:
        prompt_template = load_prompt("prioritization")
        prompt = prompt_template.format(
            account_name=ctx.account_name,
            account_id=ctx.account_id,
            segment=ctx.account.segment,
            contract_value=ctx.account.contract_value,
            renewal_date=ctx.account.renewal_date,
            health_now=ctx.account.current_health_score,
            health_prev=ctx.account.previous_health_score,
            usage_trend=ctx.account.product_usage_trend,
            nps=ctx.account.nps_score,
            expansion=ctx.account.expansion_signal,
            ticket_count=len(ctx.tickets),
            notes=ctx.account.notes,
            computed_score=score,
            computed_tier=tier,
        )
        response = call_claude(prompt)
        lines = [l.strip() for l in response.splitlines() if l.strip()]
        validated_tier = tier
        rationale = response
        for line in lines:
            if line.upper().startswith("TIER:"):
                validated_tier = line.split(":", 1)[1].strip()
            if line.upper().startswith("RATIONALE:"):
                rationale = line.split(":", 1)[1].strip()
        return validated_tier, rationale
    except Exception as e:
        logger.warning(f"Claude validation failed for {ctx.account_id}: {e}. Keeping computed tier.")
        return tier, f"Computed score {score:.1f}"


def prioritize(contexts: list[AccountContext]) -> list[PriorityResult]:
    results = []
    for ctx in contexts:
        score, days, drop = compute_score(ctx)
        tier = score_to_tier(score)

        if is_borderline(score):
            logger.info(f"{ctx.account_id} is borderline (score={score:.1f}, tier={tier}). Asking Claude.")
            tier, rationale = claude_validate_tier(ctx, score, tier)
        else:
            rationale = f"Urgency score {score:.1f}"

        result = PriorityResult(
            account_id=ctx.account_id,
            account_name=ctx.account_name,
            tier=tier,
            urgency_score=round(score, 1),
            rationale=rationale,
            days_to_renewal=days,
            health_drop=drop,
        )
        results.append(result)
        logger.info(f"{ctx.account_id} ({ctx.account_name}): {tier} (score={score:.1f}, days={days})")

    results.sort(key=lambda r: r.urgency_score, reverse=True)

    rows = [
        {
            "account_id": r.account_id,
            "account_name": r.account_name,
            "tier": r.tier,
            "urgency_score": r.urgency_score,
            "days_to_renewal": r.days_to_renewal,
            "health_drop": r.health_drop,
            "rationale": r.rationale,
        }
        for r in results
    ]
    save_csv_from_dicts(rows, "priority_rankings.csv")
    logger.info("Saved priority_rankings.csv.")
    return results


if __name__ == "__main__":
    import importlib
    _s1 = importlib.import_module("pipeline.01_account_review")
    contexts, _ = _s1.build_account_contexts()
    prioritize(contexts)
