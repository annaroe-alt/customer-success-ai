# AI System Design Assessment
## Submission C — AI Build Process Memo

---

## Candidate Information

| Field | Value |
|---|---|
| **Name** | Anna Roe |
| **Email** | anna.roe@crowley.k12.tx.us |
| **Date submitted** | 2026-06-28 |
| **Starter project version** | claude/ai-system-design-assessment-dt0l2d |
| **Other AI tools used, if any** | None |

---

## 1. Workflow Decomposition

**Major workflow stages implemented:**

I broke the customer success workflow into 8 sequential stages (Stages 0–7):

- **Stage 0 — Input Validation:** Validate all 7 input CSVs before any processing begins (column presence, nulls, enum values, referential integrity across account IDs, quality standard references, numeric range checks).
- **Stage 1 — Account Review:** Load and merge all 7 CSVs into unified `AccountContext` objects keyed by `account_id`. Flag gap accounts (tickets present but no scheduled check-in).
- **Stage 2 — Prioritization:** Deterministic urgency scoring (0–80+ points across renewal window, health drop, usage trend, ticket volume/severity, NPS, expansion signal) → tier assignment (Critical / High / Medium / Low / Monitor). Claude is called only for borderline scores (within 5 points of a tier boundary) to confirm or adjust the tier.
- **Stage 3 — Inbound Triage:** Per-ticket Claude classification: issue type (technical / enablement / strategic / churn-risk), churn risk flag, churn risk reason, recommended action. Gap accounts (ticket but no check-in) are flagged for immediate addition to the check-in queue.
- **Stage 4 — Check-in Prep:** Per-scheduled-check-in Claude brief generation. Output is structured markdown with five required sections: Situation Summary, Open Risks, Committed Follow-ups, Recommended Talking Points, Suggested Ask.
- **Stage 5 — Quality Review:** Per-junior-CSM-output Claude evaluation against the quality standards referenced in that output record. Returns pass/fail per standard and a rewrite suggestion if any standard fails.
- **Stage 6 — Intervention Planner:** Selective Claude call only for accounts that are Critical or High priority, or where any junior output failed quality review. Generates a concrete 7-section intervention plan.
- **Stage 7 — Router:** Rule-based routing first (Critical tier or escalation keywords → Escalate; Low/Monitor with no tickets or follow-ups → Resolve); Claude decides ambiguous cases and returns structured track, reason, and next step.

**Why I structured the workflow this way:**

The stages mirror the actual daily CSM workflow: validate data integrity first so downstream stages don't silently fail on bad input; merge context once so every later stage shares a consistent view; prioritize accounts before triaging tickets so routing decisions can reference tier; quality-review junior outputs before intervention planning so the plan can explicitly address any output failures. The dependency graph (prioritization + triage + QA → intervention → routing) reflects real operational sequencing.

**Parts prioritized first:**

I prioritized Stage 0 (validation) and Stage 2 (prioritization) first because they gate the rest of the pipeline. Getting the scoring formula and tier boundaries right before writing any Claude prompts meant I could test the deterministic path without API calls. Stage 7 (routing) was the last stage implemented because it depends on outputs from all previous stages.

**Intentional simplifications for the assessment:**

- Used CSV flat files rather than a database; no incremental processing — the pipeline reruns from scratch each time.
- Loaded only the most recent call note per account (latest by `call_date`) rather than building a full call history.
- Quality review evaluates outputs against the quality standards already tagged in the CSV record rather than dynamically selecting applicable standards from a catalogue.
- No authentication, multi-tenancy, or CSM-specific access controls.

---

## 2. Claude Code Usage Summary

**What I asked Claude Code to help with:**

I used Claude Code as a primary build partner throughout. I asked it to: scaffold the full project structure (directory layout, `models/schemas.py`, `pipeline/utils.py`, `config.py`, `main.py`); implement each of the 8 pipeline stages as Python modules; write all 6 prompt files; implement token tracking and cost calculation; add per-stage `__main__` blocks with mocked Claude calls for local testing; and add the optimized model-routing branch (`claude/ai-system-cost-optimization-evquyo`) that routes short structured-output stages to Haiku and long-form stages to Sonnet.

**Which parts of the codebase Claude Code created or modified:**

Claude Code created essentially the entire codebase from scratch: all 8 pipeline modules, `models/schemas.py` (14 dataclasses), `pipeline/utils.py` (logging, retry logic, Claude client singleton, StageStats, enum validation, prompt loader), `config.py`, `main.py`, all 6 prompt `.txt` files, `requirements.txt`, `.env.example`, and `README.md`. On the cost-optimization branch, Claude Code added per-stage model routing, token budget constants, and cost accumulation logic.

