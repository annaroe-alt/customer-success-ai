"""
Stage 3 — Inbound Issue Handling / Triage
Runs on every inbound ticket/email. Uses Claude Haiku 4.5 for fast
classification: category, urgency, owner routing, SLA assignment.
"""
import json
from src.claude_client import ClaudeClient

MODEL = "claude-haiku-4-5-20251001"
STAGE = "3_inbound_triage"


def build_prompt(issue: dict) -> str:
    return f"""You are a customer success triage agent for a B2B SaaS company.

Incoming issue:
Company: {issue['company']} (MRR: ${issue['account_mrr']:,})
Channel: {issue['channel']}
Subject: {issue['subject']}
Body: {issue['body']}

Classify and return JSON:
{{
  "ticket_id": "{issue['id']}",
  "category": "bug" | "feature_request" | "billing" | "compliance" | "how_to" | "performance" | "escalation",
  "urgency": "P1" | "P2" | "P3" | "P4",
  "suggested_owner": "CSM" | "Support Tier 1" | "Support Tier 2" | "Engineering" | "Account Executive",
  "sla_hours": integer,
  "summary": "one sentence issue summary",
  "needs_escalation": true or false,
  "escalation_reason": "reason string or null"
}}

P1=system down/compliance/data loss, P2=major feature broken, P3=minor issue, P4=question/request.
Return valid JSON only, no markdown."""


def run(issue: dict, client: ClaudeClient, logger, run_index: int) -> dict:
    prompt = build_prompt(issue)
    response = client.create(model=MODEL, prompt=prompt, max_tokens=300)
    logger.log(
        stage=STAGE, model=MODEL, run_index=run_index,
        input_tokens=response.usage.input_tokens,
        output_tokens=response.usage.output_tokens,
    )
    raw = response.content[0].text.strip().strip("```json").strip("```").strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"ticket_id": issue["id"], "category": "unknown", "urgency": "P2",
                "suggested_owner": "CSM", "sla_hours": 4,
                "summary": "parse error — manual review", "needs_escalation": False,
                "escalation_reason": None}
