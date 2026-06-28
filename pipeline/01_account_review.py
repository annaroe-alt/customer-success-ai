"""
Stage 1 — Account Review
Loads all 7 CSVs and merges them by account_id into AccountContext objects.
Writes account_contexts.json to outputs/.
"""
import json
import pandas as pd

import config
from models.schemas import (
    Account, UsageSnapshot, SupportTicket, CallNote,
    CheckIn, JuniorOutput, QualityStandard, AccountContext,
)
from pipeline.utils import get_logger, save_json

logger = get_logger("01_account_review")


def load_accounts() -> dict[str, Account]:
    df = pd.read_csv(config.DATA_DIR / "accounts.csv")
    accounts = {}
    for _, row in df.iterrows():
        a = Account(
            account_id=str(row["account_id"]),
            account_name=str(row["account_name"]),
            segment=str(row["segment"]),
            contract_value=int(row["contract_value"]),
            renewal_date=str(row["renewal_date"]),
            csm_owner=str(row["csm_owner"]),
            current_health_score=int(row["current_health_score"]),
            previous_health_score=int(row["previous_health_score"]),
            product_usage_trend=str(row["product_usage_trend"]),
            support_ticket_count_30d=int(row["support_ticket_count_30d"]),
            nps_score=int(row["nps_score"]),
            expansion_signal=str(row["expansion_signal"]),
            last_contact_date=str(row["last_contact_date"]),
            notes=str(row["notes"]),
        )
        accounts[a.account_id] = a
    logger.info(f"Loaded {len(accounts)} accounts.")
    return accounts


def load_usage_events() -> dict[str, list[UsageSnapshot]]:
    df = pd.read_csv(config.DATA_DIR / "usage_events.csv")
    snapshots: dict[str, list[UsageSnapshot]] = {}
    for _, row in df.iterrows():
        s = UsageSnapshot(
            account_id=str(row["account_id"]),
            event_date=str(row["event_date"]),
            active_users=int(row["active_users"]),
            key_feature_users=int(row["key_feature_users"]),
            login_frequency=str(row["login_frequency"]),
            usage_trend=str(row["usage_trend"]),
            notable_change=str(row["notable_change"]),
        )
        snapshots.setdefault(s.account_id, []).append(s)
    logger.info(f"Loaded usage events for {len(snapshots)} accounts.")
    return snapshots


def load_tickets() -> dict[str, list[SupportTicket]]:
    df = pd.read_csv(config.DATA_DIR / "support_tickets.csv")
    tickets: dict[str, list[SupportTicket]] = {}
    for _, row in df.iterrows():
        t = SupportTicket(
            ticket_id=str(row["ticket_id"]),
            account_id=str(row["account_id"]),
            date_received=str(row["date_received"]),
            issue_summary=str(row["issue_summary"]),
            severity=str(row["severity"]),
            customer_sentiment=str(row["customer_sentiment"]),
            frontline_notes=str(row["frontline_notes"]),
            current_status=str(row["current_status"]),
        )
        tickets.setdefault(t.account_id, []).append(t)
    logger.info(f"Loaded tickets for {len(tickets)} accounts.")
    return tickets


def load_call_notes() -> dict[str, CallNote]:
    df = pd.read_csv(config.DATA_DIR / "call_notes.csv")
    notes: dict[str, CallNote] = {}
    for _, row in df.iterrows():
        n = CallNote(
            account_id=str(row["account_id"]),
            call_date=str(row["call_date"]),
            participants=str(row["participants"]),
            summary=str(row["summary"]),
            customer_goal=str(row["customer_goal"]),
            risk_or_blocker=str(row["risk_or_blocker"]),
            follow_up_items=str(row["follow_up_items"]),
        )
        # Keep the most recent note per account
        if n.account_id not in notes or n.call_date > notes[n.account_id].call_date:
            notes[n.account_id] = n
    logger.info(f"Loaded call notes for {len(notes)} accounts.")
    return notes


def load_checkins() -> dict[str, CheckIn]:
    df = pd.read_csv(config.DATA_DIR / "scheduled_checkins.csv")
    checkins: dict[str, CheckIn] = {}
    for _, row in df.iterrows():
        c = CheckIn(
            checkin_id=str(row["checkin_id"]),
            account_id=str(row["account_id"]),
            scheduled_date=str(row["scheduled_date"]),
            checkin_type=str(row["checkin_type"]),
            priority=str(row["priority"]),
            topics_to_cover=str(row["topics_to_cover"]),
        )
        checkins[c.account_id] = c
    logger.info(f"Loaded check-ins for {len(checkins)} accounts.")
    return checkins