**Where I relied on Claude Code heavily:**

- Scaffolding the full module structure before any logic was written
- Writing the 6 structured prompt templates and the response-parsing code that consumes them
- Implementing retry logic with exponential backoff and distinguishing transient vs. non-transient API errors
- Generating the `__main__` test blocks with mock `call_claude()` replacements

**Where I made decisions myself:**

- The specific point values in the prioritization scoring formula (e.g., 40 pts for ≤30-day renewal, 25 pts for health drop ≥20) and the tier boundary thresholds (80/55/35/15)
- The 5-point borderline margin that triggers Claude validation in Stage 2
- The choice of a hybrid routing approach in Stage 7: deterministic rules first, Claude only for ambiguous cases (rather than calling Claude for every account)
- The decision to selectively call Claude in Stage 6 (only Critical/High or failed-QA accounts) rather than generating an intervention plan for every account — driven by cost containment
- The model split on the optimization branch: Haiku for stages 2, 3, and 7 (short structured outputs), Sonnet for stages 4, 5, and 6 (long-form markdown)
- The token budget split: 256 max tokens for structured short responses, 1024 for markdown outputs

**How I reviewed or tested Claude Code output before accepting it:**

I read each generated file against the spec before accepting it. For the prioritization module, I manually traced the scoring formula with sample account values and verified tier assignments matched my intent. For each prompt file, I reviewed the format constraints against the parsing code that would consume the response — if the prompt said `TIER: <tier>` but the parser expected a different key name, I caught that before running. I ran the `__main__` test block on each module after implementation to verify the mock path executed without errors. On the cost-optimization branch, I verified the cost math by computing expected cost for a sample token count against the configured per-million rates.

---

## 3. Key Prompts or Instructions

| Prompt / instruction summary | Goal | Claude Code output | Accepted / revised / rejected | Why |
|---|---|---|---|---|
| "Scaffold the full project directory: config, models/schemas.py with dataclasses for all entities, pipeline/utils.py with logging and Claude client, and main.py that runs 8 stages in order." | Establish project structure before any logic | Full directory tree, all stub modules, working imports, dataclasses for 14 entities | Accepted with minor revision | Renamed two dataclass fields to better match the CSV column names in the spec |
| "Implement the prioritization scoring formula: renewal urgency, health drop, usage trend, ticket volume and severity, NPS, expansion signal — assign tier boundaries Critical/High/Medium/Low/Monitor. Call Claude only for borderline scores within 5 points of a boundary." | Stage 2 rule-based scoring with selective Claude fallback | Complete `02_prioritization.py` with scoring function, tier assignment, and borderline Claude call | Revised | Adjusted the point values on the scoring dimensions and the tier boundary thresholds to match my design intent — Claude Code's initial values were reasonable but not what I had specified |
| "Write all 6 prompt files. Each must use structured format constraints so the response is machine-parseable without heuristics. Prompts: borderline tier confirmation, ticket triage, check-in brief, quality review, intervention plan, routing decision." | Parseable Claude responses for all 6 AI-driven stages | 6 `.txt` prompt files with format instructions and output schema embedded in the prompt text | Revised for 2 prompts | The triage and routing prompts initially asked for free-text explanations; I revised them to require strict `KEY: value` line formats that match the parser's expected keys |
| "Implement Stage 7 router: check escalation keywords and Critical tier first; check Low/Monitor with clean state for Resolve; send everything else to Claude with a structured 3-line response." | Hybrid deterministic + AI routing that avoids unnecessary Claude calls | Complete `07_router.py` with keyword list, tier checks, Claude call, and response parser | Accepted | Logic and keyword list matched my design |
| "Add a cost-optimization branch: route stages 2, 3, 7 to claude-haiku-4-5-20251001 (max 256 tokens) and stages 4, 5, 6 to claude-sonnet-4-6 (max 1024 tokens). Track tokens and USD cost per call and log total at pipeline end." | Reduce Claude spend while preserving output quality where it matters | Updated `config.py`, updated `call_claude()` signature, cost accumulation in `_TokenUsage`, updated stage calls with model/max_tokens args, summary cost log in `main.py` | Accepted with one revision | Added a `calls` counter to `_TokenUsage` to track the number of API calls alongside token counts |
| "Add `__main__` test blocks to each pipeline module (01–07) that mock `call_claude()` and run the stage logic end-to-end without an API key." | Local smoke-testing without consuming API credits | `if __name__ == "__main__"` blocks in each module that patch `call_claude` and print stage summary counts | Accepted | All blocks ran cleanly and surfaced one parsing bug in Stage 5 (missing strip on standard ID) that I then fixed |

---

## 4. Debugging and Iteration

