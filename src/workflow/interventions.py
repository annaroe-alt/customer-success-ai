"""
Stage 6 — Targeted Interventions
Weekly: generate deep intervention plans for top at-risk accounts.
Uses Claude Opus 4.8 for multi-factor reasoning on churn risk.
"""
from src.claude_client import ClaudeClient

MODEL = "claude-opus-4-8"
STAGE = "6_targeted_interventions"


def build_prompt(account: dict, health_result: dict) -> str:
    interactions = "\n".join(
        f"  [{i['date']}] {i['type'].upper()}: {i['note']}"
        for i in account["recent_interactions"]
    )
    stakeholders = "\n".join(
        f"  - {s['name']} ({s['title']}, sentiment: {s['sentiment']})"
        for s in account.get("stakeholders", [])
    )
    flags = "\n".join(f"  ⚠ {f}" for f in health_result.get("flags", []))
    trend = account["usage_trend_30d"]
    return f"""You are a senior Customer Success strategist. This account is at high churn risk.
Develop a targeted intervention plan.

ACCOUNT BRIEF
Company: {account['company']} | Industry: {account['industry']}
MRR at risk: ${account['mrr']:,}/month | Renewal: {account['renewal_date']}
Health score: {health_result['health_score']}/100 | Risk: {health_result['risk_level']}
Days since login: {account['days_since_login']} | Open tickets: {account['open_tickets']}
Usage 30-day trend: {trend[0]} → {trend[-1]} (change: {trend[-1]-trend[0]:+d})

Stakeholders:
{stakeholders}

Warning flags:
{flags}

Recent interactions:
{interactions}

Produce a 3-step intervention plan:
1. IMMEDIATE (this week): specific action, named owner, success metric
2. SHORT-TERM (weeks 2-3): what changes, how it is measured
3. ESCALATION TRIGGER: exact condition that moves to executive escalation

Also include:
- Root cause hypothesis grounded in the data
- Competitive threat assessment (if signals present)
- Revenue risk if account churns"""


def run(account: dict, health_result: dict, client: ClaudeClient,
        logger, run_index: int) -> dict:
    prompt = build_prompt(account, health_result)
    response = client.create(model=MODEL, prompt=prompt, max_tokens=700)
    logger.log(
        stage=STAGE, model=MODEL, run_index=run_index,
        input_tokens=response.usage.input_tokens,
        output_tokens=response.usage.output_tokens,
    )
    return {
        "account_id": account["id"],
        "company": account["company"],
        "intervention_plan": response.content[0].text.strip(),
    }
