import logging
import asyncio
from typing import Dict, Optional
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from aiogram import Bot

import database as db
from config import API_ID, API_HASH

logger = logging.getLogger("ShadowAdsBot.SystemClients")

# Live running clients for 'log' and 'manager' roles
_SYSTEM_CLIENTS: Dict[str, TelegramClient] = {}


def get_system_client(role: str) -> Optional[TelegramClient]:
    return _SYSTEM_CLIENTS.get(role)


async def start_system_client(role: str, session_str: str, bot: Bot = None) -> Optional[TelegramClient]:
    """
    Connects the official Log or Manager account userbot,
    and sets up the automatic activation listener when users message it.
    """
    if not session_str:
        return None

    # Disconnect any old instance first
    await stop_system_client(role)

    try:
        client = TelegramClient(StringSession(session_str), API_ID, API_HASH)
        await client.connect()
        if not await client.is_user_authorized():
            logger.warning(f"System account for role '{role}' is not authorized.")
            return None

        me = await client.get_me()
        logger.info(f"Connected system client '{role}' as @{me.username or me.phone or me.id}")

        @client.on(events.NewMessage(incoming=True, func=lambda e: e.is_private))
        async def on_private_msg(event):
            try:
                sender = await event.get_sender()
                if not sender or getattr(sender, "bot", False) or getattr(sender, "is_self", False):
                    return
                if sender.id in (777000, 42777):
                    return

                sender_id = sender.id
                first_name = getattr(sender, "first_name", "") or "User"

                # Mark in database that this user has messaged this account!
                await db.mark_user_messaged_account(sender_id, role)
                logger.info(f"User {sender_id} ({first_name}) successfully activated connection with {role} account!")

                # Send friendly confirmation greeting to the user
                if role == "log":
                    reply_txt = (
                        f"📡 <b>[LIVE DELIVERY LOGS ACTIVATED]</b> 🐲\n\n"
                        f"Namaste <b>{first_name}</b>! Aapka account live logs ke liye successfully link ho gaya hai.\n"
                        f"Aapke automated ad campaigns ke delivery logs yahan aane lagenge.\n\n"
                        f"👉 <i>Ab bot me jakar 'Verified / Continue' par click karein!</i>"
                    )
                else:
                    reply_txt = (
                        f"👤 <b>[LEAD DM MANAGER ACTIVATED]</b> ⚡\n\n"
                        f"Namaste <b>{first_name}</b>! Aapka account lead inquiries relay ke liye link ho gaya hai.\n"
                        f"Alt accounts ke saare lead inquiries aur two-way responses yahan sync honge.\n\n"
                        f"👉 <i>Ab bot me jakar 'Verified / Continue' par click karein!</i>"
                    )

                try:
                    await event.reply(reply_txt, parse_mode="html")
                except Exception:
                    pass

            except Exception as e:
                logger.error(f"Error handling message on system client '{role}': {e}")

        _SYSTEM_CLIENTS[role] = client
        return client

    except Exception as e:
        logger.error(f"Failed to start system client '{role}': {e}")
        return None


async def stop_system_client(role: str):
    """Disconnects and removes system client."""
    client = _SYSTEM_CLIENTS.pop(role, None)
    if client:
        try:
            if client.is_connected():
                await client.disconnect()
            logger.info(f"Disconnected system client '{role}'")
        except Exception as e:
            logger.warning(f"Error disconnecting system client '{role}': {e}")


async def init_system_clients(bot: Bot):
    """Initializes both log and manager clients from database on startup."""
    for role in ["log", "manager"]:
        acc = await db.get_system_account(role)
        if acc and acc.get("session_string"):
            logger.info(f"Initializing saved system account for '{role}'...")
            await start_system_client(role, acc["session_string"], bot)
