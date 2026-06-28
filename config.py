import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# Paths
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
OUTPUTS_DIR = BASE_DIR / "outputs"
PROMPTS_DIR = BASE_DIR / "prompts"
LOGS_DIR = BASE_DIR / "logs"

# Anthropic
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

# Primary model for long-form stages (check-in prep, quality review, intervention)
MODEL = "claude-sonnet-4-6"
# Fast/cheap model for short structured-output stages (triage, borderline tier, routing)
MODEL_FAST = "claude-haiku-4-5-20251001"

# Global fallback; stages override per-call with appropriate limits
MAX_TOKENS = 2048
# Short structured outputs (2-4 lines: TIER/TRACK/ISSUE_TYPE responses)
MAX_TOKENS_SHORT = 256
# Long-form markdown outputs (briefs, plans, quality reviews)
MAX_TOKENS_LONG = 1024

# Prioritization thresholds (days to renewal)
RENEWAL_CRITICAL_DAYS = 30
RENEWAL_HIGH_DAYS = 60
RENEWAL_MEDIUM_DAYS = 90

# Health score drop that elevates tier
HEALTH_DROP_CRITICAL = 20
HEALTH_DROP_HIGH = 10

# Priority tier labels
TIER_CRITICAL = "Critical"
TIER_HIGH = "High"
TIER_MEDIUM = "Medium"
TIER_LOW = "Low"
TIER_MONITOR = "Monitor"

# Routing track labels
TRACK_RESOLVE = "Resolve"
TRACK_FOLLOW_UP = "Follow-up"
TRACK_ESCALATE = "Escalate"
