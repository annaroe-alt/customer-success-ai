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
MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 2048

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
