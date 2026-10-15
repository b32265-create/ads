"""
Shadow Ads Bot - PostgreSQL Database Module
==========================================
Uses asyncpg with connection pooling for high-performance 500+ concurrent account support.
Connection pool: min=10, max=50 connections.
All operations are async and production-ready.
"""

import asyncpg
import logging
import json
from typing import Optional, List, Dict, Any
from config import DATABASE_URL

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────
# GLOBAL CONNECTION POOL
# ─────────────────────────────────────────────────────────
_pool: Optional[asyncpg.Pool] = None

async def get_pool() -> asyncpg.Pool:
    """Return the global connection pool, creating it if needed."""
    global _pool
    if _pool is None or _pool._closed:
        if not DATABASE_URL:
            raise ValueError("DATABASE_URL is not configured in .env! Cannot connect to PostgreSQL.")
        dsn = DATABASE_URL
        if dsn.startswith("postgres://"):
            dsn = dsn.replace("postgres://", "postgresql://", 1)
        _pool = await asyncpg.create_pool(
            dsn=dsn,
            min_size=5,
            max_size=30,
            max_inactive_connection_lifetime=300,
            command_timeout=30,
            statement_cache_size=0,  # 0 ensures compatibility with PgBouncer / Supabase poolers
        )
        logger.info("PostgreSQL connection pool created (min=5, max=30)")
    return _pool

async def close_pool():
    """Gracefully close the connection pool on shutdown."""
    global _pool
    if _pool and not _pool._closed:
        await _pool.close()
        logger.info("PostgreSQL connection pool closed.")

# ─────────────────────────────────────────────────────────
# IN-MEMORY ULTRA-FAST RAM CACHES (0ms latency for repeated lookups)
# ─────────────────────────────────────────────────────────
_cache_settings: Dict[int, Dict[str, Any]] = {}
_cache_account_counts: Dict[int, int] = {}
_cache_user_info: Dict[int, Dict[str, Any]] = {}
_cache_force_channels: Optional[List[Dict[str, Any]]] = None
_cache_bot_settings: Dict[str, str] = {}
_cache_system_accounts: Dict[str, Dict[str, Any]] = {}
_cache_user_messaged: Dict[int, Tuple[bool, bool]] = {}
_known_users: set = set()

