"""
Stage 2 — Account Prioritization / Risk Scoring
Weekly batch run across all accounts. Uses Claude Haiku 4.5 to classify
priority tier from health monitoring output and trend data.
"""
import json
from src.claude_client import ClaudeClient

MODEL = "claude-haiku-4-5-20251001"
STAGE = "2_prioritization"


def build_prompt(accounts: list) -> str:
    accounts_text = "\n".join(
        f"- ID: {a['account_id']} | Company: {a['company']} "
        f"| Health: {a['health_score']} | Risk: {a['risk_level']} "
        f"| MRR: ${a.get('mrr', 0):,} | Flags: {'; '.join(a.get('flags', []))}"
        for a in accounts
    )
    return f"""You are a customer success operations manager.

{len(accounts)} accounts with current health scores and risk signals:
{accounts_text}

Assign each account a priority tier and recommended weekly CSM action.

Return a JSON array. Each element:
{{
  "account_id": "...",
  "priority_tier": 1-4 (1=urgent/churn risk, 2=at-risk, 3=monitor, 4=healthy),
  "csm_action": "specific next action for the CSM (one sentence)",
  "escalate_to_manager": true or false
}}

Return valid JSON array only, no markdown."""


def run(health_results: list, client: ClaudeClient, logger, run_index: int) -> list:
    prompt = build_prompt(health_results)
    response = client.create(model=MODEL, prompt=prompt, max_tokens=600)
    logger.log(
        stage=STAGE, model=MODEL, run_index=run_index,
        input_tokens=response.usage.input_tokens,
        output_tokens=response.usage.output_tokens,
    )
    raw = response.content[0].text.strip().strip("```json").strip("```").strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return [{"account_id": a["account_id"], "priority_tier": 2,
                 "csm_action": "manual review required", "escalate_to_manager": False}
                for a in health_results]
