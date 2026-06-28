# Customer Success AI Pipeline

An end-to-end AI workflow that processes a customer success portfolio through seven
sequential stages: account review, prioritization, inbound triage, check-in preparation,
quality review, intervention planning, and routing.

## Requirements

- Python 3.12+
- An Anthropic API key (Claude)

## Setup

```bash
# 1. Clone and enter the repo
git clone <repo-url>
cd customer-success-ai

# 2. Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Add your API key
cp .env.example .env
# Edit .env and set ANTHROPIC_API_KEY=sk-ant-...

# 5. Confirm the data files are in place
ls data/
# accounts.csv  call_notes.csv  junior_outputs.csv  quality_standards.csv
# scheduled_checkins.csv  support_tickets.csv  usage_events.csv
```

## Running the Pipeline

```bash
python main.py
```

All outputs are written to `outputs/`. A log file is written to `logs/pipeline.log`.

## Running Individual Stages

Each pipeline module can be run standalone:

```bash
python -m pipeline.01_account_review
python -m pipeline.02_prioritization
# ... and so on
```

## Project Structure

```
customer-success-ai/
├── data/                   # Input CSVs (7 files)
├── models/
│   └── schemas.py          # Typed dataclasses for all entities
├── pipeline/
│   ├── utils.py            # Logging, Claude client, file I/O helpers
│   ├── 01_account_review.py
│   ├── 02_prioritization.py
│   ├── 03_inbound_triage.py
│   ├── 04_checkin_prep.py
│   ├── 05_quality_review.py
│   ├── 06_intervention_planner.py
│   └── 07_router.py
├── prompts/                # Prompt templates (one per Claude-calling stage)
│   ├── prioritization.txt
│   ├── triage.txt
│   ├── checkin_brief.txt
│   ├── quality_review.txt
│   ├── intervention.txt
│   └── routing.txt
├── outputs/                # JSON and CSV results (written at runtime)
├── logs/                   # pipeline.log (written at runtime)
├── config.py               # Paths, model ID, thresholds
├── main.py                 # Pipeline orchestrator
├── requirements.txt
└── .env.example
```

## Pipeline Stages

| Stage | Module | Claude? | Output |
|---|---|---|---|
| 1 — Account Review | `01_account_review.py` | No | `account_contexts.json` |
| 2 — Prioritization | `02_prioritization.py` | Borderline cases only | `priority_rankings.csv` |
| 3 — Inbound Triage | `03_inbound_triage.py` | Yes (per ticket) | `triage_results.json` |
| 4 — Check-in Prep | `04_checkin_prep.py` | Yes (per check-in) | `checkin_briefs.json` |
| 5 — Quality Review | `05_quality_review.py` | Yes (per output) | `quality_reviews.json` |
| 6 — Intervention Planner | `06_intervention_planner.py` | Yes (per at-risk account) | `intervention_plans.json` |
| 7 — Router | `07_router.py` | Ambiguous accounts only | `routing_decisions.csv` |

## Routing Tracks

| Track | Meaning |
|---|---|
| **Resolve** | Self-contained; CSM can close without external dependencies |
| **Follow-up** | Pending deliverable, monitoring period, or scheduled next step |
| **Escalate** | Requires engineering, product, or executive involvement |

## Configuration

Edit `config.py` to change:
- `MODEL` — Claude model ID
- `MAX_TOKENS` — max response length per Claude call
- `RENEWAL_CRITICAL_DAYS` / `RENEWAL_HIGH_DAYS` / `RENEWAL_MEDIUM_DAYS` — renewal urgency windows
- `HEALTH_DROP_CRITICAL` / `HEALTH_DROP_HIGH` — health score drop thresholds that elevate tier