# ─────────────────────────────────────────────────────────
# DATABASE INITIALIZATION - CREATE ALL TABLES
# ─────────────────────────────────────────────────────────
async def init_db():
    """Initialize all tables and indexes. Safe to call on every startup."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        # Enable UUID extension
        await conn.execute("CREATE EXTENSION IF NOT EXISTS \"uuid-ossp\";")

        # 1. USERS TABLE
        await conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id            BIGINT PRIMARY KEY,
            username           TEXT,
            first_name         TEXT,
            joined_at          TIMESTAMPTZ DEFAULT NOW(),
            is_banned          SMALLINT DEFAULT 0,
            is_premium         SMALLINT DEFAULT 0,
            referred_by        BIGINT DEFAULT NULL,
            referral_count     INTEGER DEFAULT 0,
            premium_expires_at TIMESTAMPTZ DEFAULT NULL
        );
        """)

        # Migrations for existing deployments
        await conn.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS referred_by BIGINT DEFAULT NULL;")
        await conn.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS referral_count INTEGER DEFAULT 0;")
        await conn.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS premium_expires_at TIMESTAMPTZ DEFAULT NULL;")

        # 2. USER SETTINGS TABLE
        await conn.execute("""
        CREATE TABLE IF NOT EXISTS user_settings (
            user_id          BIGINT PRIMARY KEY REFERENCES users(user_id) ON DELETE CASCADE,
            ad_message       TEXT DEFAULT NULL,
            ad_media_id      TEXT DEFAULT NULL,
            ad_media_type    TEXT DEFAULT NULL,
            cycle_interval   INTEGER DEFAULT 0,
            message_delay    INTEGER DEFAULT 5,
            target_type      TEXT DEFAULT 'Groups',
            max_cycles       INTEGER DEFAULT 0,
            completed_cycles INTEGER DEFAULT 0,
            status           TEXT DEFAULT 'Paused',
            ai_reply         SMALLINT DEFAULT 0,
            exclude_groups   TEXT DEFAULT '',
            schedule_start   TEXT DEFAULT NULL,
            schedule_end     TEXT DEFAULT NULL,
            schedule_enabled SMALLINT DEFAULT 0,
            manager_enabled  SMALLINT DEFAULT 1
        );
        """)

        # 3. ACCOUNTS TABLE (Telethon sessions)
        await conn.execute("""
        CREATE TABLE IF NOT EXISTS accounts (
            id             BIGSERIAL PRIMARY KEY,
            user_id        BIGINT REFERENCES users(user_id) ON DELETE CASCADE,
            phone_number   TEXT,
            session_string TEXT,
            account_name   TEXT,
            status         TEXT DEFAULT 'active',
            is_banned      SMALLINT DEFAULT 0,
            total_sent     INTEGER DEFAULT 0,
            total_failed   INTEGER DEFAULT 0,
            last_used_at   TIMESTAMPTZ,
            added_at       TIMESTAMPTZ DEFAULT NOW()
        );
        """)

        # 4. FORCE JOIN CHANNELS TABLE
        await conn.execute("""
        CREATE TABLE IF NOT EXISTS force_join_channels (
            id          SERIAL PRIMARY KEY,
            channel_id  TEXT UNIQUE NOT NULL,
            title       TEXT,
            invite_link TEXT,
            is_active   SMALLINT DEFAULT 1
        );
        """)

        # 5. BOT SETTINGS KEY-VALUE TABLE
        await conn.execute("""
        CREATE TABLE IF NOT EXISTS bot_settings (
            key   TEXT PRIMARY KEY,
            value TEXT
        );
        """)

        # 6. ANALYTICS TABLE
        await conn.execute("""
        CREATE TABLE IF NOT EXISTS analytics (
            user_id      BIGINT PRIMARY KEY REFERENCES users(user_id) ON DELETE CASCADE,
            total_sent   INTEGER DEFAULT 0,
            total_failed INTEGER DEFAULT 0,
            last_sent_at TIMESTAMPTZ
        );
        """)

        # 7. LEAD MESSAGES RELAY TABLE (Incoming DMs & Replies)
        await conn.execute("""
        CREATE TABLE IF NOT EXISTS lead_messages (
            id             BIGSERIAL PRIMARY KEY,
            user_id        BIGINT REFERENCES users(user_id) ON DELETE CASCADE,
            account_id     BIGINT,
            alt_username   TEXT,
            lead_id        BIGINT,
            lead_username  TEXT,
            lead_name      TEXT,
            message_text   TEXT,
            bot_message_id BIGINT,
            created_at     TIMESTAMPTZ DEFAULT NOW()
        );
        """)

        # 8. SYSTEM ACCOUNTS (Admin-hosted Log Account & Manager Account)
        await conn.execute("""
        CREATE TABLE IF NOT EXISTS system_accounts (
            role           TEXT PRIMARY KEY,
            session_string TEXT,
            phone_number   TEXT,
            account_name   TEXT,
            username       TEXT,
            tg_id          BIGINT,
            updated_at     TIMESTAMPTZ DEFAULT NOW()
        );
        """)

        # 9. USER MESSAGED ACCOUNTS (Mandatory verification tracking)
        await conn.execute("""
        CREATE TABLE IF NOT EXISTS user_messaged_accounts (
            user_id          BIGINT PRIMARY KEY,
            messaged_log     SMALLINT DEFAULT 0,
            messaged_manager SMALLINT DEFAULT 0,
            updated_at       TIMESTAMPTZ DEFAULT NOW()
        );
        """)

        # Migrations for user_settings
        await conn.execute("ALTER TABLE user_settings ADD COLUMN IF NOT EXISTS forward_account TEXT DEFAULT NULL;")
        await conn.execute("ALTER TABLE user_settings ADD COLUMN IF NOT EXISTS manager_enabled SMALLINT DEFAULT 1;")
        await conn.execute("ALTER TABLE user_settings ADD COLUMN IF NOT EXISTS autodm_enabled SMALLINT DEFAULT 0;")
        await conn.execute("ALTER TABLE user_settings ADD COLUMN IF NOT EXISTS autodm_message TEXT DEFAULT NULL;")
        await conn.execute("ALTER TABLE user_settings ADD COLUMN IF NOT EXISTS autodm_media_id TEXT DEFAULT NULL;")
        await conn.execute("ALTER TABLE user_settings ADD COLUMN IF NOT EXISTS autodm_media_type TEXT DEFAULT NULL;")
        await conn.execute("ALTER TABLE user_settings ADD COLUMN IF NOT EXISTS autodm_rate_per_hour INTEGER DEFAULT 10;")
        await conn.execute("ALTER TABLE user_settings ADD COLUMN IF NOT EXISTS autodm_target_mode TEXT DEFAULT 'groups';")
        await conn.execute("ALTER TABLE user_settings ADD COLUMN IF NOT EXISTS autodm_custom_targets TEXT DEFAULT '';")
        await conn.execute("ALTER TABLE user_settings ADD COLUMN IF NOT EXISTS autodm_total_sent INTEGER DEFAULT 0;")
        await conn.execute("ALTER TABLE user_settings ADD COLUMN IF NOT EXISTS autodm_total_failed INTEGER DEFAULT 0;")
        await conn.execute("ALTER TABLE user_settings ADD COLUMN IF NOT EXISTS autodm_keywords TEXT DEFAULT '';")
        await conn.execute("ALTER TABLE user_settings ADD COLUMN IF NOT EXISTS autodm_auto_reply TEXT DEFAULT NULL;")
        await conn.execute("ALTER TABLE user_settings ADD COLUMN IF NOT EXISTS autodm_interval_minutes INTEGER DEFAULT 10;")
        await conn.execute("ALTER TABLE user_settings ADD COLUMN IF NOT EXISTS autodm_rate_per_round INTEGER DEFAULT 2;")

        # 10. CONTACTED LEADS TABLE (Anti-spam / Anti-duplicate protection)
        await conn.execute("""
        CREATE TABLE IF NOT EXISTS contacted_leads (
            id           BIGSERIAL PRIMARY KEY,
            user_id      BIGINT,
            lead_id      TEXT,
            contacted_at TIMESTAMPTZ DEFAULT NOW(),
            UNIQUE(user_id, lead_id)
        );
        """)

        # 11. SCRAPED LEADS TABLE
        await conn.execute("""
        CREATE TABLE IF NOT EXISTS scraped_leads (
            id           BIGSERIAL PRIMARY KEY,
            user_id      BIGINT REFERENCES users(user_id) ON DELETE CASCADE,
            username     TEXT,
            lead_id      TEXT,
            first_name   TEXT,
            group_id     TEXT,
            group_title  TEXT,
            scraped_at   TIMESTAMPTZ DEFAULT NOW(),
            is_contacted SMALLINT DEFAULT 0,
            UNIQUE(user_id, lead_id)
        );
        """)
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_scraped_leads_user ON scraped_leads(user_id, is_contacted);")

        # 12. GROUP SCAN PROGRESS
        await conn.execute("""
        CREATE TABLE IF NOT EXISTS group_scan_progress (
            user_id         BIGINT REFERENCES users(user_id) ON DELETE CASCADE,
            group_id        TEXT,
            last_msg_id     BIGINT DEFAULT 0,
            last_scanned_at TIMESTAMPTZ DEFAULT NOW(),
            PRIMARY KEY(user_id, group_id)
        );
        """)

        # ── INDEXES for performance ──────────────────────
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_accounts_user_id   ON accounts(user_id);")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_accounts_status     ON accounts(user_id, status, is_banned);")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_users_banned        ON users(is_banned);")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_user_settings_status ON user_settings(status);")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_force_join_active   ON force_join_channels(is_active);")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_lead_msg_lookup     ON lead_messages(user_id, bot_message_id);")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_lead_msg_account    ON lead_messages(account_id, lead_id);")

        # Pre-warm in-memory caches to guarantee 0ms latency for user interactions
        try:
            users_rows = await conn.fetch("SELECT * FROM users")
            for r in users_rows:
                _known_users.add(r['user_id'])
                _cache_user_info[r['user_id']] = dict(r)

            settings_rows = await conn.fetch("SELECT * FROM user_settings")
            for r in settings_rows:
                _cache_settings[r['user_id']] = dict(r)

            counts_rows = await conn.fetch("SELECT user_id, COUNT(*) as cnt FROM accounts WHERE status = 'active' AND is_banned = 0 GROUP BY user_id")
            for r in counts_rows:
                _cache_account_counts[r['user_id']] = r['cnt']

            sys_rows = await conn.fetch("SELECT * FROM system_accounts")
            for r in sys_rows:
                _cache_system_accounts[r['role']] = dict(r)

            b_settings_rows = await conn.fetch("SELECT key, value FROM bot_settings")
            for r in b_settings_rows:
                _cache_bot_settings[r['key']] = r['value']

            msg_rows = await conn.fetch("SELECT user_id, messaged_log, messaged_manager FROM user_messaged_accounts")
            for r in msg_rows:
                _cache_user_messaged[r['user_id']] = (bool(r['messaged_log']), bool(r['messaged_manager']))
        except Exception as e:
            logger.warning(f"Could not pre-warm database caches: {e}")

    logger.info("✅ PostgreSQL database initialized with all tables, indexes, and hot-RAM caches!")

