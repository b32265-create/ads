import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()

# Admin Telegram IDs (comma-separated, e.g. "8457796840")
_admin_raw = os.getenv("ADMIN_IDS", "8457796840")
ADMIN_IDS = [int(x.strip()) for x in _admin_raw.split(",") if x.strip().isdigit()]

# Telegram API credentials for Telethon client login
API_ID = int(os.getenv("API_ID", "2040"))
API_HASH = os.getenv("API_HASH", "b18441a1ff607e10a989891a5462e627")

# Database settings
DB_PATH = os.getenv("DB_PATH", "shadow_ads.db")
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()

# Default Ad posting settings
DEFAULT_MSG_DELAY = int(os.getenv("DEFAULT_MSG_DELAY", "5"))       # seconds
DEFAULT_CYCLE_INTERVAL = int(os.getenv("DEFAULT_CYCLE_INTERVAL", "600")) # 10 mins in seconds
