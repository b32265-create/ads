import logging
from telethon import TelegramClient
from telethon.tl.functions.account import UpdateProfileRequest
from telethon.tl.functions.users import GetFullUserRequest
from aiogram import Bot
import database as db

logger = logging.getLogger("Bot.AccountBranding")

_CACHED_BOT_USERNAME = ""

async def get_cached_bot_username(bot: Bot = None) -> str:
    global _CACHED_BOT_USERNAME
    if not _CACHED_BOT_USERNAME and bot:
        try:
            me = await bot.get_me()
            if me and me.username:
                _CACHED_BOT_USERNAME = me.username
        except Exception:
            pass
    if not _CACHED_BOT_USERNAME:
        _CACHED_BOT_USERNAME = "Atomic_Ads_Robot"
    return _CACHED_BOT_USERNAME

async def sync_account_branding(client: TelegramClient, user_id: int, bot: Bot = None, bot_username: str = None):
    """
    Enforces branding policy on hosted Telegram accounts:
    - If user is NOT premium (Free User):
      - Appends '@BotUsername' to account's Telegram first_name.
      - Adds '@BotUsername' into account's Telegram bio/about.
    - If user IS premium (VIP User):
      - Removes '@BotUsername' from first_name and bio/about.
    """
    if not client or not await client.is_user_authorized():
        return

    try:
        if not bot_username:
            b_name = await get_cached_bot_username(bot)
            bot_username = f"@{b_name.replace('@', '')}"
        elif not bot_username.startswith("@"):
            bot_username = f"@{bot_username}"

        user_info = await db.get_user_info(user_id)
        is_premium = bool(user_info and user_info.get("is_premium", 0))

        me = await client.get_me()
        current_first = me.first_name or ""
        current_last = me.last_name or ""

        # Fetch bio / about
        current_bio = ""
        try:
            full = await client(GetFullUserRequest("me"))
            current_bio = getattr(full.full_user, "about", "") or ""
        except Exception as e:
            logger.debug(f"Could not fetch full user bio: {e}")

        suffix = f" | {bot_username}"

        if not is_premium:
            # FREE USER: Add branding
            new_first = None
            if bot_username.lower() not in current_first.lower() and bot_username.lower() not in current_last.lower():
                max_name_len = max(10, 64 - len(suffix))
                trimmed_orig = current_first[:max_name_len].rstrip()
                new_first = f"{trimmed_orig}{suffix}"

            new_bio = None
            if bot_username.lower() not in current_bio.lower():
                if current_bio:
                    bio_suffix = f" | {bot_username}"
                    max_bio_len = max(10, 70 - len(bio_suffix))
                    trimmed_bio = current_bio[:max_bio_len].rstrip()
                    new_bio = f"{trimmed_bio}{bio_suffix}"
                else:
                    new_bio = f"Ad Powered by {bot_username}"

            kwargs = {}
            if new_first is not None and new_first != current_first:
                kwargs["first_name"] = new_first
            if new_bio is not None and new_bio != current_bio:
                kwargs["about"] = new_bio

            if kwargs:
                await client(UpdateProfileRequest(**kwargs))
                logger.info(f"Applied free-tier branding to account {me.id} (user {user_id}): {kwargs}")

        else:
            # PREMIUM USER: Remove branding
            new_first = None
            if bot_username.lower() in current_first.lower():
                cleaned = current_first
                for pattern in [f" | {bot_username}", f"| {bot_username}", f"|{bot_username}", bot_username]:
                    cleaned = cleaned.replace(pattern, "").strip()
                if not cleaned:
                    cleaned = "Telegram User"
                new_first = cleaned

            new_bio = None
            if bot_username.lower() in current_bio.lower():
                cleaned_bio = current_bio
                for pattern in [f"Ad Powered by {bot_username}", f" | {bot_username}", f"| {bot_username}", f"|{bot_username}", bot_username]:
                    cleaned_bio = cleaned_bio.replace(pattern, "").strip()
                new_bio = cleaned_bio

            kwargs = {}
            if new_first is not None and new_first != current_first:
                kwargs["first_name"] = new_first
            if new_bio is not None and new_bio != current_bio:
                kwargs["about"] = new_bio

            if kwargs:
                await client(UpdateProfileRequest(**kwargs))
                logger.info(f"Cleaned VIP branding from account {me.id} (user {user_id}): {kwargs}")

    except Exception as e:
        logger.warning(f"Profile branding sync skipped/failed for user {user_id}: {e}")

async def sync_all_user_accounts_branding(user_id: int, bot: Bot = None):
    """Syncs branding across all accounts of a user (e.g. after purchasing VIP)."""
    try:
        accounts = await db.get_user_accounts(user_id)
        if not accounts:
            return
        from config import API_ID, API_HASH
        from telethon.sessions import StringSession
        for acc in accounts:
            session_str = acc.get("session_string")
            if not session_str:
                continue
            try:
                client = TelegramClient(StringSession(session_str), API_ID, API_HASH)
                await client.connect()
                if await client.is_user_authorized():
                    await sync_account_branding(client, user_id, bot=bot)
                await client.disconnect()
            except Exception as e:
                logger.debug(f"Could not batch sync account {acc.get('id')}: {e}")
    except Exception as e:
        logger.warning(f"Batch account sync error for user {user_id}: {e}")