# ─────────────────────────────────────────────────────────
# USER OPERATIONS
# ─────────────────────────────────────────────────────────
async def get_or_create_user(user_id: int, username: str = None, first_name: str = None):
    # If user already registered in current session, skip redundant DB roundtrips (0ms!)
    if user_id in _known_users:
        return

    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute("""
                INSERT INTO users (user_id, username, first_name)
                VALUES ($1, $2, $3)
                ON CONFLICT (user_id) DO UPDATE
                SET username = EXCLUDED.username, first_name = EXCLUDED.first_name
            """, user_id, username, first_name)

            await conn.execute("""
                INSERT INTO user_settings (user_id) VALUES ($1)
                ON CONFLICT (user_id) DO NOTHING
            """, user_id)

            await conn.execute("""
                INSERT INTO analytics (user_id) VALUES ($1)
                ON CONFLICT (user_id) DO NOTHING
            """, user_id)

    _known_users.add(user_id)

async def get_all_user_ids() -> List[int]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT user_id FROM users WHERE is_banned = 0")
        return [r['user_id'] for r in rows]

async def get_user_count() -> int:
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchval("SELECT COUNT(*) FROM users")

async def get_premium_user_count() -> int:
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchval("SELECT COUNT(*) FROM users WHERE is_premium = 1")

