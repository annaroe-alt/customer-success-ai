"""
Stage 7 — Responsiveness / Escalation
Triggered when: urgency P1, escalate_to_manager flag, or health_score < 35.
Uses Claude Opus 4.8 for high-stakes multi-stakeholder reasoning.
"""
from src.claude_client import ClaudeClient

MODEL = "claude-opus-4-8"
STAGE = "7_escalation"


def build_prompt(account: dict, health_result: dict,
                 triage_result: dict, trigger_reason: str) -> str:
    interactions = "\n".join(
        f"  [{i['date']}] {i['type'].upper()}: {i['note']}"
        for i in account["recent_interactions"]
    )
    stakeholders = "\n".join(
        f"  - {s['name']} ({s['title']}, sentiment: {s['sentiment']})"
        for s in account.get("stakeholders", [])
    )
    return f"""You are VP of Customer Success handling an executive escalation.

ESCALATION TRIGGER: {trigger_reason}

ACCOUNT
Company: {account['company']} | Industry: {account['industry']}
MRR at risk: ${account['mrr']:,}/month | Renewal: {account['renewal_date']}
Health score: {health_result['health_score']}/100 | Risk: {health_result['risk_level']}
Flags: {'; '.join(health_result.get('flags', []))}

Stakeholder map:
{stakeholders}

Interaction history:
{interactions}

Active issue:
  Category: {triage_result.get('category', 'N/A')} | Urgency: {triage_result.get('urgency', 'N/A')}
  Summary: {triage_result.get('summary', 'N/A')}

Produce:
1. EXECUTIVE SUMMARY (3 sentences): situation, business risk, recommended response
2. ESCALATION MEMO for VP CS + AE: impact, root cause, what has been tried, what we need from leadership
3. STAKEHOLDER OUTREACH PLAN: who contacts whom, in what order, via what channel, with what message
4. SUCCESS CRITERIA: how we know this escalation resolved successfully
5. 14-DAY TIMELINE: key milestones and check-ins"""


def run(account: dict, health_result: dict, triage_result: dict,
        trigger_reason: str, client: ClaudeClient, logger, run_index: int) -> dict:
    prompt = build_prompt(account, health_result, triage_result, trigger_reason)
    response = client.create(model=MODEL, prompt=prompt, max_tokens=800)
    logger.log(
        stage=STAGE, model=MODEL, run_index=run_index,
        input_tokens=response.usage.input_tokens,
        output_tokens=response.usage.output_tokens,
    )
    return {
        "account_id": account["id"],
        "company": account["company"],
        "trigger": trigger_reason,
        "escalation_memo": response.content[0].text.strip(),
    }