| Issue | How I found it | How I fixed it | Claude Code's role |
|---|---|---|---|
| Quality review parser failed to match standard IDs because Claude returned `QS-001:` with a trailing space, but the parser split on `: ` and expected an exact `QS-001` match | Running the Stage 5 `__main__` mock block and seeing zero standards matched | Added `.strip()` to the parsed standard ID before lookup | Claude Code identified the fix when I described the symptom; I accepted the one-line change |
| Prioritization scoring for expansion-signal discount used `if expansion == "high"` but the CSV column used capitalized values (`High`) — accounts with expansion signal were not receiving the discount | Manual trace of the scoring function against a sample account with `expansion_signal = "High"` | Changed all enum comparisons in the scoring function to `.lower()` before comparing | I made the fix; Claude Code had already applied `.lower()` in other enum checks in the same file, so I applied the same pattern |
| Stage 6 intervention planner was called for every account, not just Critical/High or failed-QA accounts — this would blow the token budget in production | Code review of `06_intervention_planner.py` before running the pipeline | Added a `should_plan` guard: only proceed if `priority_result.tier in ("Critical", "High")` or any QA result has `overall_passed == False` | Prompted Claude Code to add the guard with my exact condition; it implemented it correctly on the first try |
| `call_claude()` raised an unhandled `KeyError` when the retry loop exhausted all attempts because the final exception was swallowed | Running the full pipeline with an intentionally invalid API key to test error paths | Restructured the retry loop to re-raise the last exception after all retries are exhausted; downstream stages catch it and log the error without halting the pipeline | Claude Code implemented the fix; I verified the error-handling path manually |

---

## 5. Design Decisions

**Workflow structure:**

I chose a sequential 8-stage pipeline with in-memory `AccountContext` objects rather than a microservices or event-driven architecture. For an assessment, this is the right tradeoff: easy to run, easy to read, easy to validate. Every stage sees the same shared context object without serialization overhead. The pipeline fails fast on validation errors in Stage 0 rather than producing silently corrupt outputs in later stages.

**Routing and escalation logic:**

Stage 7 uses deterministic rules before calling Claude because the escalation and resolve cases are binary and rule-expressible. Calling Claude for an account that has `tier = Critical` or contains "sso fail" in its ticket notes adds latency and cost without improving accuracy. Claude is reserved for the genuinely ambiguous mid-tier accounts where context — call notes, ticket trends, open follow-ups — actually changes the routing decision. This hybrid approach is cheaper, faster, and more auditable than a pure-LLM router.

**Prompt design:**

All 6 prompts use strict line-key format constraints (`KEY: value`) or labeled markdown section headers. I made this decision to avoid brittle string parsing. If Claude returns a free-text paragraph, there is no reliable way to extract structured fields without another LLM call. By requiring `TRACK: <value>` on its own line, the parser can use a simple split and strip — it either finds the key or it doesn't, and the fallback behavior is defined. The check-in brief and intervention plan prompts use markdown section headers (`## Section Name`) because the outputs are human-readable and the format expectations are looser.

**Evaluation and quality checks:**

Stage 5 evaluates each junior output against the quality standards explicitly tagged in that output's `quality_standard_ids` CSV field rather than asking Claude to select applicable standards dynamically. This is a deliberate simplification: it keeps the evaluation deterministic (same standards are always evaluated for the same output), avoids an additional classification step, and prevents Claude from omitting standards it deems inapplicable. The tradeoff is that the standard selection must be correct at data entry time.

**Token and cost tracking:**

I track tokens at the `call_claude()` level using `response.usage.input_tokens` and `response.usage.output_tokens` from the API response object. This is more accurate than estimating from prompt character count because the API returns actual billed tokens. Cost is computed per call using model-specific per-million-token rates and accumulated in a global `_TokenUsage` singleton, then logged at pipeline completion.

**Tradeoffs made to stay within the $50,000/year token budget:**

