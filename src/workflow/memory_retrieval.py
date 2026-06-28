"""
Stage 8 — Memory / Context Retrieval
Simulates a RAG retrieval pipeline: given a query, uses Haiku to rank and
return relevant knowledge base chunks. In production this uses
text-embedding-3-small (OpenAI) for vector search; this module models
the prompt token cost of the re-ranking and chunk assembly step.
"""
import json
from src.claude_client import ClaudeClient

MODEL = "claude-haiku-4-5-20251001"
STAGE = "8_memory_retrieval"

KNOWLEDGE_CHUNKS = [
    "Data sync feature runs a nightly cron job; known latency issues occur under heavy DB load.",
    "HIPAA audit log API has a default 500-record page limit per export request; use pagination param.",
    "Mobile API rate limit: 1,000 requests/hour on Standard plan, 5,000/hour on Enterprise plan.",
    "Dashboard performance degradation reported Q1 2026 — root cause: unindexed query in v2.4 (patched v2.5).",
    "Bulk CSV user import is on the product roadmap for Q3 2026 per the June product announcement.",
    "SLA policy: P1 = 1-hour response, 4-hour resolution during business hours.",
    "Compliance module supports SOC2 Type II, HIPAA, and PCI-DSS natively.",
    "Renewal pricing is typically locked 90 days before contract end; escalate to AE for exceptions.",
]


def run(query: str, client: ClaudeClient, logger, run_index: int) -> dict:
    chunks_text = "\n".join(f"{i+1}. {c}" for i, c in enumerate(KNOWLEDGE_CHUNKS))
    prompt = f"""You are a knowledge retrieval system. Identify the most relevant entries for this query.

Query: {query}

Knowledge base:
{chunks_text}

Return JSON with the top 2 matches:
{{
  "query": "{query}",
  "top_matches": [
    {{"rank": 1, "chunk_id": <1-8>, "relevance": "high"|"medium", "excerpt": "<full chunk text>"}},
    {{"rank": 2, "chunk_id": <1-8>, "relevance": "high"|"medium", "excerpt": "<full chunk text>"}}
  ]
}}

Return valid JSON only, no markdown."""

    response = client.create(model=MODEL, prompt=prompt, max_tokens=250)
    logger.log(
        stage=STAGE, model=MODEL, run_index=run_index,
        input_tokens=response.usage.input_tokens,
        output_tokens=response.usage.output_tokens,
    )
    raw = response.content[0].text.strip().strip("```json").strip("```").strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"query": query, "top_matches": []}
