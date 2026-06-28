"""
Thin wrapper around the claude CLI that provides:
- Real API calls with specified models
- Actual token usage from modelUsage field
- Simple .messages.create()-compatible interface
"""
import subprocess
import json
from dataclasses import dataclass


@dataclass
class Usage:
    input_tokens: int
    output_tokens: int
    cost_usd: float


@dataclass
class Content:
    text: str


@dataclass
class Message:
    content: list
    usage: Usage


class ClaudeClient:
    """Calls the claude CLI to make real Anthropic API requests."""

    def create(self, model: str, prompt: str, max_tokens: int = 500,
               system: str = "") -> Message:
        cmd = [
            "claude", "-p", prompt,
            "--model", model,
            "--output-format", "json",
        ]
        if system:
            cmd += ["--system-prompt", system]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if result.returncode != 0:
            raise RuntimeError(f"claude CLI error: {result.stderr[:200]}")

        data = json.loads(result.stdout)
        if data.get("is_error"):
            raise RuntimeError(f"API error: {data}")

        raw_text = data.get("result", "")

        # Extract token usage for the specified model from modelUsage
        model_usage = data.get("modelUsage", {})
        if model in model_usage:
            u = model_usage[model]
            usage = Usage(
                input_tokens=u["inputTokens"],
                output_tokens=u["outputTokens"],
                cost_usd=u["costUSD"],
            )
        else:
            # Fall back to aggregate usage
            agg = data.get("usage", {})
            usage = Usage(
                input_tokens=agg.get("input_tokens", 0),
                output_tokens=agg.get("output_tokens", 0),
                cost_usd=data.get("total_cost_usd", 0.0),
            )

        return Message(content=[Content(text=raw_text)], usage=usage)


def make_client() -> ClaudeClient:
    return ClaudeClient()
