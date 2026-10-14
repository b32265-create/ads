import aiosqlite
import json
import logging
from config import DB_PATH

logger = logging.getLogger(__name__)

async def init_db():
    """Initialize database tables and optimize SQLite settings with WAL mode."""
    async with aiosqlite.connect(DB_PATH) as db:
        # Enable WAL mode for high concurrency and speed
        await db.execute("PRAGMA journal_mode = WAL;")
        await db.execute("PRAGMA synchronous = NORMAL;")
        
        # 1. Users table
        await db.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_banned INTEGER DEFAULT 0,
            is_premium INTEGER DEFAULT 0,
            referred_by INTEGER DEFAULT NULL,
            referral_count INTEGER DEFAULT 0,
            premium_expires_at TEXT DEFAULT NULL
        );
        """)
        for col_def in [
            "referred_by INTEGER DEFAULT NULL",
            "referral_count INTEGER DEFAULT 0",
            "premium_expires_at TEXT DEFAULT NULL"
        ]:
            try:
                await db.execute(f"ALTER TABLE users ADD COLUMN {col_def};")
            except Exception:
                pass

        # 2. User Ad Settings table (with schedule + media support)
        await db.execute("""
        CREATE TABLE IF NOT EXISTS user_settings (
            user_id INTEGER PRIMARY KEY,
            ad_message TEXT DEFAULT NULL,
            ad_media_id TEXT DEFAULT NULL,
            ad_media_type TEXT DEFAULT NULL,
            cycle_interval INTEGER DEFAULT 0,
            message_delay INTEGER DEFAULT 5,
            target_type TEXT DEFAULT 'Groups',
            max_cycles INTEGER DEFAULT 0,
            completed_cycles INTEGER DEFAULT 0,
            status TEXT DEFAULT 'Paused',
            ai_reply INTEGER DEFAULT 0,
            exclude_groups TEXT DEFAULT '',
            schedule_start TEXT DEFAULT NULL,
            schedule_end TEXT DEFAULT NULL,
            schedule_enabled INTEGER DEFAULT 0,
            FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE
        );
        """)

        # 3. Hosted Telegram Accounts table (with ban tracking)
        await db.execute("""
        CREATE TABLE IF NOT EXISTS accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            phone_number TEXT,
            session_string TEXT,
            account_name TEXT,
            status TEXT DEFAULT 'active',
            is_banned INTEGER DEFAULT 0,
            total_sent INTEGER DEFAULT 0,
            total_failed INTEGER DEFAULT 0,
            last_used_at TIMESTAMP,
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE
        );
        """)

        # 4. Force Join Channels table (Admin manageable)
        await db.execute("""
        CREATE TABLE IF NOT EXISTS force_join_channels (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            channel_id TEXT UNIQUE,
            title TEXT,
            invite_link TEXT,
            is_active INTEGER DEFAULT 1
        );
        """)

        # 5. Global Bot Settings / Key-Value table
        await db.execute("""
        CREATE TABLE IF NOT EXISTS bot_settings (
            key TEXT PRIMARY KEY,
            value TEXT
        );
        """)

        # 6. Analytics table
        await db.execute("""
        CREATE TABLE IF NOT EXISTS analytics (
            user_id INTEGER PRIMARY KEY,
            total_sent INTEGER DEFAULT 0,
            total_failed INTEGER DEFAULT 0,
            last_sent_at TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE
        );
        """)

        # Safe migration: add new columns if they don't exist (for existing DBs)
        migration_columns = [
            ("user_settings", "schedule_start", "TEXT DEFAULT NULL"),
            ("user_settings", "schedule_end", "TEXT DEFAULT NULL"),
            ("user_settings", "schedule_enabled", "INTEGER DEFAULT 0"),
            ("accounts", "is_banned", "INTEGER DEFAULT 0"),
            ("accounts", "total_sent", "INTEGER DEFAULT 0"),
            ("accounts", "total_failed", "INTEGER DEFAULT 0"),
            ("accounts", "last_used_at", "TIMESTAMP"),
        ]
        for table, col, col_def in migration_columns:
            try:
                await db.execute(f"ALTER TABLE {table} ADD COLUMN {col} {col_def}")
            except Exception:
                pass  # Column already exists

        await db.commit()
    logger.info("Database initialized successfully with WAL mode!")

# --- USER OPERATIONS ---
async def get_or_create_user(user_id: int, username: str = None, first_name: str = None):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)) as cursor:
            user = await cursor.fetchone()
            if not user:
                await db.execute(
                    "INSERT INTO users (user_id, username, first_name) VALUES (?, ?, ?)",
                    (user_id, username, first_name)
                )
                await db.execute(
                    "INSERT OR IGNORE INTO user_settings (user_id) VALUES (?)",
                    (user_id,)
                )
                await db.execute(
                    "INSERT OR IGNORE INTO analytics (user_id) VALUES (?)",
                    (user_id,)
                )
                await db.commit()
            else:
                # Update info if changed
                await db.execute(
                    "UPDATE users SET username = ?, first_name = ? WHERE user_id = ?",
                    (username, first_name, user_id)
                )
                await db.commit()

async def get_all_user_ids():
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT user_id FROM users WHERE is_banned = 0") as cursor:
            rows = await cursor.fetchall()
            return [r[0] for r in rows]

async def get_user_count():
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM users") as cursor:
            row = await cursor.fetchone()
            return row[0] if row else 0

async def get_premium_user_count():
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM users WHERE is_premium = 1") as cursor:
            row = await cursor.fetchone()
            return row[0] if row else 0

async def get_banned_user_count():
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM users WHERE is_banned = 1") as cursor:
            row = await cursor.fetchone()
            return row[0] if row else 0

async def get_user_info(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

async def set_user_banned(user_id: int, banned: bool):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET is_banned = ? WHERE user_id = ?", (1 if banned else 0, user_id))
        await db.commit()

async def set_user_premium(user_id: int, premium: bool):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET is_premium = ? WHERE user_id = ?", (1 if premium else 0, user_id))
        await db.commit()

async def get_all_users_list(limit: int = 50, offset: int = 0):
    """Get paginated list of users for admin panel."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM users ORDER BY joined_at DESC LIMIT ? OFFSET ?",
            (limit, offset)
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