def load_junior_outputs() -> dict[str, list[JuniorOutput]]:
    df = pd.read_csv(config.DATA_DIR / "junior_outputs.csv")
    outputs: dict[str, list[JuniorOutput]] = {}
    for _, row in df.iterrows():
        o = JuniorOutput(
            output_id=str(row["output_id"]),
            account_id=str(row["account_id"]),
            output_type=str(row["output_type"]),
            draft_text=str(row["draft_text"]),
            intended_customer_action=str(row["intended_customer_action"]),
            quality_standard_ids=[s.strip() for s in str(row["quality_standard_ids"]).split(";")],
        )
        outputs.setdefault(o.account_id, []).append(o)
    logger.info(f"Loaded junior outputs for {len(outputs)} accounts.")
    return outputs


def load_quality_standards() -> dict[str, QualityStandard]:
    df = pd.read_csv(config.DATA_DIR / "quality_standards.csv")
    standards: dict[str, QualityStandard] = {}
    for _, row in df.iterrows():
        s = QualityStandard(
            standard_id=str(row["standard_id"]),
            standard_name=str(row["standard_name"]),
            description=str(row["description"]),
        )
        standards[s.standard_id] = s
    logger.info(f"Loaded {len(standards)} quality standards.")
    return standards


def build_account_contexts() -> tuple[list[AccountContext], dict[str, QualityStandard]]:
    from pipeline.utils import StageStats
    stats = StageStats("01_account_review")

    accounts = load_accounts()
    usage = load_usage_events()
    tickets = load_tickets()
    call_notes = load_call_notes()
    checkins = load_checkins()
    junior_outputs = load_junior_outputs()
    quality_standards = load_quality_standards()

    if not accounts:
        raise RuntimeError("accounts.csv loaded 0 accounts — cannot continue.")

    contexts = []
    for account_id, account in accounts.items():
        ctx = AccountContext(
            account=account,
            usage_snapshots=sorted(usage.get(account_id, []), key=lambda s: s.event_date),
            tickets=tickets.get(account_id, []),
            call_note=call_notes.get(account_id),
            checkin=checkins.get(account_id),
            junior_outputs=junior_outputs.get(account_id, []),
        )
        contexts.append(ctx)

        if not ctx.usage_snapshots:
            stats.warn(f"{account_id}: no usage events found")
        if ctx.call_note is None:
            stats.warn(f"{account_id}: no call note (may be expected for low-touch accounts)")
        if ctx.tickets and ctx.checkin is None:
            stats.warn(f"{account_id}: has open tickets but no scheduled check-in (gap account)")
        stats.ok()

    # Persist a serialisable summary for downstream inspection
    serialised = []
    for ctx in contexts:
        serialised.append({
            "account_id": ctx.account_id,
            "account_name": ctx.account_name,
            "segment": ctx.account.segment,
            "contract_value": ctx.account.contract_value,
            "renewal_date": ctx.account.renewal_date,
            "csm_owner": ctx.account.csm_owner,
            "current_health_score": ctx.account.current_health_score,
            "previous_health_score": ctx.account.previous_health_score,
            "product_usage_trend": ctx.account.product_usage_trend,
            "nps_score": ctx.account.nps_score,
            "expansion_signal": ctx.account.expansion_signal,
            "notes": ctx.account.notes,
            "usage_snapshots": [
                {"date": s.event_date, "active_users": s.active_users,
                 "key_feature_users": s.key_feature_users, "trend": s.usage_trend}
                for s in ctx.usage_snapshots
            ],
            "open_ticket_count": len(ctx.tickets),
            "tickets": [
                {"ticket_id": t.ticket_id, "severity": t.severity,
                 "summary": t.issue_summary, "sentiment": t.customer_sentiment}
                for t in ctx.tickets
            ],
            "has_call_note": ctx.call_note is not None,
            "has_checkin": ctx.checkin is not None,
            "junior_output_count": len(ctx.junior_outputs),
        })

    save_json(serialised, "account_contexts.json")
    stats.summary(logger)
    logger.info(f"Built {len(contexts)} AccountContext objects. Saved account_contexts.json.")
    return contexts, quality_standards


if __name__ == "__main__":
    ok = build_account_contexts()
    print(f"Built {len(ok[0])} contexts, {len(ok[1])} quality standards.")