async def get_banned_user_count() -> int:
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchval("SELECT COUNT(*) FROM users WHERE is_banned = 1")

async def get_user_info(user_id: int) -> Optional[Dict]:
    if user_id in _cache_user_info:
        return dict(_cache_user_info[user_id])
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM users WHERE user_id = $1", user_id)
        if row:
            data = dict(row)
            _cache_user_info[user_id] = data
            return dict(data)
        return None

async def set_user_banned(user_id: int, banned: bool):
    _cache_user_info.pop(user_id, None)
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE users SET is_banned = $1 WHERE user_id = $2",
            1 if banned else 0, user_id
        )

async def set_user_premium(user_id: int, premium: bool):
    _cache_user_info.pop(user_id, None)
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE users SET is_premium = $1 WHERE user_id = $2",
            1 if premium else 0, user_id
        )
        await conn.execute(
            "UPDATE users SET is_premium = $1 WHERE user_id = $2",
            1 if premium else 0, user_id
        )

async def get_all_users_list(limit: int = 50, offset: int = 0) -> List[Dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM users ORDER BY joined_at DESC LIMIT $1 OFFSET $2",
            limit, offset
        )
        return [dict(r) for r in rows]

async def search_user_by_id_or_username(query: str) -> Optional[Dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        q = query.lstrip('@')
        row = await conn.fetchrow(
            "SELECT * FROM users WHERE user_id::TEXT = $1 OR username = $2 LIMIT 1",
            q, q
        )
        return dict(row) if row else None

async def get_total_active_campaigns() -> int:
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchval(
            "SELECT COUNT(*) FROM user_settings WHERE status = 'Running'"
        )

async def get_global_total_sent() -> int:
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchval(
            "SELECT COALESCE(SUM(total_sent), 0) FROM analytics"
        )

async def get_total_accounts() -> int:
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchval(
            "SELECT COUNT(*) FROM accounts WHERE status = 'active'"
        )

# ─────────────────────────────────────────────────────────
# USER SETTINGS OPERATIONS
# ─────────────────────────────────────────────────────────
_ALLOWED_SETTING_KEYS = {
    'ad_message', 'ad_media_id', 'ad_media_type', 'cycle_interval',
    'message_delay', 'target_type', 'max_cycles', 'completed_cycles',
    'status', 'ai_reply', 'exclude_groups',
    'schedule_start', 'schedule_end', 'schedule_enabled',
    'forward_account', 'manager_enabled',
    'autodm_enabled', 'autodm_message', 'autodm_media_id', 'autodm_media_type',
    'autodm_rate_per_hour', 'autodm_target_mode', 'autodm_custom_targets',
    'autodm_total_sent', 'autodm_total_failed',
    'autodm_keywords', 'autodm_auto_reply'
}

async def get_user_settings(user_id: int) -> Dict:
    # 1. Ultra-fast RAM lookup (< 0.01 ms)
    if user_id in _cache_settings:
        return dict(_cache_settings[user_id])

    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM user_settings WHERE user_id = $1", user_id
        )
        if not row:
            await conn.execute(
                "INSERT INTO user_settings (user_id) VALUES ($1) ON CONFLICT DO NOTHING",
                user_id
            )
            row = await conn.fetchrow(
                "SELECT * FROM user_settings WHERE user_id = $1", user_id
            )
        data = dict(row) if row else {}
        _cache_settings[user_id] = dict(data)
        return data

async def update_user_setting(user_id: int, key: str, value):
    if key not in _ALLOWED_SETTING_KEYS:
        raise ValueError(f"Invalid setting key: {key}")

    # 1. Update RAM cache instantly (0ms)
    if user_id in _cache_settings:
        _cache_settings[user_id][key] = value
    else:
        _cache_settings[user_id] = {key: value}

    # 2. Persist to DB
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            f"UPDATE user_settings SET {key} = $1 WHERE user_id = $2",
            value, user_id
        )

async def update_user_settings_bulk(user_id: int, updates: Dict[str, Any]):
    """Update multiple settings in a single transaction for performance."""
    for key in updates:
        if key not in _ALLOWED_SETTING_KEYS:
            raise ValueError(f"Invalid setting key: {key}")
    if not updates:
        return
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            for key, value in updates.items():
                await conn.execute(
                    f"UPDATE user_settings SET {key} = $1 WHERE user_id = $2",
                    value, user_id
                )

async def get_active_running_users() -> List[int]:
    """List of user_ids with status='Running'."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT user_id FROM user_settings WHERE status = 'Running'")
        return [r["user_id"] for r in rows]

# --- AUTO DM HELPERS ---
async def is_lead_contacted(user_id: int, lead_id: str) -> bool:
    """Returns True if this lead has already received an Auto DM from this user."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id FROM contacted_leads WHERE user_id = $1 AND lead_id = $2 LIMIT 1",
            user_id, str(lead_id).lower().strip()
        )
        return bool(row)

