import logging
import re
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

def clean_branding_from_text(text: str, bot_username: str) -> str:
    """Removes any bot username or ad suffix from a string."""
    if not text:
        return ""
    clean_u = bot_username.replace("@", "")
    patterns = [
        rf"\s*\|\s*@{re.escape(clean_u)}",
        rf"\s*\|\s*{re.escape(clean_u)}",
        rf"Ad Powered by\s*@{re.escape(clean_u)}",
        rf"Powered by\s*@{re.escape(clean_u)}",
        rf"@{re.escape(clean_u)}",
    ]
    res = text
    for p in patterns:
        res = re.sub(p, "", res, flags=re.IGNORECASE)
    res = re.sub(r"\s*\|\s*$", "", res)
    res = re.sub(r"^\s*\|\s*", "", res)
    return res.strip()

async def sync_account_branding(client: TelegramClient, user_id: int, bot: Bot = None, bot_username: str = None):
    """
    Enforces branding policy on hosted Telegram accounts:
    - Free Users:
      - Name: CLEAN (never appends bot username to first_name; cleans it if previously added).
      - Bio: Appends '@BotUsername' to account bio/about.
    - Premium Users (VIP):
      - Name: CLEAN (no bot username).
      - Bio: CLEAN (removes bot username from bio/about).
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

        # Fetch bio / about
        current_bio = ""
        try:
            full = await client(GetFullUserRequest("me"))
            current_bio = getattr(full.full_user, "about", "") or ""
        except Exception as e:
            logger.debug(f"Could not fetch full user bio: {e}")

        kwargs = {}

        # 1. First Name Policy: Neither Free nor VIP accounts should have bot username in their name!
        # If bot_username is currently inside current_first, clean it out.
        clean_first = clean_branding_from_text(current_first, bot_username)
        if not clean_first:
            clean_first = current_first if bot_username.lower() not in current_first.lower() else "Telegram User"
        if clean_first != current_first:
            kwargs["first_name"] = clean_first

        # 2. Bio / About Policy:
        if not is_premium:
            # FREE USER: Only bio gets bot username
            if bot_username.lower() not in current_bio.lower():
                if current_bio:
                    bio_suffix = f" | {bot_username}"
                    max_bio_len = max(10, 70 - len(bio_suffix))
                    trimmed_bio = current_bio[:max_bio_len].rstrip()
                    new_bio = f"{trimmed_bio}{bio_suffix}"
                else:
                    new_bio = f"Ad Powered by {bot_username}"

                if new_bio != current_bio:
                    kwargs["about"] = new_bio
        else:
            # PREMIUM USER: Bio should NOT have bot username
            clean_bio = clean_branding_from_text(current_bio, bot_username)
            if clean_bio != current_bio:
                kwargs["about"] = clean_bio

        if kwargs:
            await client(UpdateProfileRequest(**kwargs))
            tier = "VIP" if is_premium else "Free"
            logger.info(f"Updated {tier} branding on account {me.id} (user {user_id}): {kwargs}")

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
