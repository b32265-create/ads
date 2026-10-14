"""
Shadow Ads Bot - SQLite to PostgreSQL Data Migrator
===================================================
Run this script whenever you want to copy all existing data
from shadow_ads.db (SQLite) to your PostgreSQL database.

Usage:
    python migrate_sqlite_to_pg.py
"""

import asyncio
import logging
import sys
import aiosqlite
import asyncpg
from config import DB_PATH, DATABASE_URL

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("Migrator")

async def migrate():
    if not DATABASE_URL:
        logger.error("❌ DATABASE_URL is not set in .env! Please set your PostgreSQL URL in .env first.")
        return

    logger.info(f"📂 Reading from SQLite database: {DB_PATH}")
    logger.info("⚡ Connecting to PostgreSQL...")

    dsn = DATABASE_URL
    if dsn.startswith("postgres://"):
        dsn = dsn.replace("postgres://", "postgresql://", 1)

    try:
        pg_conn = await asyncpg.connect(dsn, statement_cache_size=0)
    except Exception as e:
        logger.error(f"❌ Failed to connect to PostgreSQL: {e}")
        return

    try:
        async with aiosqlite.connect(DB_PATH) as sqlite_conn:
            sqlite_conn.row_factory = aiosqlite.Row

            # 1. Initialize PG tables first
            import database_pg
            await database_pg.init_db()

            # 2. Migrate Users
            logger.info("Migrating users...")
            async with sqlite_conn.execute("SELECT * FROM users") as cursor:
                users = await cursor.fetchall()
                for u in users:
                    await pg_conn.execute("""
                        INSERT INTO users (user_id, username, first_name, is_banned, is_premium)
                        VALUES ($1, $2, $3, $4, $5)
                        ON CONFLICT (user_id) DO UPDATE
                        SET username = EXCLUDED.username,
                            first_name = EXCLUDED.first_name,
                            is_banned = EXCLUDED.is_banned,
                            is_premium = EXCLUDED.is_premium
                    """, u['user_id'], u['username'], u['first_name'], u['is_banned'], u['is_premium'])
            logger.info(f"✅ Migrated {len(users)} users.")

            # 3. Migrate User Settings
            logger.info("Migrating user settings...")
            async with sqlite_conn.execute("SELECT * FROM user_settings") as cursor:
                settings = await cursor.fetchall()
                for s in settings:
                    await pg_conn.execute("""
                        INSERT INTO user_settings (
                            user_id, ad_message, ad_media_id, ad_media_type,
                            cycle_interval, message_delay, target_type,
                            max_cycles, completed_cycles, status, ai_reply,
                            exclude_groups, schedule_start, schedule_end, schedule_enabled,
                            manager_enabled
                        )
                        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16)
                        ON CONFLICT (user_id) DO UPDATE SET
                            ad_message = EXCLUDED.ad_message,
                            ad_media_id = EXCLUDED.ad_media_id,
                            ad_media_type = EXCLUDED.ad_media_type,
                            cycle_interval = EXCLUDED.cycle_interval,
                            message_delay = EXCLUDED.message_delay,
                            target_type = EXCLUDED.target_type,
                            max_cycles = EXCLUDED.max_cycles,
                            completed_cycles = EXCLUDED.completed_cycles,
                            status = EXCLUDED.status,
                            ai_reply = EXCLUDED.ai_reply,
                            exclude_groups = EXCLUDED.exclude_groups,
                            schedule_start = EXCLUDED.schedule_start,
                            schedule_end = EXCLUDED.schedule_end,
                            schedule_enabled = EXCLUDED.schedule_enabled,
                            manager_enabled = EXCLUDED.manager_enabled
                    """,
                        s['user_id'], s['ad_message'], s['ad_media_id'], s['ad_media_type'],
                        s['cycle_interval'], s['message_delay'], s['target_type'],
                        s['max_cycles'], s['completed_cycles'], s['status'], s['ai_reply'],
                        s['exclude_groups'], s['schedule_start'], s['schedule_end'], s['schedule_enabled'],
                        s['manager_enabled'] if 'manager_enabled' in s.keys() else 1
                    )
            logger.info(f"✅ Migrated {len(settings)} user settings.")

            # 4. Migrate Accounts
            logger.info("Migrating accounts...")
            async with sqlite_conn.execute("SELECT * FROM accounts") as cursor:
                accounts = await cursor.fetchall()
                for a in accounts:
                    await pg_conn.execute("""
                        INSERT INTO accounts (
                            user_id, phone_number, session_string, account_name,
                            status, is_banned, total_sent, total_failed
                        )
                        VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                    """,
                        a['user_id'], a['phone_number'], a['session_string'],
                        a['account_name'], a['status'], a['is_banned'],
                        a['total_sent'], a['total_failed']
                    )
            logger.info(f"✅ Migrated {len(accounts)} accounts.")

            # 5. Migrate Force Join Channels
            logger.info("Migrating force join channels...")
            async with sqlite_conn.execute("SELECT * FROM force_join_channels") as cursor:
                channels = await cursor.fetchall()
                for ch in channels:
                    await pg_conn.execute("""
                        INSERT INTO force_join_channels (channel_id, title, invite_link, is_active)
                        VALUES ($1, $2, $3, $4)
                        ON CONFLICT (channel_id) DO UPDATE SET
                            title = EXCLUDED.title,
                            invite_link = EXCLUDED.invite_link,
                            is_active = EXCLUDED.is_active
                    """, str(ch['channel_id']), ch['title'], ch['invite_link'], ch['is_active'])
            logger.info(f"✅ Migrated {len(channels)} channels.")

            # 6. Migrate Analytics
            logger.info("Migrating analytics...")
            async with sqlite_conn.execute("SELECT * FROM analytics") as cursor:
                analytics = await cursor.fetchall()
                for an in analytics:
                    await pg_conn.execute("""
                        INSERT INTO analytics (user_id, total_sent, total_failed)
                        VALUES ($1, $2, $3)
                        ON CONFLICT (user_id) DO UPDATE SET
                            total_sent = EXCLUDED.total_sent,
                            total_failed = EXCLUDED.total_failed
                    """, an['user_id'], an['total_sent'], an['total_failed'])
            logger.info(f"✅ Migrated {len(analytics)} analytics records.")

            # 7. Migrate Bot Settings
            logger.info("Migrating bot settings...")
            async with sqlite_conn.execute("SELECT * FROM bot_settings") as cursor:
                settings_rows = await cursor.fetchall()
                for row in settings_rows:
                    await pg_conn.execute("""
                        INSERT INTO bot_settings (key, value)
                        VALUES ($1, $2)
                        ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
                    """, row['key'], row['value'])
            logger.info(f"✅ Migrated {len(settings_rows)} bot settings.")

        print("\n" + "="*50)
        print("[SUCCESS] SQLite to PostgreSQL Migration Completed Successfully!")
        print("="*50 + "\n")

    except Exception as e:
        logger.error(f"❌ Error during migration: {e}", exc_info=True)
    finally:
        await pg_conn.close()

if __name__ == "__main__":
    asyncio.run(migrate())
