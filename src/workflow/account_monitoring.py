"""
Stage 1 — Account Health Monitoring
Runs daily on every account. Uses Claude Haiku 4.5 for cost-efficient
classification of health signals from structured CRM + usage data.
"""
import json
from src.claude_client import ClaudeClient

MODEL = "claude-haiku-4-5-20251001"
STAGE = "1_account_monitoring"


def build_prompt(account: dict) -> str:
    trend = account["usage_trend_30d"]
    trend_summary = f"Start: {trend[0]}, End: {trend[-1]}, Change: {trend[-1]-trend[0]:+d}"
    interactions = "\n".join(
        f"  - [{i['date']}] {i['type'].upper()}: {i['note']}"
        for i in account["recent_interactions"]
    )
    stakeholders = "\n".join(
        f"  - {s['name']} ({s['title']}, sentiment: {s['sentiment']})"
        for s in account.get("stakeholders", [])
    )
    return f"""You are a customer health analyst for a B2B SaaS company.

Account: {account['company']} ({account['industry']})
MRR: ${account['mrr']:,}/month
Account age: {account['account_age_months']} months
Days since last login: {account['days_since_login']}
Open support tickets: {account['open_tickets']}
30-day usage trend: {trend_summary}
Renewal date: {account['renewal_date']}

Key stakeholders:
{stakeholders}

Recent interactions:
{interactions}

Analyze this account's health and return a JSON object with:
- health_score: integer 0-100 (your independent assessment)
- risk_level: "low" | "medium" | "high" | "critical"
- primary_risk_factor: the single most important concern (one sentence)
- recommended_action: the immediate next action for the CSM (one sentence)
- flags: list of up to 3 specific warning signals

Respond with valid JSON only, no markdown."""


def run(account: dict, client: ClaudeClient, logger, run_index: int) -> dict:
    prompt = build_prompt(account)
    response = client.create(model=MODEL, prompt=prompt, max_tokens=300)
    logger.log(
        stage=STAGE, model=MODEL, run_index=run_index,
        input_tokens=response.usage.input_tokens,
        output_tokens=response.usage.output_tokens,
    )
    raw = response.content[0].text.strip().strip("```json").strip("```").strip()
    try:
        result = json.loads(raw)
    except json.JSONDecodeError:
        result = {"health_score": 50, "risk_level": "medium",
                  "primary_risk_factor": "parse error — manual review",
                  "recommended_action": "CSM review required", "flags": []}
    result["account_id"] = account["id"]
    result["company"] = account["company"]
    result["mrr"] = account["mrr"]
    return result
