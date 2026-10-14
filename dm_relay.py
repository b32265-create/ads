import logging
import asyncio
from typing import Dict, Optional
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from aiogram import Bot

import database as db
from config import API_ID, API_HASH
from emojis import EMOJI_MSG, EMOJI_STAR, EMOJI_FIRE, EMOJI_VERIFIED

logger = logging.getLogger("ShadowAdsBot.DMRelay")

# In-memory pool of active running Telethon clients: account_id -> TelegramClient
_ACTIVE_CLIENTS: Dict[int, TelegramClient] = {}

# Fast in-memory lookup for reply mapping: (user_id, bot_message_id) -> dict(account_id, lead_id, alt_username, lead_name)
_REPLY_CACHE: Dict[str, dict] = {}


def get_active_client(account_id: int) -> Optional[TelegramClient]:
    return _ACTIVE_CLIENTS.get(account_id)


async def get_or_create_client(account_dict: dict) -> Optional[TelegramClient]:
    """Get existing connected client or create a new one."""
    acc_id = account_dict.get("id")
    if acc_id in _ACTIVE_CLIENTS:
        client = _ACTIVE_CLIENTS[acc_id]
        if client.is_connected():
            return client

    session_str = account_dict.get("session_string")
    if not session_str:
        return None

    try:
        client = TelegramClient(StringSession(session_str), API_ID, API_HASH)
        await client.connect()
        if not await client.is_user_authorized():
            logger.warning(f"Account {acc_id} is not authorized.")
            return None
        _ACTIVE_CLIENTS[acc_id] = client
        return client
    except Exception as e:
        logger.error(f"Error connecting client for account {acc_id}: {e}")
        return None


async def start_account_dm_listener(account_dict: dict, bot: Bot):
    """
    Connects a client for the account and listens for incoming private messages (DMs from leads).
    When a DM arrives:
    1. Forwards it to Customer's Main Account (if configured).
    2. Sends an interactive notification to the Customer in the Bot chat.
    3. Logs it to the Admin Manager Account (if configured).
    """
    acc_id = account_dict.get("id")
    user_id = account_dict.get("user_id")
    session_str = account_dict.get("session_string")

    if not acc_id or not user_id or not session_str:
        return

    client = await get_or_create_client(account_dict)
    if not client:
        return

    # Check if handler already registered on this client to avoid duplicates
    if getattr(client, "_dm_listener_registered", False):
        return
    client._dm_listener_registered = True

    alt_username = account_dict.get("username") or account_dict.get("phone_number") or f"Account_{acc_id}"

    @client.on(events.NewMessage(incoming=True, func=lambda e: e.is_private))
    async def incoming_dm_handler(event):
        try:
            sender = await event.get_sender()
            if not sender or getattr(sender, "bot", False) or getattr(sender, "is_self", False):
                return
            
            # Ignore official Telegram service notifications (777000, 42777)
            if sender.id in (777000, 42777):
                return

            lead_id = sender.id
            lead_name = (getattr(sender, "first_name", "") or "") + " " + (getattr(sender, "last_name", "") or "")
            lead_name = lead_name.strip() or "Telegram User"
            lead_username = getattr(sender, "username", "") or ""
            text = event.raw_text or "[Non-text message / Media]"

            logger.info(f"Incoming DM on Alt @{alt_username} from {lead_name} ({lead_id}): {text[:50]}")

            # 1. Forward directly to Customer's Main Personal Account (if set)
            forward_acc = await db.get_user_forward_account(user_id)
            if forward_acc:
                try:
                    target_dest = int(forward_acc) if (forward_acc.startswith("-") or forward_acc.isdigit()) else forward_acc
                    await event.forward_to(target_dest)
                    logger.info(f"Forwarded DM to customer's main account: {forward_acc}")
                except Exception as e:
                    logger.warning(f"Could not forward message to main account {forward_acc}: {e}")

            # 2. Build interactive message for Customer in the Bot
            lead_user_link = f"@{lead_username}" if lead_username else f"<a href='tg://user?id={lead_id}'>{lead_name}</a>"
            notify_text = (
                f"╔══════════════════════════╗\n"
                f"  💬 <b>NEW LEAD INQUIRY RECEIVED!</b>\n"
                f"╚══════════════════════════╝\n"
                f"📱 <b>Ads Account:</b> <code>@{alt_username}</code>\n"
                f"👤 <b>From Lead:</b> {lead_user_link} [ID: <code>{lead_id}</code>]\n"
                f"━━━━━━━━━━━━━━━━━━━━━\n"
                f"📝 <b>Message:</b>\n"
                f"<blockquote>{text}</blockquote>\n"
                f"━━━━━━━━━━━━━━━━━━━━━\n"
                f"↩️ <b>Reply Kaise Karein:</b>\n"
                f"<i>Aap bas <b>is message par Reply / Tag</b> karein apna message likh kar — aapka jawab direct @{alt_username} se is lead ko chala jayega!</i>"
            )

            try:
                bot_msg = await bot.send_message(
                    chat_id=user_id,
                    text=notify_text,
                    parse_mode="HTML"
                )

                # Store mapping in DB & Memory Cache
                cache_key = f"{user_id}_{bot_msg.message_id}"
                mapping = {
                    "account_id": acc_id,
                    "lead_id": lead_id,
                    "alt_username": alt_username,
                    "lead_name": lead_name,
                    "lead_username": lead_username
                }
                _REPLY_CACHE[cache_key] = mapping

                await db.save_lead_message(
                    user_id=user_id,
                    account_id=acc_id,
                    alt_username=alt_username,
                    lead_id=lead_id,
                    lead_username=lead_username,
                    lead_name=lead_name,
                    message_text=text,
                    bot_message_id=bot_msg.message_id
                )
            except Exception as e:
                logger.error(f"Failed to send lead notification to user {user_id}: {e}")

            # 3. Log to Admin Manager Account if configured and user has manager_enabled != 0
            user_settings = await db.get_user_settings(user_id)
            if user_settings.get("manager_enabled", 1):
                manager_acc = await db.get_manager_account()
                if manager_acc:
                    try:
                        # If manager is numeric ID or username
                        manager_dest = int(manager_acc) if (manager_acc.startswith("-") or manager_acc.isdigit()) else manager_acc
                        mgr_text = (
                            f"📡 <b>[MANAGER LEAD LOG]</b>\n"
                            f"• <b>Customer ID:</b> <code>{user_id}</code>\n"
                            f"• <b>Ads Account:</b> @{alt_username}\n"
                            f"• <b>Lead:</b> {lead_user_link} (ID: <code>{lead_id}</code>)\n"
                            f"• <b>Message:</b> {text}"
                        )
                        await bot.send_message(manager_dest, mgr_text, parse_mode="HTML")
                    except Exception:
                        pass

        except Exception as e:
            logger.error(f"Error processing incoming DM on account {acc_id}: {e}")


