"""
Stage 5 — Output Quality Review
Samples ~10% of AI outputs weekly for quality scoring.
Uses Claude Sonnet 4.6 to evaluate against a structured rubric.
"""
import json
from src.claude_client import ClaudeClient

MODEL = "claude-sonnet-4-6"
STAGE = "5_quality_review"


def run(output_text: str, account_context: str, client: ClaudeClient,
        logger, run_index: int) -> dict:
    prompt = f"""You are a Customer Success AI quality reviewer.

Account context:
{account_context}

AI-generated output to review:
---
{output_text[:1000]}
---

Score this output on each dimension (1-5):
1. Personalization — references specific account context, not generic
2. Tone — warm and professional, not sycophantic or alarming
3. Accuracy — facts consistent with provided account data
4. Call to action — clear, specific, and low-friction
5. CSM readiness — a CSM could send this without edits

Return JSON:
{{
  "scores": {{"personalization": 1-5, "tone": 1-5, "accuracy": 1-5, "cta": 1-5, "csm_readiness": 1-5}},
  "overall_score": 1.0-5.0,
  "verdict": "pass" | "needs_edit" | "fail",
  "top_strength": "one sentence",
  "top_issue": "one sentence or null",
  "requires_human_review": true or false
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
        return {"verdict": "needs_edit", "overall_score": 3.0,
                "requires_human_review": True, "top_issue": "parse error"}