async def mark_lead_contacted(user_id: int, lead_id: str):
    """Mark a lead as contacted to prevent duplicate messages."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO contacted_leads (user_id, lead_id) VALUES ($1, $2) ON CONFLICT DO NOTHING",
            user_id, str(lead_id).lower().strip()
        )

async def clear_contacted_leads(user_id: int):
    """Reset contacted leads history for a user."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM contacted_leads WHERE user_id = $1", user_id)

async def increment_autodm_stats(user_id: int, sent: int = 0, failed: int = 0):
    """Increment Auto DM total sent and failed counts."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE user_settings SET autodm_total_sent = COALESCE(autodm_total_sent, 0) + $1, autodm_total_failed = COALESCE(autodm_total_failed, 0) + $2 WHERE user_id = $3",
            sent, failed, user_id
        )

async def get_active_autodm_users() -> List[int]:
    """List of user_ids with autodm_enabled = 1."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT user_id FROM user_settings WHERE autodm_enabled = 1")
        return [r["user_id"] for r in rows]

# --- SCRAPED LEADS HELPERS ---
async def save_scraped_leads_batch(user_id: int, leads: list) -> int:
    """
    Saves a batch of leads: (username, lead_id, first_name, group_id, group_title).
    Returns number of newly saved unique leads.
    """
    if not leads:
        return 0
    pool = await get_pool()
    new_count = 0
    async with pool.acquire() as conn:
        for item in leads:
            username, lead_id, first_name, group_id, group_title = item
            clean_u = (username or "").lstrip("@").strip()
            lead_id_str = str(lead_id).strip()
            res = await conn.execute("""
                INSERT INTO scraped_leads (user_id, username, lead_id, first_name, group_id, group_title)
                VALUES ($1, $2, $3, $4, $5, $6)
                ON CONFLICT (user_id, lead_id) DO NOTHING
            """, user_id, clean_u or None, lead_id_str, first_name or "", str(group_id), group_title or "")
            if res.endswith("1"):
                new_count += 1
    return new_count

async def get_scraped_leads_stats(user_id: int) -> dict:
    """Returns count of total, pending (uncontacted), and contacted leads."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT 
                COUNT(*) AS total,
                COALESCE(SUM(CASE WHEN is_contacted = 0 THEN 1 ELSE 0 END), 0) AS pending,
                COALESCE(SUM(CASE WHEN is_contacted = 1 THEN 1 ELSE 0 END), 0) AS contacted
            FROM scraped_leads
            WHERE user_id = $1
        """, user_id)
        if row:
            return {
                "total": row["total"] or 0,
                "pending": row["pending"] or 0,
                "contacted": row["contacted"] or 0
            }
        return {"total": 0, "pending": 0, "contacted": 0}

async def get_pending_scraped_leads(user_id: int, limit: int = 50) -> list:
    """Fetch uncontacted leads for Auto DM dispatch."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM scraped_leads WHERE user_id = $1 AND is_contacted = 0 ORDER BY id ASC LIMIT $2",
            user_id, limit
        )
        return [dict(r) for r in rows]

async def mark_scraped_lead_contacted(user_id: int, lead_id: str, username: str = None):
    """Marks a lead as contacted in scraped_leads table."""
    pool = await get_pool()
    clean_u = (username or "").lstrip("@").strip()
    async with pool.acquire() as conn:
        if clean_u:
            await conn.execute(
                "UPDATE scraped_leads SET is_contacted = 1 WHERE user_id = $1 AND (lead_id = $2 OR LOWER(username) = $3)",
                user_id, str(lead_id).strip(), clean_u.lower()
            )
        else:
            await conn.execute(
                "UPDATE scraped_leads SET is_contacted = 1 WHERE user_id = $1 AND lead_id = $2",
                user_id, str(lead_id).strip()
            )

async def get_all_scraped_leads_list(user_id: int, limit: int = 1000) -> list:
    """Returns list of scraped leads for display / export."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT username, lead_id, first_name, group_title, is_contacted, scraped_at FROM scraped_leads WHERE user_id = $1 ORDER BY id DESC LIMIT $2",
            user_id, limit
        )
        return [dict(r) for r in rows]

async def clear_scraped_leads(user_id: int):
    """Deletes all scraped leads for this user."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM scraped_leads WHERE user_id = $1", user_id)

async def get_group_last_scanned_msg_id(user_id: int, group_id: str) -> int:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchval(
            "SELECT last_msg_id FROM group_scan_progress WHERE user_id = $1 AND group_id = $2",
            user_id, str(group_id)
        )
        return row or 0

async def update_group_last_scanned_msg_id(user_id: int, group_id: str, msg_id: int):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO group_scan_progress (user_id, group_id, last_msg_id, last_scanned_at)
            VALUES ($1, $2, $3, NOW())
            ON CONFLICT (user_id, group_id) DO UPDATE SET
                last_msg_id = GREATEST(group_scan_progress.last_msg_id, EXCLUDED.last_msg_id),
                last_scanned_at = NOW()
        """, user_id, str(group_id), msg_id)

