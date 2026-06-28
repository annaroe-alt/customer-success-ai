"""
Customer Success AI — End-to-End Workflow Runner
Executes all 9 workflow stages against sample accounts and inbound issues,
logs token usage per stage, and prints a cost report.

Usage:
    python main.py

Requires: ANTHROPIC_API_KEY environment variable
Scale note: Sample data = 5 accounts, 5 tickets. Production design handles
2,000+ accounts; see Token Math Sheet for annualized cost projections.
"""
import json
import os

from src.token_logger import TokenLogger
from src.claude_client import make_client
from src.workflow import (
    account_monitoring,
    prioritization,
    inbound_triage,
    checkin_support,
    quality_review,
    interventions,
    escalation,
    memory_retrieval,
    evaluation,
)

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")


def load_json(filename: str) -> list:
    with open(os.path.join(DATA_DIR, filename)) as f:
        return json.load(f)


def main():
    client = make_client()
    logger = TokenLogger()

    accounts = load_json("accounts.json")
    issues   = load_json("inbound_issues.json")

    print("=" * 60)
    print("Customer Success AI — Full Workflow Run")
    print(f"Processing {len(accounts)} accounts, {len(issues)} inbound issues")
    print("=" * 60)

    # ── Stage 1: Account Health Monitoring ────────────────────────
    print(f"\n[Stage 1] Account Health Monitoring ({len(accounts)} accounts)...")
    health_results = []
    for i, account in enumerate(accounts):
        result = account_monitoring.run(account, client, logger, run_index=i)
        health_results.append(result)
        print(f"  {account['company']}: score={result['health_score']} "
              f"risk={result['risk_level']}")

    # ── Stage 2: Prioritization ────────────────────────────────────
    print(f"\n[Stage 2] Account Prioritization (batch of {len(health_results)})...")
    priority_results = prioritization.run(health_results, client, logger, run_index=0)
    priority_by_id = {p["account_id"]: p for p in priority_results}
    for p in priority_results:
        print(f"  {p['account_id']}: tier={p['priority_tier']} "
              f"escalate={p.get('escalate_to_manager', False)}")

    # Build account lookup
    account_by_id = {a["id"]: a for a in accounts}
    health_by_id  = {r["account_id"]: r for r in health_results}

    # ── Stage 3: Inbound Issue Triage ─────────────────────────────
    print(f"\n[Stage 3] Inbound Issue Triage ({len(issues)} tickets)...")
    triage_results = []
    for i, issue in enumerate(issues):
        result = inbound_triage.run(issue, client, logger, run_index=i)
        triage_results.append(result)
        print(f"  {result['ticket_id']}: {result['urgency']} | "
              f"{result['category']} → {result['suggested_owner']}")
    triage_by_account = {}
    for t in triage_results:
        issue = next((x for x in issues if x["id"] == t["ticket_id"]), None)
        if issue:
            triage_by_account[issue["account_id"]] = t

    # ── Stage 8: Memory / Context Retrieval (runs before stages that need it) ──
    print("\n[Stage 8] Memory / Context Retrieval (RAG queries)...")
    rag_queries = [
        "dashboard performance issues",
        "HIPAA audit log export limits",
        "mobile API rate limits for integration",
        "data sync failure troubleshooting",
        "bulk user import options",
    ]
    rag_results = []
    for i, query in enumerate(rag_queries):
        result = memory_retrieval.run(query, client, logger, run_index=i)
        rag_results.append(result)
        matches = [m["excerpt"][:50] + "..." for m in result.get("top_matches", [])[:1]]
        print(f"  Query: '{query[:40]}' → {matches}")

    # ── Stage 4: Customer Check-in Support ────────────────────────
    # Run for accounts at tier 1-3 (skip tier 4 — healthy, no action needed)
    checkin_accounts = [
        a for a in accounts
        if priority_by_id.get(a["id"], {}).get("priority_tier", 3) <= 3
    ]
    print(f"\n[Stage 4] Customer Check-in Drafts ({len(checkin_accounts)} accounts)...")
    checkin_results = []
    for i, account in enumerate(checkin_accounts):
        pinfo = priority_by_id.get(account["id"], {})
        result = checkin_support.run(account, pinfo, client, logger, run_index=i)
        checkin_results.append(result)
        preview = result["draft"][:80].replace("\n", " ")
        print(f"  {account['company']}: {preview}...")

    # ── Stage 5: Output Quality Review ────────────────────────────
    # Review first check-in draft as a QA sample
    print(f"\n[Stage 5] Output Quality Review (sampling {min(2, len(checkin_results))} outputs)...")
    qr_results = []
    for i, cr in enumerate(checkin_results[:2]):
        account = account_by_id[cr["account_id"]]
        ctx = (f"Company: {account['company']}, MRR: ${account['mrr']:,}, "
               f"Health: {health_by_id[account['id']]['health_score']}/100")
        result = quality_review.run(cr["draft"], ctx, client, logger, run_index=i)
        qr_results.append(result)
        print(f"  {cr['company']}: verdict={result.get('verdict')} "
              f"score={result.get('overall_score')}")

    # ── Stage 6: Targeted Interventions ───────────────────────────
    # Only for critical/high risk accounts (health < 50 or tier 1)
    intervention_accounts = [
        a for a in accounts
        if health_by_id[a["id"]]["health_score"] < 50
        or priority_by_id.get(a["id"], {}).get("priority_tier", 4) == 1
    ]
    print(f"\n[Stage 6] Targeted Interventions ({len(intervention_accounts)} at-risk accounts)...")
    intervention_results = []
    for i, account in enumerate(intervention_accounts):
        result = interventions.run(
            account, health_by_id[account["id"]], client, logger, run_index=i
        )
        intervention_results.append(result)
        preview = result["intervention_plan"][:80].replace("\n", " ")
        print(f"  {account['company']}: {preview}...")

    # ── Stage 7: Escalation ────────────────────────────────────────
    # Trigger for: P1 tickets OR health_score < 35 OR explicit escalation flag
    escalation_triggers = []
    for t in triage_results:
        if t.get("urgency") == "P1" or t.get("needs_escalation"):
            issue = next((x for x in issues if x["id"] == t["ticket_id"]), None)
            if issue and issue["account_id"] in account_by_id:
                escalation_triggers.append({
                    "account": account_by_id[issue["account_id"]],
                    "triage": t,
                    "reason": f"P1 ticket: {t.get('summary', 'critical issue')}",
                })
    for acct in accounts:
        if health_by_id[acct["id"]]["health_score"] < 35:
            if not any(e["account"]["id"] == acct["id"] for e in escalation_triggers):
                escalation_triggers.append({
                    "account": acct,
                    "triage": triage_by_account.get(acct["id"], {}),
                    "reason": f"Health score {health_by_id[acct['id']]['health_score']}/100 — critical threshold",
                })

    print(f"\n[Stage 7] Escalations ({len(escalation_triggers)} triggered)...")
    escalation_results = []
    for i, trigger in enumerate(escalation_triggers[:2]):  # cap at 2 for sample run
        result = escalation.run(
            trigger["account"],
            health_by_id[trigger["account"]["id"]],
            trigger["triage"],
            trigger["reason"],
            client, logger, run_index=i,
        )
        escalation_results.append(result)
        preview = result["escalation_memo"][:80].replace("\n", " ")
        print(f"  {trigger['account']['company']} [{trigger['reason'][:40]}]: {preview}...")

    # ── Stage 9: Evaluation / QA Checks ───────────────────────────
    print("\n[Stage 9] LLM-as-Judge Evaluation (sampling across stages)...")
    eval_samples = [
        {
            "stage": "account_monitoring",
            "output": json.dumps(health_results[0]),
            "context": json.dumps(accounts[0]),
        },
        {
            "stage": "inbound_triage",
            "output": json.dumps(triage_results[0]),
            "context": json.dumps(issues[0]),
        },
        {
            "stage": "interventions",
            "output": intervention_results[0]["intervention_plan"] if intervention_results else "N/A",
            "context": json.dumps(intervention_accounts[0]) if intervention_accounts else "{}",
        },
    ]
    eval_results = []
    for i, sample in enumerate(eval_samples):
        result = evaluation.run(
            sample["stage"], sample["output"], sample["context"],
            client, logger, run_index=i,
        )
        eval_results.append(result)
        print(f"  Stage '{sample['stage']}': verdict={result.get('verdict')} "
              f"score={result.get('overall_score')} "
              f"failure={result.get('failure_mode')}")

    # ── Final report ───────────────────────────────────────────────
    logger.print_summary()
    logger.save("token_usage_report.json")

    print("\nWorkflow complete. All stages executed end-to-end.")
    print("See token_usage_report.json for per-stage token measurements.")


if __name__ == "__main__":
    main()
