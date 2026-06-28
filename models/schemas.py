from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Account:
    account_id: str
    account_name: str
    segment: str
    contract_value: int
    renewal_date: str
    csm_owner: str
    current_health_score: int
    previous_health_score: int
    product_usage_trend: str
    support_ticket_count_30d: int
    nps_score: int
    expansion_signal: str
    last_contact_date: str
    notes: str


@dataclass
class UsageSnapshot:
    account_id: str
    event_date: str
    active_users: int
    key_feature_users: int
    login_frequency: str
    usage_trend: str
    notable_change: str


@dataclass
class SupportTicket:
    ticket_id: str
    account_id: str
    date_received: str
    issue_summary: str
    severity: str
    customer_sentiment: str
    frontline_notes: str
    current_status: str


@dataclass
class CallNote:
    account_id: str
    call_date: str
    participants: str
    summary: str
    customer_goal: str
    risk_or_blocker: str
    follow_up_items: str


@dataclass
class CheckIn:
    checkin_id: str
    account_id: str
    scheduled_date: str
    checkin_type: str
    priority: str
    topics_to_cover: str


@dataclass
class JuniorOutput:
    output_id: str
    account_id: str
    output_type: str
    draft_text: str
    intended_customer_action: str
    quality_standard_ids: list[str]


@dataclass
class QualityStandard:
    standard_id: str
    standard_name: str
    description: str


@dataclass
class AccountContext:
    """All data sources merged for one account."""
    account: Account
    usage_snapshots: list[UsageSnapshot] = field(default_factory=list)
    tickets: list[SupportTicket] = field(default_factory=list)
    call_note: Optional[CallNote] = None
    checkin: Optional[CheckIn] = None
    junior_outputs: list[JuniorOutput] = field(default_factory=list)

    @property
    def account_id(self) -> str:
        return self.account.account_id

    @property
    def account_name(self) -> str:
        return self.account.account_name


@dataclass
class PriorityResult:
    account_id: str
    account_name: str
    tier: str
    urgency_score: float
    rationale: str
    days_to_renewal: int
    health_drop: int


@dataclass
class TriageResult:
    ticket_id: str
    account_id: str
    issue_type: str
    churn_risk: bool
    churn_risk_reason: str
    recommended_action: str
    gap_flag: bool
    gap_note: str


@dataclass
class CheckInBrief:
    checkin_id: str
    account_id: str
    account_name: str
    scheduled_date: str
    brief_text: str


@dataclass
class QualityReviewResult:
    output_id: str
    account_id: str
    output_type: str
    standard_results: dict[str, dict]  # {standard_id: {passed: bool, reason: str}}
    overall_passed: bool
    rewrite_suggestion: str


@dataclass
class InterventionPlan:
    account_id: str
    account_name: str
    priority_tier: str
    plan_text: str


@dataclass
class CheckInIntake:
    """Structured post-call record captured after a check-in completes."""
    intake_id: str
    checkin_id: str
    account_id: str
    call_date: str
    topics_covered: str
    decisions_made: str
    follow_ups_committed: str   # pipe-separated list of items
    risks_updated: str
    customer_sentiment: str     # positive / neutral / negative
    csm_notes: str


@dataclass
class FollowUpItem:
    """A single tracked commitment extracted from a post-call intake."""
    item_id: str
    account_id: str
    source_checkin_id: str
    description: str
    owner: str
    due_date: str
    status: str                 # "open" | "completed" | "overdue"
    completed_date: str = ""


@dataclass
class RoutingDecision:
    account_id: str
    account_name: str
    track: str
    reason: str
    owner: str
    next_step: str
    # Approval workflow — only meaningful when track == "Escalate"
    status: str = "approved"          # "approved" | "denied" | "pending_review"
    reviewed_by: str = ""
    reviewed_at: str = ""
    denial_reason: str = ""
