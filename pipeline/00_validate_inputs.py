"""
Stage 0 — Input Validation
Validates all 7 CSV files before the pipeline runs.
Checks: file presence, required columns, non-empty data,
account_id consistency across sources, and enum field values.
Exits non-zero if any error is found; warnings are non-fatal.
"""
import sys
import pandas as pd

import config
from pipeline.utils import get_logger

logger = get_logger("00_validate_inputs")

# Required columns per file
REQUIRED_COLUMNS: dict[str, list[str]] = {
    "accounts.csv": [
        "account_id", "account_name", "segment", "contract_value", "renewal_date",
        "csm_owner", "current_health_score", "previous_health_score",
        "product_usage_trend", "support_ticket_count_30d", "nps_score",
        "expansion_signal", "last_contact_date", "notes",
    ],
    "usage_events.csv": [
        "account_id", "event_date", "active_users", "key_feature_users",
        "login_frequency", "usage_trend", "notable_change",
    ],
    "support_tickets.csv": [
        "ticket_id", "account_id", "date_received", "issue_summary",
        "severity", "customer_sentiment", "frontline_notes", "current_status",
    ],
    "call_notes.csv": [
        "account_id", "call_date", "participants", "summary",
        "customer_goal", "risk_or_blocker", "follow_up_items",
    ],
    "scheduled_checkins.csv": [
        "checkin_id", "account_id", "scheduled_date", "checkin_type",
        "priority", "topics_to_cover",
    ],
    "junior_outputs.csv": [
        "output_id", "account_id", "output_type", "draft_text",
        "intended_customer_action", "quality_standard_ids",
    ],
    "quality_standards.csv": ["standard_id", "standard_name", "description"],
}

VALID_ENUMS: dict[str, dict[str, set[str]]] = {
    "accounts.csv": {
        "segment": {"SMB", "Mid-Market", "Enterprise"},
        "product_usage_trend": {"growing", "flat", "declining"},
        "expansion_signal": {"low", "medium", "high"},
    },
    "support_tickets.csv": {
        "severity": {"Low", "Medium", "High"},
        "current_status": {"new", "open", "closed", "resolved"},
    },
    "scheduled_checkins.csv": {
        "priority": {"Low", "Medium", "High"},
    },
}


def _load(filename: str) -> pd.DataFrame | None:
    path = config.DATA_DIR / filename
    if not path.exists():
        return None
    try:
        return pd.read_csv(path)
    except Exception as e:
        return None