On the optimization branch, I made three cost-containment decisions:
1. Route stages 2, 3, and 7 (short structured outputs) to `claude-haiku-4-5-20251001` ($1/$5 per million vs. Sonnet's $3/$15). These stages need accurate parsing of 2–4 line responses, not long-form reasoning.
2. Cap short-stage responses at 256 max tokens and long-stage responses at 1024 max tokens. The original global 2048 cap was wasteful for stages where the correct output is 3 lines.
3. Gate Stage 6 (intervention planner) to only Critical/High accounts and failed-QA outputs. For a portfolio of 50 accounts, this could reduce intervention-plan calls by 60–70% compared to running for every account.

**Simplifications made for the assessment:**

- No caching: repeated runs re-call Claude even for unchanged inputs. In production, I would cache Claude responses keyed on a hash of the input context.
- No parallelism: stages process items sequentially. In production, per-ticket and per-check-in Claude calls would run concurrently with a rate-limiter.
- No streaming: outputs are fully buffered. Long intervention plans and check-in briefs would benefit from streaming for time-to-first-token in a UI context.

---

## 6. Validation

**How I ran the workflow:**

I ran each stage individually using its `__main__` block with a mocked `call_claude()` function that returns a valid fixture response. This let me verify the parsing and data-flow logic without consuming API credits. I also ran `python main.py` end-to-end against the sample data CSVs to produce real outputs and inspect them.

**What outputs I inspected:**

- `outputs/priority_rankings.csv`: Verified tier assignments for accounts I had manually scored, and verified that borderline accounts triggered a Claude call (logged in `pipeline.log`).
- `outputs/triage_results.json`: Spot-checked that issue_type, churn_risk, and recommended_action fields were populated and correctly typed for several tickets.
- `outputs/checkin_briefs.json`: Read the `brief_text` markdown for a sample check-in to confirm all 5 required section headers were present.
- `outputs/quality_reviews.json`: Verified that `standard_results` contained a pass/fail entry per tagged standard ID, and that `rewrite_suggestion` was populated when `overall_passed` was `False`.
- `outputs/intervention_plans.json`: Read a sample plan and verified all 7 sections were present.
- `outputs/routing_decisions.csv`: Verified that Critical-tier accounts routed to Escalate without a Claude call, and that Low/Monitor clean accounts routed to Resolve.

**How I verified representative end-to-end runs:**

I constructed three representative test accounts in the CSV data: one clearly Critical (renewal in 15 days, health drop of 30, declining usage, two high-severity tickets), one clearly Monitor (renewal in 200 days, stable usage, no tickets), and one borderline High/Medium (score within 5 points of the 55-boundary). I verified that the Critical account escalated, the Monitor account resolved without a Claude call, and the borderline account triggered a Claude confirmation prompt logged in `pipeline.log`.

**How I checked token and cost calculations:**

I added a log statement to print `input_tokens`, `output_tokens`, and computed cost for each Claude call during development. I manually verified one call: a triage prompt with a known character count, Haiku model at $1/$5 per million, max 256 output tokens. The per-call cost matched my hand calculation. The pipeline summary log prints total tokens and estimated cost, which I cross-checked against the sum of individual call logs.

**Tests, smoke checks, and validation logic added:**

- `__main__` blocks in all 7 processing modules (01–07) with mock `call_claude()` returning fixture responses
- Stage 0 validation module (`00_validate_inputs.py`) with explicit checks for file presence, column names, null critical fields, enum values, account ID consistency, and numeric ranges
- `StageStats` tracker in `pipeline/utils.py` that records success/failure/warning counts per stage and logs a summary at stage completion
- `validate_claude_enum()` utility for case-insensitive enum matching with a safe default fallback when Claude returns an unexpected value

---

## 7. What I Would Improve With More Time

**Caching:** Add a response cache keyed on a hash of the prompt context (account snapshot hash + stage name). For accounts that haven't changed since the last run, return the cached Claude response instead of re-calling. This would reduce both cost and latency for incremental daily runs.

**Parallelism:** Stages 3, 4, 5, and 6 process one item at a time sequentially. In production with 500+ accounts and thousands of tickets, these would run as concurrent async tasks with a token-bucket rate limiter against the Anthropic API rate limits.

**Evaluation harness:** Build a small offline evaluator for each prompt: given 20–30 labeled examples (expected tier, expected track, expected pass/fail), compute accuracy and log regression when prompts change. Right now I validate prompts by reading sample outputs — that doesn't scale.

**Confidence scores and human review queue:** Stage 7 currently routes each account to exactly one track. In production, I would add a confidence score to Claude's routing response and route low-confidence decisions to a human review queue rather than acting on them automatically.

**Prompt versioning:** Store prompt templates with a version identifier and log which version was used for each Claude call. This makes it possible to A/B test prompt changes and audit past outputs if a prompt is later revised.

**Cost alerting:** Add a hard stop (or at least a warning) if estimated per-run cost exceeds a configurable threshold, so a data spike (e.g., 10x the expected number of tickets) doesn't silently generate a large API bill.

**Streaming for UX:** If this pipeline were exposed through a UI, check-in briefs and intervention plans would benefit from streaming responses to reduce perceived latency for long markdown outputs.

---

## 8. Candidate Confirmation

| Field | Value |
|---|---|
| **Name** | Anna Roe |
| **Signature or typed confirmation** | Anna Roe |
| **Date** | 2026-06-28 |

I confirm that this memo accurately describes how I used Claude Code and any other AI tools while completing this assessment.

---

*Optional Appendix: No additional notes.*
