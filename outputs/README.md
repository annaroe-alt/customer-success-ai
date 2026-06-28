# Pipeline Outputs

Each file is written by the corresponding pipeline stage.

| File | Stage | Description |
|---|---|---|
| `account_contexts.json` | 1 — Account Review | Merged view of all data sources per account |
| `priority_rankings.csv` | 2 — Prioritization | Accounts ranked by urgency score with tier and rationale |
| `triage_results.json` | 3 — Inbound Triage | Per-ticket classification, churn risk flags, gap detection |
| `checkin_briefs.json` | 4 — Check-in Prep | Structured CSM briefings for each scheduled check-in |
| `quality_reviews.json` | 5 — Quality Review | Per-standard pass/fail for each junior output plus rewrites |
| `intervention_plans.json` | 6 — Intervention Planner | Action plans for Critical/High accounts and failing outputs |
| `routing_decisions.csv` | 7 — Router | Final track (Resolve / Follow-up / Escalate) per account |