async def search_user_by_id_or_username(query: str):
    """Search user by user_id or @username."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        q = query.lstrip('@')
        async with db.execute(
            "SELECT * FROM users WHERE CAST(user_id AS TEXT) = ? OR username = ? LIMIT 1",
            (q, q)
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

async def get_total_active_campaigns():
    """Count users with status=Running."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM user_settings WHERE status = 'Running'") as cursor:
            row = await cursor.fetchone()
            return row[0] if row else 0

async def get_global_total_sent():
    """Sum of all ads sent across all users."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COALESCE(SUM(total_sent), 0) FROM analytics") as cursor:
            row = await cursor.fetchone()
            return row[0] if row else 0

async def get_total_accounts():
    """Total hosted accounts count."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM accounts WHERE status = 'active'") as cursor:
            row = await cursor.fetchone()
            return row[0] if row else 0

# --- USER SETTINGS OPERATIONS ---
async def get_user_settings(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM user_settings WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            if not row:
                await db.execute("INSERT OR IGNORE INTO user_settings (user_id) VALUES (?)", (user_id,))
                await db.commit()
                async with db.execute("SELECT * FROM user_settings WHERE user_id = ?", (user_id,)) as c2:
                    row = await c2.fetchone()
            return dict(row) if row else {}

async def update_user_setting(user_id: int, key: str, value):
    allowed_keys = {
        'ad_message', 'ad_media_id', 'ad_media_type', 'cycle_interval',
        'message_delay', 'target_type', 'max_cycles', 'completed_cycles',
        'status', 'ai_reply', 'exclude_groups',
        'schedule_start', 'schedule_end', 'schedule_enabled'
    }
    if key not in allowed_keys:
        raise ValueError(f"Invalid setting key: {key}")
    
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(f"UPDATE user_settings SET {key} = ? WHERE user_id = ?", (value, user_id))
        await db.commit()

# --- ACCOUNTS OPERATIONS ---
async def add_account(user_id: int, phone_number: str, session_string: str, account_name: str = ""):
    async with aiosqlite.connect(DB_PATH) as db:
        # Check if already exists for this user
        async with db.execute(
            "SELECT id FROM accounts WHERE user_id = ? AND phone_number = ?", 
            (user_id, phone_number)
        ) as cursor:
            existing = await cursor.fetchone()
            if existing:
                await db.execute(
                    "UPDATE accounts SET session_string = ?, account_name = ?, status = 'active' WHERE id = ?",
                    (session_string, account_name, existing[0])
                )
                await db.commit()
                return existing[0]

        cursor = await db.execute(
            "INSERT INTO accounts (user_id, phone_number, session_string, account_name) VALUES (?, ?, ?, ?)",
            (user_id, phone_number, session_string, account_name)
        )
        await db.commit()
        return cursor.lastrowid

async def get_user_accounts(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM accounts WHERE user_id = ? AND is_banned = 0", (user_id,)) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

async def get_user_accounts_all(user_id: int):
    """Get all accounts including banned ones (for display)."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM accounts WHERE user_id = ?", (user_id,)) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

async def get_all_active_accounts():
    """Get ALL active, non-banned accounts across all users for admin mass tasks."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM accounts WHERE status = 'active' AND is_banned = 0 ORDER BY id ASC") as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

async def get_account_count(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM accounts WHERE user_id = ? AND status = 'active' AND is_banned = 0", (user_id,)) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else 0

async def mark_account_banned(account_id: int):
    """Mark an account as banned due to Telegram ban."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE accounts SET is_banned = 1, status = 'banned' WHERE id = ?", (account_id,))
        await db.commit()

async def update_account_stats(account_id: int, sent: int = 0, failed: int = 0):
    """Update per-account sent/failed stats and last_used_at."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE accounts SET total_sent = total_sent + ?, total_failed = total_failed + ?, last_used_at = CURRENT_TIMESTAMP WHERE id = ?",
            (sent, failed, account_id)
        )
        await db.commit()

async def delete_account_by_id(account_id: int, user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM accounts WHERE id = ? AND user_id = ?", (account_id, user_id))
        await db.commit()

async def delete_all_user_accounts(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM accounts WHERE user_id = ?", (user_id,))
        await db.commit()

# --- FORCE JOIN CHANNELS OPERATIONS ---
async def add_force_channel(channel_id: str, title: str, invite_link: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO force_join_channels (channel_id, title, invite_link, is_active)
            VALUES (?, ?, ?, 1)
            ON CONFLICT (channel_id) DO UPDATE SET title = EXCLUDED.title, invite_link = EXCLUDED.invite_link, is_active = 1
        """, (str(channel_id), title, invite_link))
        await db.commit()

async def get_active_force_channels():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM force_join_channels WHERE is_active = 1") as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

async def remove_force_channel(channel_id: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM force_join_channels WHERE channel_id = ?", (str(channel_id),))
        await db.commit()

# --- ANALYTICS OPERATIONS ---
async def get_analytics(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM analytics WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else {"total_sent": 0, "total_failed": 0}

async def increment_analytics(user_id: int, sent_count: int = 1, failed_count: int = 0):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            UPDATE analytics 
            SET total_sent = total_sent + ?, 
                total_failed = total_failed + ?,
                last_sent_at = CURRENT_TIMESTAMP
            WHERE user_id = ?
        """, (sent_count, failed_count, user_id))
        await db.commit()

# --- BOT GLOBAL SETTINGS ---
async def get_bot_setting(key: str, default=None):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT value FROM bot_settings WHERE key = ?", (key,)) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else default

async def set_bot_setting(key: str, value: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO bot_settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = EXCLUDED.value",
            (key, str(value))
        )
        await db.commit()

async def get_all_bot_settings():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT key, value FROM bot_settings") as cursor:
            rows = await cursor.fetchall()
            return {r['key']: r['value'] for r in rows}

# --- REFERRAL & REWARD OPERATIONS ---
async def record_user_referral(new_user_id: int, referrer_id: int):
    if new_user_id == referrer_id:
        return False, 0, False
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT user_id FROM users WHERE user_id = ?", (referrer_id,)) as cur:
            if not await cur.fetchone():
                return False, 0, False

        async with db.execute("SELECT referred_by FROM users WHERE user_id = ?", (new_user_id,)) as cur:
            row = await cur.fetchone()
            if row and row[0] is not None:
                return False, 0, False

        await db.execute("UPDATE users SET referred_by = ? WHERE user_id = ?", (referrer_id, new_user_id))
        await db.execute("UPDATE users SET referral_count = COALESCE(referral_count, 0) + 1 WHERE user_id = ?", (referrer_id,))
        await db.commit()

        async with db.execute("SELECT referral_count, is_premium FROM users WHERE user_id = ?", (referrer_id,)) as cur:
            row = await cur.fetchone()
            new_count = row[0] if row else 0
            is_prem = row[1] if row else 0

        unlocked = False
        if new_count >= 5 and is_prem == 0:
            await db.execute("UPDATE users SET is_premium = 1 WHERE user_id = ?", (referrer_id,))
            await db.commit()
            unlocked = True

        return True, new_count, unlocked

async def get_user_referral_stats(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT referral_count, referred_by, is_premium, premium_expires_at FROM users WHERE user_id = ?", (user_id,)) as cur:
            row = await cur.fetchone()
            if row:
                return dict(row)
            return {"referral_count": 0, "referred_by": None, "is_premium": 0, "premium_expires_at": None}

async def set_user_premium_status(user_id: int, is_premium: int = 1, days=None):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET is_premium = ? WHERE user_id = ?", (is_premium, user_id))
        await db.commit()

# --- LOG ACCOUNT OPERATIONS ---
async def get_log_account():
    val = await get_bot_setting("log_account_username", "")
    return val or ""

async def set_log_account(username: str):
    clean = username.replace("@", "").replace("https://t.me/", "").strip()
    await set_bot_setting("log_account_username", clean)

async def close_pool():
    """No-op for SQLite engine."""
    pass
