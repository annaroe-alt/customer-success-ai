"""
Stage 9 — Evaluation / QA Checks (LLM-as-judge)
Monthly: systematic evaluation of AI output quality across all workflow stages.
Uses Claude Sonnet 4.6 as an independent judge with structured rubric.
"""
import json
from src.claude_client import ClaudeClient

MODEL = "claude-sonnet-4-6"
STAGE = "9_evaluation"

RUBRIC = {
    "account_monitoring": "Is the health score consistent with account signals? Are flags specific and non-generic?",
    "inbound_triage": "Is urgency correctly calibrated? Is suggested owner appropriate? Does SLA match urgency tier?",
    "checkin_support": "Is the email personalized to the account? Does it reference real context? Is the CTA clear?",
    "interventions": "Is the root cause grounded in data? Are the 3 steps specific, named-owner, and measurable?",
    "escalation": "Is the exec summary clear and actionable? Does the stakeholder plan cover all relevant contacts?",
}


def run(stage_name: str, ai_output: str, ground_truth_context: str,
        client: ClaudeClient, logger, run_index: int) -> dict:
    rubric_question = RUBRIC.get(stage_name, "Is the output high quality, accurate, and actionable?")
    prompt = f"""You are an AI systems evaluator for a customer success platform.
Evaluate the following output from the '{stage_name}' stage.

Rubric for this stage:
{rubric_question}

Ground truth context provided to the AI:
{ground_truth_context[:800]}

AI output:
---
{ai_output[:800]}
---

Score each dimension 1-5 and return JSON:
{{
  "stage": "{stage_name}",
  "scores": {{
    "factual_accuracy": 1-5,
    "actionability": 1-5,
    "completeness": 1-5,
    "judgment_quality": 1-5
  }},
  "overall_score": 1-5,
  "verdict": "pass" | "marginal" | "fail",
  "failure_mode": null | "hallucination" | "incomplete" | "wrong_urgency" | "poor_judgment" | "other",
  "evaluator_note": "one sentence observation"
}}

Return valid JSON only, no markdown."""

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
        return {"stage": stage_name, "verdict": "marginal", "overall_score": 3,
                "failure_mode": "parse_error", "evaluator_note": "JSON parse failed"}
