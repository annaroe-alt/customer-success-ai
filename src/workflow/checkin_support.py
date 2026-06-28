"""
Stage 4 — Customer Check-in Support
Weekly: generate personalized check-in email drafts for priority accounts.
Uses Claude Sonnet 4.6 for high-quality, contextually nuanced drafts.
"""
from src.claude_client import ClaudeClient

MODEL = "claude-sonnet-4-6"
STAGE = "4_checkin_support"


def build_prompt(account: dict, priority_info: dict) -> str:
    interactions = "\n".join(
        f"  [{i['date']}] {i['type'].upper()}: {i['note']}"
        for i in account["recent_interactions"]
    )
    stakeholders = ", ".join(
        f"{s['name']} ({s['title']}, sentiment: {s['sentiment']})"
        for s in account.get("stakeholders", [])
    )
    return f"""You are a senior Customer Success Manager at a B2B SaaS company.
Draft a personalized check-in email for this account.

Account context:
- Company: {account['company']} | Industry: {account['industry']}
- MRR: ${account['mrr']:,}/month | Account age: {account['account_age_months']} months
- Health score: {account['health_score']}/100
- Renewal date: {account['renewal_date']}
- Open tickets: {account['open_tickets']}
- Key stakeholders: {stakeholders}
- Priority action: {priority_info.get('csm_action', 'routine check-in')}

Recent interactions:
{interactions}

Write a warm, professional check-in email (150-200 words) that:
1. References a specific recent interaction showing attention to detail
2. Addresses the account's current situation honestly
3. Offers one concrete value-add (resource, walkthrough, or connection)
4. Ends with a clear, low-friction call to action

Format exactly as:
Subject: [subject line]

[email body]

---
CSM Talking Points (internal only):
- [bullet 1]
- [bullet 2]
- [bullet 3]"""


def run(account: dict, priority_info: dict, client: ClaudeClient,
        logger, run_index: int) -> dict:
    prompt = build_prompt(account, priority_info)
    response = client.create(model=MODEL, prompt=prompt, max_tokens=500)
    logger.log(
        stage=STAGE, model=MODEL, run_index=run_index,
        input_tokens=response.usage.input_tokens,
        output_tokens=response.usage.output_tokens,
    )
    return {
        "account_id": account["id"],
        "company": account["company"],
        "draft": response.content[0].text.strip(),
    }
