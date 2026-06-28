"""
Stage 11 — Follow-up Tracker
Reads all tracked follow-up items from data/followup_items.csv, applies
overdue detection, and returns open items grouped by account — ready to
be surfaced in the next check-in prep brief for continuity.

Also marks items as overdue when their due_date has passed, writing the
updated statuses back to followup_items.csv. No Claude call needed —
this is deterministic data management.

Writes outputs/followup_status.csv with a per-item status report.
"""
import csv
from datetime import date, datetime
from pathlib import Path

import config
from models.schemas import FollowUpItem
from pipeline.utils import get_logger, save_csv_from_dicts, StageStats

logger = get_logger("11_followup_tracker")

FOLLOWUPS_FILE = config.DATA_DIR / "followup_items.csv"
FOLLOWUP_FIELDS = [
    "item_id", "account_id", "source_checkin_id",
    "description", "owner", "due_date", "status", "completed_date",
]


def load_all_followups() -> list[FollowUpItem]:
    if not FOLLOWUPS_FILE.exists():
        return []
    items = []
    with open(FOLLOWUPS_FILE, newline="") as f:
        for row in csv.DictReader(f):
            items.append(FollowUpItem(
                item_id=row["item_id"],
                account_id=row["account_id"],
                source_checkin_id=row["source_checkin_id"],
                description=row["description"],
                owner=row["owner"],
                due_date=row["due_date"],
                status=row["status"],
                completed_date=row.get("completed_date", ""),
            ))
    return items


def _apply_overdue(items: list[FollowUpItem]) -> list[FollowUpItem]:
    today = date.today()
    updated = []
    for it in items:
        if it.status == "open" and it.due_date:
            try:
                due = datetime.strptime(it.due_date, "%Y-%m-%d").date()
                if due < today:
                    it.status = "overdue"
            except ValueError:
                pass
        updated.append(it)
    return updated


def _write_followups(items: list[FollowUpItem]) -> None:
    with open(FOLLOWUPS_FILE, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FOLLOWUP_FIELDS)
        w.writeheader()
        for it in items:
            w.writerow({
                "item_id": it.item_id,
                "account_id": it.account_id,
                "source_checkin_id": it.source_checkin_id,
                "description": it.description,
                "owner": it.owner,
                "due_date": it.due_date,
                "status": it.status,
                "completed_date": it.completed_date,
            })


def mark_completed(item_id: str) -> bool:
    """Mark a single follow-up item as completed. Returns True if found."""
    items = load_all_followups()
    found = False
    today = date.today().isoformat()
    for it in items:
        if it.item_id == item_id and it.status != "completed":
            it.status = "completed"
            it.completed_date = today
            found = True
            logger.info(f"Marked {item_id} as completed.")
            break
    if found:
        _write_followups(items)
    else:
        logger.warning(f"Item {item_id} not found or already completed.")
    return found


def get_open_items_for_account(account_id: str) -> list[FollowUpItem]:
    """Return current open/overdue follow-up items for one account."""
    items = _apply_overdue(load_all_followups())
    return [it for it in items if it.account_id == account_id and it.status in ("open", "overdue")]


def run_followup_tracker() -> dict[str, list[FollowUpItem]]:
    """
    Apply overdue detection to all items, persist updates, write a status
    report, and return a map of account_id → open/overdue items.
    """
    stats = StageStats("11_followup_tracker")
    all_items = load_all_followups()

    if not all_items:
        logger.info("No follow-up items found — tracker produced no output.")
        return {}

    all_items = _apply_overdue(all_items)
    _write_followups(all_items)

    open_items   = [it for it in all_items if it.status in ("open", "overdue")]
    overdue      = [it for it in all_items if it.status == "overdue"]
    completed    = [it for it in all_items if it.status == "completed"]

    logger.info(
        f"Follow-up tracker: {len(all_items)} total items — "
        f"{len(open_items)} open, {len(overdue)} overdue, {len(completed)} completed."
    )

    if overdue:
        logger.warning(f"OVERDUE items ({len(overdue)}):")
        for it in overdue:
            logger.warning(f"  [{it.account_id}] {it.description} — due {it.due_date}, owner: {it.owner}")

    rows = [
        {
            "item_id": it.item_id,
            "account_id": it.account_id,
            "source_checkin_id": it.source_checkin_id,
            "description": it.description,
            "owner": it.owner,
            "due_date": it.due_date,
            "status": it.status,
            "completed_date": it.completed_date,
        }
        for it in all_items
    ]
    save_csv_from_dicts(rows, "followup_status.csv")
    logger.info("Saved followup_status.csv.")

    # Group open items by account for Stage 4 (check-in prep) to consume
    by_account: dict[str, list[FollowUpItem]] = {}
    for it in open_items:
        by_account.setdefault(it.account_id, []).append(it)

    stats.ok()
    stats.summary(logger)
    return by_account