# ─────────────────────────────────────────────────────────
# ACCOUNTS OPERATIONS
# ─────────────────────────────────────────────────────────
async def add_account(user_id: int, phone_number: str, session_string: str, account_name: str = "") -> int:
    pool = await get_pool()
    async with pool.acquire() as conn:
        # Check if already exists
        existing = await conn.fetchval(
            "SELECT id FROM accounts WHERE user_id = $1 AND phone_number = $2",
            user_id, phone_number
        )
        if existing:
            await conn.execute(
                "UPDATE accounts SET session_string = $1, account_name = $2, status = 'active', is_banned = 0 WHERE id = $3",
                session_string, account_name, existing
            )
            return existing

        new_id = await conn.fetchval(
            "INSERT INTO accounts (user_id, phone_number, session_string, account_name) VALUES ($1, $2, $3, $4) RETURNING id",
            user_id, phone_number, session_string, account_name
        )
        _cache_account_counts.pop(user_id, None)
        return new_id

async def get_user_accounts(user_id: int) -> List[Dict]:
    """Get active non-banned accounts (used by ads worker)."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM accounts WHERE user_id = $1 AND is_banned = 0 AND status = 'active' ORDER BY id",
            user_id
        )
        return [dict(r) for r in rows]

async def get_user_accounts_all(user_id: int) -> List[Dict]:
    """Get ALL accounts including banned ones (for display in My Accounts)."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM accounts WHERE user_id = $1 ORDER BY added_at DESC",
            user_id
        )
        return [dict(r) for r in rows]

async def get_all_active_accounts() -> List[Dict]:
    """Get ALL active, non-banned accounts across all users for admin mass tasks."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM accounts WHERE status = 'active' AND is_banned = 0 ORDER BY id ASC"
        )
        return [dict(r) for r in rows]

async def get_account_count(user_id: int) -> int:
    if user_id in _cache_account_counts:
        return _cache_account_counts[user_id]
    pool = await get_pool()
    async with pool.acquire() as conn:
        val = await conn.fetchval(
            "SELECT COUNT(*) FROM accounts WHERE user_id = $1 AND status = 'active' AND is_banned = 0",
            user_id
        )
        count = val or 0
        _cache_account_counts[user_id] = count
        return count

async def mark_account_banned(account_id: int):
    _cache_account_counts.clear()
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE accounts SET is_banned = 1, status = 'banned' WHERE id = $1",
            account_id
        )

async def update_account_stats(account_id: int, sent: int = 0, failed: int = 0):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE accounts SET total_sent = total_sent + $1, total_failed = total_failed + $2, last_used_at = NOW() WHERE id = $3",
            sent, failed, account_id
        )

async def delete_account_by_id(account_id: int, user_id: int):
    _cache_account_counts.pop(user_id, None)
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "DELETE FROM accounts WHERE id = $1 AND user_id = $2",
            account_id, user_id
        )

async def delete_all_user_accounts(user_id: int):
    _cache_account_counts.pop(user_id, None)
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM accounts WHERE user_id = $1", user_id)

# ─────────────────────────────────────────────────────────
# FORCE JOIN CHANNELS
# ─────────────────────────────────────────────────────────
async def add_force_channel(channel_id: str, title: str, invite_link: str):
    global _cache_force_channels
    _cache_force_channels = None
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO force_join_channels (channel_id, title, invite_link, is_active)
            VALUES ($1, $2, $3, 1)
            ON CONFLICT (channel_id) DO UPDATE
            SET title = EXCLUDED.title, invite_link = EXCLUDED.invite_link, is_active = 1
        """, str(channel_id), title, invite_link)

async def get_active_force_channels() -> List[Dict]:
    global _cache_force_channels
    if _cache_force_channels is not None:
        return [dict(c) for c in _cache_force_channels]

    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM force_join_channels WHERE is_active = 1 ORDER BY id"
        )
        _cache_force_channels = [dict(r) for r in rows]
        return [dict(c) for c in _cache_force_channels]

async def remove_force_channel(channel_id: str):
    global _cache_force_channels
    _cache_force_channels = None
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "DELETE FROM force_join_channels WHERE channel_id = $1",
            str(channel_id)
        )

# ─────────────────────────────────────────────────────────
# ANALYTICS
# ─────────────────────────────────────────────────────────
async def get_analytics(user_id: int) -> Dict:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM analytics WHERE user_id = $1", user_id
        )
        return dict(row) if row else {"total_sent": 0, "total_failed": 0, "last_sent_at": None}