async def send_reply_from_alt(
    user_id: int,
    bot_message_id: int,
    reply_text: str,
    bot: Bot = None,
    media_file=None
) -> tuple[bool, str]:
    """
    Looks up which alt account and lead received the original message,
    and sends the customer's response directly from that alt account.
    """
    cache_key = f"{user_id}_{bot_message_id}"
    mapping = _REPLY_CACHE.get(cache_key)

    if not mapping:
        # Fallback to DB query
        lead_row = await db.get_lead_message_by_bot_msg(user_id, bot_message_id)
        if lead_row:
            mapping = {
                "account_id": lead_row["account_id"],
                "lead_id": lead_row["lead_id"],
                "alt_username": lead_row["alt_username"],
                "lead_name": lead_row["lead_name"],
                "lead_username": lead_row.get("lead_username", "")
            }
            _REPLY_CACHE[cache_key] = mapping

    if not mapping:
        return False, "Yeh message kisi lead inquiry se linked nahi hai ya link expire ho chuka hai."

    account_id = mapping["account_id"]
    lead_id = mapping["lead_id"]
    alt_username = mapping["alt_username"]
    lead_name = mapping["lead_name"]

    account_dict = await db.get_account_by_id(account_id)
    if not account_dict:
        return False, f"Ads account @{alt_username} system me nahi mila."

    client = await get_or_create_client(account_dict)
    if not client or not client.is_connected():
        return False, f"Ads account @{alt_username} connect nahi ho paya. Kripya account status check karein."

    try:
        if media_file:
            await client.send_file(lead_id, file=media_file, caption=reply_text or None)
        else:
            await client.send_message(lead_id, reply_text)
        
        logger.info(f"Delivered reply to {lead_id} via @{alt_username}")
        return True, f"Aapka reply <b>{lead_name}</b> ko <b>@{alt_username}</b> se successfully deliver ho gaya!"
    except Exception as e:
        logger.error(f"Failed to deliver reply to {lead_id} from @{alt_username}: {e}")
        return False, f"Reply deliver nahi ho paya: {e}"


async def init_all_active_dm_listeners(bot: Bot):
    """
    Initializes DM listeners for all active accounts in background.
    Safe to call on bot startup.
    """
    try:
        active_accounts = await db.get_all_active_accounts()
        logger.info(f"Initializing DM relay listeners for {len(active_accounts)} active accounts...")
        for acc in active_accounts:
            try:
                await start_account_dm_listener(acc, bot)
            except Exception as e:
                logger.warning(f"Could not start listener for account {acc.get('id')}: {e}")
    except Exception as e:
        logger.error(f"Error initializing DM relay listeners: {e}")
