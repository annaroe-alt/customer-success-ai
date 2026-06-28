"""
Stage 10 — Check-in Intake
Processes raw post-call notes into a structured intake record immediately
after a check-in completes. Claude extracts decisions, follow-up commitments,
risk updates, and customer sentiment.

Called per check-in as it completes — not as a batch over all accounts.
Writes / appends to data/checkin_intakes.csv (source of truth for follow-up
tracking and continuity in future prep briefs).
"""
import csv
import uuid
from datetime import date
from pathlib import Path

import config
from models.schemas import CheckInIntake, FollowUpItem
from pipeline.utils import get_logger, call_claude, load_prompt, StageStats

logger = get_logger("10_checkin_intake")

INTAKES_FILE = config.DATA_DIR / "checkin_intakes.csv"
FOLLOWUPS_FILE = config.DATA_DIR / "followup_items.csv"

INTAKE_FIELDS = [
    "intake_id", "checkin_id", "account_id", "call_date",
    "topics_covered", "decisions_made", "follow_ups_committed",
    "risks_updated", "customer_sentiment", "csm_notes",
]
FOLLOWUP_FIELDS = [
    "item_id", "account_id", "source_checkin_id",
    "description", "owner", "due_date", "status", "completed_date",
]

_VALID_SENTIMENTS = {"positive", "neutral", "negative"}


def load_open_followups(account_id: str) -> list[FollowUpItem]:
    """Return open follow-up items for an account from the tracking file."""
    if not FOLLOWUPS_FILE.exists():
        return []
    items = []
    with open(FOLLOWUPS_FILE, newline="") as f:
        for row in csv.DictReader(f):
            if row["account_id"] == account_id and row["status"] in ("open", "overdue"):
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


def _format_prior_items(items: list[FollowUpItem]) -> str:
    if not items:
        return "None."
    lines = []
    for it in items:
        lines.append(f"  - [{it.status.upper()}] {it.description} (owner: {it.owner}, due: {it.due_date})")
    return "\n".join(lines)


def _parse_intake_response(
    response: str,
    checkin_id: str,
    account_id: str,
    call_date: str,
) -> tuple[CheckInIntake, list[FollowUpItem]]:
    fields: dict[str, str] = {}
    for line in response.splitlines():
        for key in ("TOPICS_COVERED", "DECISIONS_MADE", "FOLLOW_UPS_COMMITTED",
                    "RISKS_UPDATED", "CUSTOMER_SENTIMENT", "CSM_NOTES"):
            if line.strip().upper().startswith(f"{key}:"):
                fields[key] = line.split(":", 1)[1].strip()
                break

    sentiment = fields.get("CUSTOMER_SENTIMENT", "neutral").lower()
    if sentiment not in _VALID_SENTIMENTS:
        logger.warning(f"{checkin_id}: unexpected sentiment {sentiment!r}, defaulting to 'neutral'")
        sentiment = "neutral"

    intake = CheckInIntake(
        intake_id=f"I-{uuid.uuid4().hex[:8].upper()}",
        checkin_id=checkin_id,
        account_id=account_id,
        call_date=call_date,
        topics_covered=fields.get("TOPICS_COVERED", ""),
        decisions_made=fields.get("DECISIONS_MADE", ""),
        follow_ups_committed=fields.get("FOLLOW_UPS_COMMITTED", "None"),
        risks_updated=fields.get("RISKS_UPDATED", ""),
        customer_sentiment=sentiment,
        csm_notes=fields.get("CSM_NOTES", ""),
    )

    follow_up_items: list[FollowUpItem] = []
    raw_fups = fields.get("FOLLOW_UPS_COMMITTED", "None")
    if raw_fups.strip().lower() != "none":
        today = date.today().isoformat()
        for part in raw_fups.split("|"):
            part = part.strip()
            if not part:
                continue
            segments = [s.strip() for s in part.split("|")]
            # Each segment is "description | owner | due YYYY-MM-DD"
            # After splitting on | above, segments is a list of one (the whole thing was split already)
            # Re-parse: the raw item before splitting by | for each pipe-delimited item
            # Actually the outer split already happened; each `part` is one complete item.
            # Items are pipe-separated at the top level, but each item contains " | owner | due date"
            # So we split each item on " | " (with spaces) to get its three sub-fields.
            sub = [s.strip() for s in part.split(" | ")]
            description = sub[0] if len(sub) > 0 else part
            owner = sub[1] if len(sub) > 1 else "CSM"
            due_raw = sub[2] if len(sub) > 2 else f"due {today}"
            due_date = due_raw.replace("due ", "").strip()
            follow_up_items.append(FollowUpItem(
                item_id=f"FU-{uuid.uuid4().hex[:8].upper()}",
                account_id=account_id,
                source_checkin_id=checkin_id,
                description=description,
                owner=owner,
                due_date=due_date,
                status="open",
            ))

    return intake, follow_up_items