async def increment_analytics(user_id: int, sent_count: int = 1, failed_count: int = 0):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            UPDATE analytics
            SET total_sent   = total_sent + $1,
                total_failed = total_failed + $2,
                last_sent_at = NOW()
            WHERE user_id = $3
        """, sent_count, failed_count, user_id)

# ─────────────────────────────────────────────────────────
# BOT GLOBAL SETTINGS
# ─────────────────────────────────────────────────────────
async def get_bot_setting(key: str, default=None) -> Optional[str]:
    if key in _cache_bot_settings:
        return _cache_bot_settings[key]
    pool = await get_pool()
    async with pool.acquire() as conn:
        val = await conn.fetchval(
            "SELECT value FROM bot_settings WHERE key = $1", key
        )
        res = val if val is not None else default
        if res is not None:
            _cache_bot_settings[key] = str(res)
        return res

async def set_bot_setting(key: str, value: str):
    _cache_bot_settings[key] = str(value)
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO bot_settings (key, value) VALUES ($1, $2)
            ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
        """, key, str(value))

async def get_all_bot_settings() -> Dict[str, str]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT key, value FROM bot_settings")
        res = {r['key']: r['value'] for r in rows}
        _cache_bot_settings.update(res)
        return res

# ─────────────────────────────────────────────────────────
# REFERRAL & REWARD OPERATIONS
# ─────────────────────────────────────────────────────────
async def record_user_referral(new_user_id: int, referrer_id: int) -> Tuple[bool, int, bool]:
    """
    Records a referral if new_user_id is not self and not already referred.
    Every 1 referral grants +2 days of VIP Premium access to referrer!
    Returns: (is_counted: bool, new_referral_count: int, unlocked_reward: bool)
    """
    if new_user_id == referrer_id:
        return False, 0, False

    pool = await get_pool()
    async with pool.acquire() as conn:
        # Check if referrer exists
        ref_exists = await conn.fetchval("SELECT user_id FROM users WHERE user_id = $1", referrer_id)
        if not ref_exists:
            return False, 0, False

        # Check if new user already has a referrer
        existing_ref = await conn.fetchval("SELECT referred_by FROM users WHERE user_id = $1", new_user_id)
        if existing_ref is not None:
            return False, 0, False

        # Set referred_by on new user
        await conn.execute("UPDATE users SET referred_by = $1 WHERE user_id = $2", referrer_id, new_user_id)

        # Increment referrer's count
        new_count = await conn.fetchval(
            "UPDATE users SET referral_count = COALESCE(referral_count, 0) + 1 WHERE user_id = $1 RETURNING referral_count",
            referrer_id
        )
        if new_count is None:
            return False, 0, False

        # Reward: 1 referral = 2 days VIP premium access!
        await conn.execute("""
            UPDATE users 
            SET is_premium = 1,
                premium_expires_at = CASE 
                    WHEN premium_expires_at IS NOT NULL AND premium_expires_at > NOW() 
                    THEN premium_expires_at + INTERVAL '2 days'
                    ELSE NOW() + INTERVAL '2 days'
                END
            WHERE user_id = $1
        """, referrer_id)
        _cache_user_info.pop(referrer_id, None)

        return True, new_count, True

async def get_user_referral_stats(user_id: int) -> Dict[str, Any]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT referral_count, referred_by, is_premium, premium_expires_at FROM users WHERE user_id = $1",
            user_id
        )
        if row:
            return dict(row)
        return {"referral_count": 0, "referred_by": None, "is_premium": 0, "premium_expires_at": None}

async def set_user_premium_status(user_id: int, is_premium: int = 1, days: Optional[int] = None):
    _cache_user_info.pop(user_id, None)
    pool = await get_pool()
    async with pool.acquire() as conn:
        if days:
            await conn.execute(
                f"UPDATE users SET is_premium = $1, premium_expires_at = NOW() + INTERVAL '{days} days' WHERE user_id = $2",
                is_premium, user_id
            )
        else:
            await conn.execute(
                "UPDATE users SET is_premium = $1, premium_expires_at = NULL WHERE user_id = $2",
                is_premium, user_id
            )

# ─────────────────────────────────────────────────────────
# LOG ACCOUNT OPERATIONS
# ─────────────────────────────────────────────────────────
async def get_log_account() -> str:
    acc = await get_system_account("log")
    if acc and acc.get("username"):
        return acc["username"]
    val = await get_bot_setting("log_account_username", "")
    return val or ""

async def set_log_account(username: str):
    clean = username.replace("@", "").replace("https://t.me/", "").strip()
    await set_bot_setting("log_account_username", clean)

# ─────────────────────────────────────────────────────────
# MANAGER ACCOUNT & LEAD DM RELAY OPERATIONS
# ─────────────────────────────────────────────────────────
async def get_manager_account() -> str:
    acc = await get_system_account("manager")
    if acc and acc.get("username"):
        return acc["username"]
    val = await get_bot_setting("manager_account_username", "")
    return val or ""

