"""Shared utilities: logging setup, Claude client, prompt loading."""
import json
import logging
import sys
from pathlib import Path

import anthropic

import config


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


def call_claude(prompt: str, system: str = "") -> str:
    if not config.ANTHROPIC_API_KEY:
        raise EnvironmentError("ANTHROPIC_API_KEY is not set. Copy .env.example to .env and add your key.")
    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    messages = [{"role": "user", "content": prompt}]
    kwargs = {
        "model": config.MODEL,
        "max_tokens": config.MAX_TOKENS,
        "messages": messages,
    }
    if system:
        kwargs["system"] = system
    response = client.messages.create(**kwargs)
    return response.content[0].text.strip()


def save_json(data: list | dict, filename: str) -> None:
    config.OUTPUTS_DIR.mkdir(exist_ok=True)
    path = config.OUTPUTS_DIR / filename
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def save_csv_from_dicts(rows: list[dict], filename: str) -> None:
    import pandas as pd
    config.OUTPUTS_DIR.mkdir(exist_ok=True)
    pd.DataFrame(rows).to_csv(config.OUTPUTS_DIR / filename, index=False)
