import logging
from aiogram import Bot
from aiogram.enums import ChatMemberStatus
import database as db

logger = logging.getLogger(__name__)

async def check_user_force_join(bot: Bot, user_id: int):
    """
    Check if user is a member of all active force-join channels.
    Returns: (is_joined: bool, unjoined_channels: list)
    """
    channels = await db.get_active_force_channels()
    if not channels:
        return True, []

    unjoined = []
    for ch in channels:
        ch_id = ch["channel_id"]
        try:
            # Handle numeric IDs or @usernames
            target_id = int(ch_id) if (ch_id.startswith("-") or ch_id.isdigit()) else ch_id
            member = await bot.get_chat_member(chat_id=target_id, user_id=user_id)
            if member.status in [ChatMemberStatus.LEFT, ChatMemberStatus.KICKED]:
                unjoined.append(ch)
        except Exception as e:
            logger.warning(f"Could not verify membership for channel {ch_id}: {e}")
            # If bot cannot check (e.g. channel ID changed or bot is not admin), don't block user
            continue

    if unjoined:
        return False, unjoined
    return True, []