def validate_inputs() -> bool:
    """
    Returns True if all checks pass (errors=0).
    Warnings are printed but do not cause a False return.
    """
    errors: list[str] = []
    warnings: list[str] = []

    dataframes: dict[str, pd.DataFrame] = {}

    # ── 1. File presence and column checks ────────────────────────────────────
    for filename, required_cols in REQUIRED_COLUMNS.items():
        path = config.DATA_DIR / filename
        if not path.exists():
            errors.append(f"Missing file: data/{filename}")
            continue

        df = _load(filename)
        if df is None:
            errors.append(f"Cannot parse data/{filename} as CSV")
            continue

        if len(df) == 0:
            errors.append(f"data/{filename} is empty (0 data rows)")
            continue

        missing_cols = [c for c in required_cols if c not in df.columns]
        if missing_cols:
            errors.append(f"data/{filename} missing columns: {missing_cols}")
            continue

        dataframes[filename] = df
        logger.info(f"  {filename}: OK ({len(df)} rows, all required columns present)")

    if errors:
        for e in errors:
            logger.error(f"  ERROR: {e}")
        return False

    # ── 2. Null checks on critical identifier and text fields ─────────────────
    critical_nulls = {
        "accounts.csv": ["account_id", "account_name", "renewal_date", "csm_owner"],
        "support_tickets.csv": ["ticket_id", "account_id", "issue_summary"],
        "junior_outputs.csv": ["output_id", "account_id", "draft_text", "quality_standard_ids"],
        "quality_standards.csv": ["standard_id", "description"],
    }
    for filename, cols in critical_nulls.items():
        if filename not in dataframes:
            continue
        df = dataframes[filename]
        for col in cols:
            null_count = df[col].isna().sum()
            if null_count:
                errors.append(f"data/{filename}[{col}]: {null_count} null value(s)")

    # ── 3. Enum validation ─────────────────────────────────────────────────────
    for filename, col_enums in VALID_ENUMS.items():
        if filename not in dataframes:
            continue
        df = dataframes[filename]
        for col, valid_values in col_enums.items():
            if col not in df.columns:
                continue
            bad = set(df[col].dropna().unique()) - valid_values
            if bad:
                # Case-insensitive check first
                bad_lower = {v.lower() for v in bad}
                valid_lower = {v.lower() for v in valid_values}
                if bad_lower - valid_lower:
                    errors.append(
                        f"data/{filename}[{col}]: unexpected values {bad} "
                        f"(expected one of {valid_values})"
                    )
                else:
                    warnings.append(
                        f"data/{filename}[{col}]: case mismatch {bad} vs {valid_values}"
                    )

    # ── 4. Account ID consistency ──────────────────────────────────────────────
    if "accounts.csv" in dataframes:
        master_ids = set(dataframes["accounts.csv"]["account_id"].astype(str))

        for filename in ["usage_events.csv", "support_tickets.csv", "call_notes.csv",
                         "scheduled_checkins.csv", "junior_outputs.csv"]:
            if filename not in dataframes:
                continue
            ids_in_file = set(dataframes[filename]["account_id"].astype(str))
            orphans = ids_in_file - master_ids
            if orphans:
                errors.append(
                    f"data/{filename}: account_id(s) not in accounts.csv: {sorted(orphans)}"
                )

        # Warn about accounts with no usage data
        if "usage_events.csv" in dataframes:
            usage_ids = set(dataframes["usage_events.csv"]["account_id"].astype(str))
            no_usage = master_ids - usage_ids
            if no_usage:
                warnings.append(f"Accounts with no usage events: {sorted(no_usage)}")

        # Warn about accounts in tickets but not in checkins (gap accounts)
        if "support_tickets.csv" in dataframes and "scheduled_checkins.csv" in dataframes:
            ticket_ids = set(dataframes["support_tickets.csv"]["account_id"].astype(str))
            checkin_ids = set(dataframes["scheduled_checkins.csv"]["account_id"].astype(str))
            gap_accounts = ticket_ids - checkin_ids
            if gap_accounts:
                warnings.append(
                    f"Accounts with tickets but no scheduled check-in (gap): {sorted(gap_accounts)}"
                )

    # ── 5. QS standard ID consistency ─────────────────────────────────────────
    if "quality_standards.csv" in dataframes and "junior_outputs.csv" in dataframes:
        valid_qs = set(dataframes["quality_standards.csv"]["standard_id"].astype(str))
        all_referenced = set()
        for ids_str in dataframes["junior_outputs.csv"]["quality_standard_ids"].dropna():
            for sid in str(ids_str).split(";"):
                all_referenced.add(sid.strip())
        unknown_qs = all_referenced - valid_qs
        if unknown_qs:
            errors.append(
                f"junior_outputs.csv references unknown quality_standard_ids: {unknown_qs}"
            )

    # ── 6. Numeric range sanity ───────────────────────────────────────────────
    if "accounts.csv" in dataframes:
        df = dataframes["accounts.csv"]
        for col in ["current_health_score", "previous_health_score"]:
            if col in df.columns:
                out_of_range = df[(df[col] < 0) | (df[col] > 100)]
                if len(out_of_range):
                    warnings.append(
                        f"accounts.csv[{col}]: {len(out_of_range)} value(s) outside [0, 100]"
                    )
        if "nps_score" in df.columns:
            out_of_range = df[(df["nps_score"] < 0) | (df["nps_score"] > 10)]
            if len(out_of_range):
                warnings.append(
                    f"accounts.csv[nps_score]: {len(out_of_range)} value(s) outside [0, 10]"
                )

    # ── Report ────────────────────────────────────────────────────────────────
    for w in warnings:
        logger.warning(f"  WARNING: {w}")
    for e in errors:
        logger.error(f"  ERROR: {e}")

    if errors:
        logger.error(f"Validation failed: {len(errors)} error(s), {len(warnings)} warning(s).")
        return False

    logger.info(
        f"Validation passed: 0 errors, {len(warnings)} warning(s). "
        "Pipeline may proceed."
    )
    return True


if __name__ == "__main__":
    ok = validate_inputs()
    sys.exit(0 if ok else 1)
