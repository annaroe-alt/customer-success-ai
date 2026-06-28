"""
24/7 Real-time Issue Watcher

Polls data/incoming/ for new ticket files and processes each one immediately
via Stage 9 (real-time intake: triage + route). Escalations and churn-risk
tickets are written to outputs/urgent_escalations.csv for immediate CSM action.

Each ticket file is a JSON object with these fields:
  ticket_id, account_id, date_received, issue_summary,
  severity, customer_sentiment, frontline_notes, current_status

Run:
  python watch.py                     # polls every 60 seconds (default)
  python watch.py --interval 30       # poll every 30 seconds
  python watch.py --once              # process queue once and exit (for cron use)

Processed files are moved to data/incoming/processed/ so they are never
double-processed. Files that fail to parse are moved to data/incoming/failed/.
"""
import argparse
import importlib
import json
import shutil
import sys
import time
from pathlib import Path

import config
from models.schemas import AccountContext, SupportTicket
from pipeline.utils import get_logger

logger = get_logger("watch")

INCOMING_DIR   = config.DATA_DIR / "incoming"
PROCESSED_DIR  = INCOMING_DIR / "processed"
FAILED_DIR     = INCOMING_DIR / "failed"

_s1 = importlib.import_module("pipeline.01_account_review")
_s9 = importlib.import_module("pipeline.09_realtime_intake")


def _ensure_dirs() -> None:
    for d in (INCOMING_DIR, PROCESSED_DIR, FAILED_DIR, config.OUTPUTS_DIR):
        d.mkdir(parents=True, exist_ok=True)


def _load_account_contexts() -> dict[str, AccountContext]:
    """Load all account contexts from the data directory (live CRM source in production)."""
    try:
        contexts, _ = _s1.build_account_contexts()
        return {ctx.account_id: ctx for ctx in contexts}
    except Exception as e:
        logger.error(f"Failed to load account contexts: {e}")
        return {}


def _parse_ticket_file(path: Path) -> SupportTicket | None:
    try:
        data = json.loads(path.read_text())
        required = {"ticket_id", "account_id", "date_received", "issue_summary",
                    "severity", "customer_sentiment", "frontline_notes", "current_status"}
        missing = required - set(data.keys())
        if missing:
            logger.error(f"{path.name}: missing fields {missing}")
            return None
        return SupportTicket(**{k: data[k] for k in required})
    except Exception as e:
        logger.error(f"{path.name}: parse error — {e}")
        return None


def process_queue(contexts: dict[str, AccountContext]) -> int:
    """
    Process all .json files in data/incoming/.
    Returns the number of issues processed.
    """
    pending = sorted(INCOMING_DIR.glob("*.json"))
    if not pending:
        return 0

    logger.info(f"Found {len(pending)} file(s) in incoming queue.")
    processed = 0

    for path in pending:
        ticket = _parse_ticket_file(path)
        if ticket is None:
            shutil.move(str(path), str(FAILED_DIR / path.name))
            logger.warning(f"Moved {path.name} to failed/.")
            continue

        ctx = contexts.get(ticket.account_id)
        if ctx is None:
            logger.warning(
                f"{path.name}: unknown account_id={ticket.account_id}. "
                f"Moving to failed/."
            )
            shutil.move(str(path), str(FAILED_DIR / path.name))
            continue

        try:
            _s9.process_inbound_issue(ticket, ctx)
            shutil.move(str(path), str(PROCESSED_DIR / path.name))
            processed += 1
        except Exception as e:
            logger.error(f"{path.name}: processing error — {e}. Moving to failed/.")
            shutil.move(str(path), str(FAILED_DIR / path.name))

    return processed


def run_watcher(interval: int = 60, once: bool = False) -> None:
    """
    Main watcher loop.

    Args:
        interval: Seconds between queue polls.
        once:     If True, process the queue once and exit.
    """
    _ensure_dirs()

    if not config.ANTHROPIC_API_KEY:
        logger.error(
            "ANTHROPIC_API_KEY is not set. "
            "Copy .env.example to .env and add your API key, then retry."
        )
        sys.exit(1)

    logger.info(
        f"Watcher started. Polling data/incoming/ every {interval}s. "
        f"Drop ticket JSON files there to trigger immediate triage + routing."
    )

    # Load account contexts once at startup; reload every hour so fresh data
    # is picked up without a full restart.
    contexts = _load_account_contexts()
    last_ctx_load = time.monotonic()
    CTX_RELOAD_INTERVAL = 3600  # reload account data every hour

    while True:
        # Reload account contexts periodically
        if time.monotonic() - last_ctx_load > CTX_RELOAD_INTERVAL:
            logger.info("Reloading account contexts...")
            contexts = _load_account_contexts()
            last_ctx_load = time.monotonic()

        n = process_queue(contexts)
        if n:
            logger.info(f"Processed {n} issue(s) from queue.")

        if once:
            logger.info("--once flag set. Exiting after single pass.")
            break

        time.sleep(interval)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="24/7 real-time issue watcher")
    parser.add_argument(
        "--interval", type=int, default=60,
        help="Seconds between queue polls (default: 60)",
    )
    parser.add_argument(
        "--once", action="store_true",
        help="Process the queue once and exit (for cron use)",
    )
    args = parser.parse_args()
    run_watcher(interval=args.interval, once=args.once)
