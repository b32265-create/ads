import logging
from aiogram import Bot
from aiogram.enums import ChatMemberStatus
import database as db

import time
from typing import Tuple, List, Dict

logger = logging.getLogger(__name__)

# In-memory caches to eliminate unnecessary network & DB queries
_CHANNELS_CACHE: List[Dict] = []
_CHANNELS_CACHE_TIME: float = 0.0
_USER_JOIN_CACHE: Dict[int, float] = {}  # user_id -> timestamp when verified

async def get_cached_active_channels() -> List[Dict]:
    global _CHANNELS_CACHE, _CHANNELS_CACHE_TIME
    now = time.time()
    if now - _CHANNELS_CACHE_TIME > 30.0:  # 30-second TTL
        try:
            _CHANNELS_CACHE = await db.get_active_force_channels()
            _CHANNELS_CACHE_TIME = now
        except Exception:
            pass
    return _CHANNELS_CACHE

async def check_user_force_join(bot: Bot, user_id: int) -> Tuple[bool, list]:
    """
    Check if user is a member of all active force-join channels.
    Returns: (is_joined: bool, unjoined_channels: list)
    Uses 5-minute cache for already-verified users to make bot blazing fast.
    """
    channels = await get_cached_active_channels()
    if not channels:
        return True, []

    now = time.time()
    if user_id in _USER_JOIN_CACHE and (now - _USER_JOIN_CACHE[user_id] < 300.0):
        return True, []

    unjoined = []
    for ch in channels:
        ch_id = ch["channel_id"]
        try:
            target_id = int(ch_id) if (ch_id.startswith("-") or ch_id.isdigit()) else ch_id
            member = await bot.get_chat_member(chat_id=target_id, user_id=user_id)
            if member.status in [ChatMemberStatus.LEFT, ChatMemberStatus.KICKED]:
                unjoined.append(ch)
        except Exception as e:
            err_msg = str(e).lower()
            if "user not found" in err_msg or "participant" in err_msg:
                unjoined.append(ch)
            else:
                logger.warning(f"Could not verify membership for channel {ch_id}: {e}")
            continue

    if unjoined:
        _USER_JOIN_CACHE.pop(user_id, None)
        return False, unjoined

    _USER_JOIN_CACHE[user_id] = now
    return True, []