def _append_intake(intake: CheckInIntake) -> None:
    exists = INTAKES_FILE.exists()
    with open(INTAKES_FILE, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=INTAKE_FIELDS)
        if not exists:
            w.writeheader()
        w.writerow({
            "intake_id": intake.intake_id,
            "checkin_id": intake.checkin_id,
            "account_id": intake.account_id,
            "call_date": intake.call_date,
            "topics_covered": intake.topics_covered,
            "decisions_made": intake.decisions_made,
            "follow_ups_committed": intake.follow_ups_committed,
            "risks_updated": intake.risks_updated,
            "customer_sentiment": intake.customer_sentiment,
            "csm_notes": intake.csm_notes,
        })


def _append_followups(items: list[FollowUpItem]) -> None:
    if not items:
        return
    exists = FOLLOWUPS_FILE.exists()
    with open(FOLLOWUPS_FILE, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FOLLOWUP_FIELDS)
        if not exists:
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


def record_intake(
    checkin_id: str,
    account_id: str,
    account_name: str,
    checkin_type: str,
    call_date: str,
    participants: str,
    raw_notes: str,
) -> CheckInIntake:
    """
    Capture and structure a post-call intake record for one check-in.
    Appends to data/checkin_intakes.csv and data/followup_items.csv.
    Returns the structured CheckInIntake.
    """
    stats = StageStats("10_checkin_intake")
    prior_items = load_open_followups(account_id)

    try:
        template = load_prompt("checkin_intake")
        prompt = template.format(
            account_name=account_name,
            account_id=account_id,
            checkin_type=checkin_type,
            call_date=call_date,
            participants=participants,
            raw_notes=raw_notes,
            prior_open_items=_format_prior_items(prior_items),
        )
        response = call_claude(prompt, max_tokens=config.MAX_TOKENS_LONG)
        intake, follow_ups = _parse_intake_response(response, checkin_id, account_id, call_date)
    except Exception as e:
        logger.error(f"Intake failed for {checkin_id}: {e}")
        intake = CheckInIntake(
            intake_id=f"I-{uuid.uuid4().hex[:8].upper()}",
            checkin_id=checkin_id,
            account_id=account_id,
            call_date=call_date,
            topics_covered="",
            decisions_made="",
            follow_ups_committed="None",
            risks_updated="",
            customer_sentiment="neutral",
            csm_notes=f"Intake failed: {e}",
        )
        follow_ups = []
        stats.fail(checkin_id, str(e))

    _append_intake(intake)
    _append_followups(follow_ups)

    if not intake.csm_notes.startswith("Intake failed"):
        stats.ok()
        logger.info(
            f"Intake recorded for {checkin_id} ({account_name}): "
            f"sentiment={intake.customer_sentiment}, "
            f"{len(follow_ups)} follow-up(s) committed."
        )

    stats.summary(logger)
    return intake


def record_intake_batch(
    checkin_records: list[dict],
) -> list[CheckInIntake]:
    """
    Process multiple post-call intakes in sequence.
    Each dict must have: checkin_id, account_id, account_name, checkin_type,
    call_date, participants, raw_notes.
    """
    return [record_intake(**r) for r in checkin_records]