async def set_manager_account(username_or_id: str):
    clean = username_or_id.replace("@", "").replace("https://t.me/", "").strip()
    await set_bot_setting("manager_account_username", clean)

async def get_account_by_id(account_id: int) -> Optional[Dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM accounts WHERE id = $1", account_id)
        return dict(row) if row else None

async def save_lead_message(
    user_id: int,
    account_id: int,
    alt_username: str,
    lead_id: int,
    lead_username: str,
    lead_name: str,
    message_text: str,
    bot_message_id: int
) -> int:
    pool = await get_pool()
    async with pool.acquire() as conn:
        val = await conn.fetchval("""
            INSERT INTO lead_messages (
                user_id, account_id, alt_username, lead_id, lead_username,
                lead_name, message_text, bot_message_id
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            RETURNING id
        """, user_id, account_id, alt_username, lead_id, lead_username or "", lead_name or "", message_text, bot_message_id)
        return val

async def get_lead_message_by_bot_msg(user_id: int, bot_message_id: int) -> Optional[Dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM lead_messages WHERE user_id = $1 AND bot_message_id = $2 ORDER BY id DESC LIMIT 1",
            user_id, bot_message_id
        )
        return dict(row) if row else None

async def get_user_forward_account(user_id: int) -> str:
    pool = await get_pool()
    async with pool.acquire() as conn:
        val = await conn.fetchval(
            "SELECT forward_account FROM user_settings WHERE user_id = $1",
            user_id
        )
        return val or ""

async def set_user_forward_account(user_id: int, forward_acc: str):
    clean = forward_acc.replace("@", "").replace("https://t.me/", "").strip()
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE user_settings SET forward_account = $1 WHERE user_id = $2",
            clean or None, user_id
        )
    _cache_settings.pop(user_id, None)

# ─────────────────────────────────────────────────────────
# SYSTEM ACCOUNTS (LOG & MANAGER USERBOT LOGIN)
# ─────────────────────────────────────────────────────────
async def set_system_account(
    role: str,
    session_string: str,
    phone_number: str,
    account_name: str,
    username: str,
    tg_id: int
):
    clean_user = (username or "").replace("@", "").strip()
    _cache_system_accounts[role] = {
        "role": role,
        "session_string": session_string,
        "phone_number": phone_number,
        "account_name": account_name,
        "username": clean_user,
        "tg_id": tg_id
    }
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO system_accounts (role, session_string, phone_number, account_name, username, tg_id, updated_at)
            VALUES ($1, $2, $3, $4, $5, $6, NOW())
            ON CONFLICT (role) DO UPDATE SET
                session_string = EXCLUDED.session_string,
                phone_number   = EXCLUDED.phone_number,
                account_name   = EXCLUDED.account_name,
                username       = EXCLUDED.username,
                tg_id          = EXCLUDED.tg_id,
                updated_at     = NOW()
        """, role, session_string, phone_number, account_name, clean_user, tg_id)

async def get_system_account(role: str) -> Optional[Dict]:
    if role in _cache_system_accounts:
        return _cache_system_accounts[role]
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM system_accounts WHERE role = $1", role)
        res = dict(row) if row else None
        if res:
            _cache_system_accounts[role] = res
        return res

async def clear_system_account(role: str):
    _cache_system_accounts.pop(role, None)
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM system_accounts WHERE role = $1", role)

# ─────────────────────────────────────────────────────────
# MANDATORY USER MESSAGE VERIFICATION
# ─────────────────────────────────────────────────────────
async def mark_user_messaged_account(user_id: int, acc_type: str):
    """Marks that user has sent a message to Log or Manager account."""
    # Update RAM cache instantly (0ms)
    has_l, has_m = _cache_user_messaged.get(user_id, (False, False))
    if acc_type.lower() == "log":
        _cache_user_messaged[user_id] = (True, has_m)
    else:
        _cache_user_messaged[user_id] = (has_l, True)

    pool = await get_pool()
    col = "messaged_log" if acc_type.lower() == "log" else "messaged_manager"
    async with pool.acquire() as conn:
        await conn.execute(f"""
            INSERT INTO user_messaged_accounts (user_id, {col}, updated_at)
            VALUES ($1, 1, NOW())
            ON CONFLICT (user_id) DO UPDATE SET
                {col} = 1,
                updated_at = NOW()
        """, user_id)

async def has_user_messaged_accounts(user_id: int) -> Tuple[bool, bool]:
    """Returns (has_messaged_log: bool, has_messaged_manager: bool)."""
    if user_id in _cache_user_messaged:
        return _cache_user_messaged[user_id]
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT messaged_log, messaged_manager FROM user_messaged_accounts WHERE user_id = $1",
            user_id
        )
        res = (bool(row["messaged_log"]), bool(row["messaged_manager"])) if row else (False, False)
        _cache_user_messaged[user_id] = res
        return res



