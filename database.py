"""
Shadow Ads Bot - Universal Database Adapter
===========================================
Automatically detects database backend:
- If DATABASE_URL is set in .env -> uses PostgreSQL (asyncpg with connection pool, 500+ accounts support)
- If DATABASE_URL is empty -> uses SQLite with WAL mode (low memory, auto-fallback)
"""
import logging
from config import DATABASE_URL

logger = logging.getLogger("ShadowAdsBot.DB")

if DATABASE_URL:
    logger.info("🚀 [DB Engine] PostgreSQL active (asyncpg connection pool, 500+ accounts support)")
    from database_pg import *
else:
    logger.info("📁 [DB Engine] SQLite active (WAL mode enabled)")
    from database_sqlite import *
