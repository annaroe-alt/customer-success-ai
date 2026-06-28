"""Shared utilities: logging setup, Claude client, prompt loading."""
import json
import logging
import sys
import time

import anthropic

import config

# Module-level singleton — avoids re-creating the client on every call.
_claude_client: anthropic.Anthropic | None = None


def _get_client() -> anthropic.Anthropic:
    global _claude_client
    if _claude_client is None:
        if not config.ANTHROPIC_API_KEY:
            raise EnvironmentError(
                "ANTHROPIC_API_KEY is not set. Copy .env.example to .env and add your key."
            )
        _claude_client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    return _claude_client


def get_logger(name: str) -> logging.Logger:
    config.LOGS_DIR.mkdir(exist_ok=True)
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    fh = logging.FileHandler(config.LOGS_DIR / "pipeline.log")
    fh.setFormatter(fmt)

    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(fmt)

    logger.addHandler(fh)
    logger.addHandler(ch)
    return logger


def load_prompt(name: str) -> str:
    path = config.PROMPTS_DIR / f"{name}.txt"
    if not path.exists():
        raise FileNotFoundError(f"Prompt template not found: {path}")
    return path.read_text()


_RETRY_DELAYS = [2, 4, 8, 16]
_RETRYABLE = (anthropic.RateLimitError, anthropic.APIConnectionError, anthropic.APITimeoutError)


def call_claude(prompt: str, system: str = "") -> str:
    client = _get_client()
    messages = [{"role": "user", "content": prompt}]
    kwargs: dict = {
        "model": config.MODEL,
        "max_tokens": config.MAX_TOKENS,
        "messages": messages,
    }
    if system:
        kwargs["system"] = system

    last_exc: Exception | None = None
    for attempt, delay in enumerate([0] + _RETRY_DELAYS):
        if delay:
            time.sleep(delay)
        try:
            response = client.messages.create(**kwargs)
            return response.content[0].text.strip()
        except _RETRYABLE as e:
            last_exc = e
            logging.getLogger("utils").warning(
                f"Claude API transient error (attempt {attempt + 1}): {e}. "
                f"{'Retrying...' if delay < _RETRY_DELAYS[-1] else 'No more retries.'}"
            )
        except anthropic.APIStatusError as e:
            raise  # non-retryable HTTP errors (4xx except 429)

    raise RuntimeError(f"Claude API failed after {len(_RETRY_DELAYS) + 1} attempts") from last_exc


def save_json(data: list | dict, filename: str) -> None:
    config.OUTPUTS_DIR.mkdir(exist_ok=True)
    path = config.OUTPUTS_DIR / filename
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def save_csv_from_dicts(rows: list[dict], filename: str) -> None:
    import pandas as pd
    config.OUTPUTS_DIR.mkdir(exist_ok=True)
    pd.DataFrame(rows).to_csv(config.OUTPUTS_DIR / filename, index=False)
