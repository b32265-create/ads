import logging
import asyncio
import os
from datetime import datetime, time as dtime
from typing import Dict, Optional, Tuple, List
from aiogram import Router, F, Bot
from aiogram.types import CallbackQuery, Message
from aiogram.filters import Command
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import (
    FloodWaitError, UserBannedInChannelError, ChatWriteForbiddenError,
    UserDeactivatedBanError, AuthKeyUnregisteredError, UserDeactivatedError,
    SessionRevokedError
)

import database as db
import keyboards as kb
from config import API_ID, API_HASH
from handlers.user import show_dashboard
from dm_relay import get_or_create_client
from system_clients import get_system_client
from emojis import (
    EMOJI_WARNING, EMOJI_MOON, EMOJI_VERIFIED, EMOJI_CROSS, EMOJI_STATS,
    EMOJI_FIRE, EMOJI_CLOCK, EMOJI_ROCKET, EMOJI_PLANE, EMOJI_TARGET
)

logger = logging.getLogger(__name__)

router = Router(name="ads_worker_router")

# Active running background tasks by user_id
active_ad_tasks: Dict[int, asyncio.Task] = {}

# Errors that indicate the account is banned/dead
ACCOUNT_DEAD_ERRORS = (
    UserDeactivatedBanError,
    UserDeactivatedError,
    AuthKeyUnregisteredError,
    SessionRevokedError,
)

def is_within_schedule(start_str: str, end_str: str) -> bool:
    """Check if current time is within the scheduled window (HH:MM format)."""
    try:
        now = datetime.now().time()
        start = dtime(int(start_str[:2]), int(start_str[3:5]))
        end = dtime(int(end_str[:2]), int(end_str[3:5]))
        if start <= end:
            return start <= now <= end
        else:
            # Overnight schedule (e.g., 22:00 to 06:00)
            return now >= start or now <= end
    except Exception:
        return True  # If parse fails, allow running

async def send_ad_to_dialog(
    client: TelegramClient,
    dialog,
    settings: dict,
    local_media_path: Optional[str] = None
) -> bool:
    """
    Send ad (text or media) to a single dialog.
    Supports native HTML formatting, custom premium emojis (<tg-emoji>), and standard text.
    Passes dialog.input_entity directly to avoid entity resolution latency.
    """
    ad_message = settings.get("ad_message") or ""
    target_peer = getattr(dialog, "input_entity", None) or getattr(dialog, "entity", None) or dialog

    media_to_send = local_media_path
    if not media_to_send and settings.get("ad_media_id"):
        cand = settings.get("ad_media_id")
        if os.path.exists(cand):
            media_to_send = cand

    if media_to_send and os.path.exists(media_to_send):
        try:
            await client.send_file(
                target_peer,
                file=media_to_send,
                caption=ad_message or None,
                parse_mode='html'
            )
        except Exception:
            try:
                await client.send_file(
                    target_peer,
                    file=media_to_send,
                    caption=ad_message or None
                )
            except Exception:
                # Fallback to plain text message if media sending is disabled/restricted in this chat
                if ad_message:
                    try:
                        await client.send_message(target_peer, ad_message, parse_mode='html')
                    except Exception:
                        await client.send_message(target_peer, ad_message)
                else:
                    raise
    else:
        try:
            await client.send_message(target_peer, ad_message, parse_mode='html')
        except Exception:
            await client.send_message(target_peer, ad_message)
    return True


async def run_single_account_ads(
    bot: Bot,
    user_id: int,
    acc: dict,
    settings: dict,
    local_media_path: Optional[str] = None
) -> Tuple[int, int, Optional[str]]:
    """
    Broadcasts ads to groups/channels for a single account.
    Reuses persistent client from dm_relay to achieve instant zero-latency message start.
    """
    current_st = await db.get_user_settings(user_id)
    if current_st.get("status", "Paused").lower() != "running":
        return 0, 0, None

    session_str = acc.get("session_string")
    if not session_str:
        return 0, 0, None

    acc_id = acc.get("id")
    acc_name = acc.get("account_name") or acc.get("phone_number") or f"Account_{acc_id}"
    acc_sent = 0
    acc_failed = 0
    client = None
    created_here = False

    try:
        # Re-use active running client from dm_relay for instant start
        client = await get_or_create_client(acc)
        if not client or not client.is_connected():
            client = TelegramClient(StringSession(session_str), API_ID, API_HASH)
            await client.connect()
            created_here = True

        if not await client.is_user_authorized():
            logger.warning(f"Account {acc_name} not authorized, marking banned")
            await db.mark_account_banned(acc_id)
            return 0, 0, acc_name

        target_type = settings.get("target_type", "Groups").lower()
        excluded_raw = settings.get("exclude_groups", "") or ""
        excluded = [x.strip().lower() for x in excluded_raw.split(",") if x.strip()]
        delay = max(settings.get("message_delay", 5), 1)

        # Iterate over dialogs (groups/supergroups/channels)
        async for dialog in client.iter_dialogs(limit=200):
            # Verify cancellation in real time
            c_chk = await db.get_user_settings(user_id)
            if c_chk.get("status", "Paused").lower() != "running":
                break

            # Target filter
            is_group = dialog.is_group
            is_channel = dialog.is_channel and not dialog.is_group

            if target_type == "groups" and not is_group:
                continue
            elif target_type == "channels" and not is_channel:
                continue
            elif target_type == "all" and not (is_group or is_channel):
                continue

            # Check exclusions
            chat_title = (dialog.title or "").lower()
            chat_uname = (dialog.entity.username or "").lower() if hasattr(dialog.entity, "username") and dialog.entity.username else ""
            chat_id_str = str(dialog.id).lower()

            if any(ex in chat_title or ex in chat_uname or ex == chat_id_str for ex in excluded):
                continue

            # Send the ad message instantly!
            try:
                await send_ad_to_dialog(client, dialog, settings, local_media_path)
                acc_sent += 1
                await db.increment_analytics(user_id, sent_count=1, failed_count=0)

                # Send live delivery log to user via system log account if active
                log_client = get_system_client("log")
                if log_client and log_client.is_connected():
                    try:
                        await log_client.send_message(
                            user_id,
                            f"📡 <b>[LIVE AD DELIVERED]</b>\n"
                            f"• <b>Account:</b> {acc_name}\n"
                            f"• <b>Target:</b> {dialog.title}\n"
                            f"• <b>Status:</b> Delivered ✅",
                            parse_mode="html"
                        )
                    except Exception:
                        pass

                await asyncio.sleep(delay)

            except FloodWaitError as fe:
                wait_sec = min(fe.seconds, 120)
                logger.warning(f"FloodWait {fe.seconds}s on acc {acc_name}")
                await asyncio.sleep(wait_sec)

            except (UserBannedInChannelError, ChatWriteForbiddenError):
                acc_failed += 1
                await db.increment_analytics(user_id, sent_count=0, failed_count=1)

            except ACCOUNT_DEAD_ERRORS as dead_err:
                logger.warning(f"Account {acc_name} DEAD: {dead_err}")
                await db.mark_account_banned(acc_id)
                return acc_sent, acc_failed, acc_name

            except Exception as post_err:
                logger.debug(f"Post error on {acc_name} to {dialog.id}: {post_err}")
                acc_failed += 1
                await db.increment_analytics(user_id, sent_count=0, failed_count=1)

    except ACCOUNT_DEAD_ERRORS as dead_err:
        logger.warning(f"Account {acc_name} DEAD on connect: {dead_err}")
        await db.mark_account_banned(acc_id)
        return acc_sent, acc_failed, acc_name
    except Exception as acc_err:
        logger.error(f"Error on account {acc_name}: {acc_err}")
    finally:
        if acc_sent > 0 or acc_failed > 0:
            await db.update_account_stats(acc_id, sent=acc_sent, failed=acc_failed)
        if created_here and client:
            try:
                await client.disconnect()
            except Exception:
                pass

    return acc_sent, acc_failed, None


async def run_user_ad_campaign(bot: Bot, user_id: int):
    """
    Background worker that posts ads to groups/channels across all accounts in parallel.
    Instant message start with zero latency, anti-ban detection, schedule, and cycle notifications.
    """
    logger.info(f"Starting ad campaign loop for user {user_id}")
    try:
        while True:
            # 1. Fetch current settings & verify still running
            settings = await db.get_user_settings(user_id)
            if not settings or settings.get("status", "Paused").lower() != "running":
                logger.info(f"Ad campaign stopped for user {user_id}")
                break

            # 2. Schedule check
            schedule_enabled = settings.get("schedule_enabled", 0)
            schedule_start = settings.get("schedule_start")
            schedule_end = settings.get("schedule_end")
            if schedule_enabled and schedule_start and schedule_end:
                if not is_within_schedule(schedule_start, schedule_end):
                    logger.info(f"User {user_id}: Outside schedule window, waiting 60s...")
                    await asyncio.sleep(60)
                    continue

            # 3. Verify ad message or media is set
            ad_message = settings.get("ad_message")
            ad_media_id = settings.get("ad_media_id")
            if not ad_message and not ad_media_id:
                await db.update_user_setting(user_id, "status", "Paused")
                await bot.send_message(
                    user_id,
                    f"{EMOJI_WARNING} <b>Ad Campaign Paused!</b>\n\n"
                    "Ad message ya media set nahi hai. Dashboard se pehle ad set karein.",
                    parse_mode="HTML"
                )
                break

            interval = settings.get("cycle_interval") or 300

            # 4. Fetch user's active accounts
            accounts = await db.get_user_accounts(user_id)
            if not accounts:
                await db.update_user_setting(user_id, "status", "Paused")
                await bot.send_message(
                    user_id,
                    f"{EMOJI_WARNING} <b>Ad Campaign Paused!</b>\n\n"
                    "Koi active account nahi mila. Naya account add karein.",
                    parse_mode="HTML"
                )
                break

            # 5. Pre-cache media locally if needed
            local_media_path = None
            if ad_media_id:
                if os.path.exists(ad_media_id):
                    local_media_path = ad_media_id
                else:
                    try:
                        os.makedirs("assets/ad_cache", exist_ok=True)
                        file_info = await bot.get_file(ad_media_id)
                        ext = file_info.file_path.split(".")[-1] if file_info.file_path and "." in file_info.file_path else "dat"
                        target_path = f"assets/ad_cache/{user_id}_ad.{ext}"
                        await bot.download_file(file_info.file_path, destination=target_path)
                        local_media_path = target_path
                    except Exception as dl_err:
                        logger.warning(f"Could not download ad media {ad_media_id}: {dl_err}")

            cycle_sent = 0
            cycle_failed = 0
            banned_accounts = []

            # 6. Post ads using ALL accounts in parallel for instant broadcast!
            tasks = [
                run_single_account_ads(bot, user_id, acc, settings, local_media_path)
                for acc in accounts
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for res in results:
                if isinstance(res, tuple):
                    sent_cnt, fail_cnt, dead_acc = res
                    cycle_sent += sent_cnt
                    cycle_failed += fail_cnt
                    if dead_acc:
                        banned_accounts.append(dead_acc)
                elif isinstance(res, Exception):
                    logger.error(f"Error in parallel account task for user {user_id}: {res}")

            # 7. Notify user about banned accounts (if any)
            if banned_accounts:
                names = "\n".join(f"• {n}" for n in banned_accounts)
                await bot.send_message(
                    user_id,
                    f"{EMOJI_WARNING} <b>Anti-Ban Alert!</b>\n\n"
                    f"Niche diye account(s) ban/expired ho gaye hain aur automatically disable kar diye gaye:\n"
                    f"{names}\n\n"
                    f"Please inhe <b>My Accounts</b> se remove karke naye accounts add karein.",
                    parse_mode="HTML"
                )

            # 8. Check cancellation after cycle
            chk_settings = await db.get_user_settings(user_id)
            if not chk_settings or chk_settings.get("status", "Paused").lower() != "running":
                break

            # 9. Cycle finished - update counter
            new_cycles = chk_settings.get("completed_cycles", 0) + 1
            await db.update_user_setting(user_id, "completed_cycles", new_cycles)

            # 10. Send detailed cycle notification
            total_analytics = await db.get_analytics(user_id)
            notif_msg = (
                f"{EMOJI_MOON} <b>Cycle #{new_cycles} Complete!</b>\n\n"
                f"• {EMOJI_VERIFIED} Sent this cycle: <code>{cycle_sent}</code>\n"
                f"• {EMOJI_CROSS} Failed this cycle: <code>{cycle_failed}</code>\n"
                f"• {EMOJI_STATS} Total All-time Sent: <code>{total_analytics.get('total_sent', 0)}</code>\n"
            )

            if cycle_sent == 0 and cycle_failed > 0:
                notif_msg += (
                    f"\n⚠️ <b>Dhayan Dein:</b> Is cycle ke saare messages fail ho gaye!\n"
                    f"• <b>Mukhya Vajah:</b> Aapke accounts jin groups me hain, unme chat locked hai (Only Admins Can Send) ya messaging permissions band hain.\n"
                    f"• <b>Solution:</b> Dashboard par <b>Auto Join Groups</b> button use karein aur open promotion groups join karein jahan messages allowed hon.\n"
                )

            max_c = chk_settings.get("max_cycles", 0)
            if max_c > 0 and new_cycles >= max_c:
                await db.update_user_setting(user_id, "status", "Paused")
                await bot.send_message(
                    user_id,
                    notif_msg +
                    f"\n{EMOJI_FIRE} <b>Campaign Finished!</b>\n"
                    f"Saare {max_c} cycles complete ho gaye. Campaign auto-paused!",
                    parse_mode="HTML"
                )
                break
            else:
                sleep_time = max(interval, 30)
                mins = sleep_time // 60
                await bot.send_message(
                    user_id,
                    notif_msg +
                    f"\n{EMOJI_CLOCK} Agli cycle <b>{mins}m</b> baad shuru hogi...",
                    parse_mode="HTML"
                )
                # Sleep for cycle interval
                await asyncio.sleep(sleep_time)

    except asyncio.CancelledError:
        logger.info(f"Ad worker task cancelled for user {user_id}")
    except Exception as e:
        logger.error(f"Fatal error in ad campaign for user {user_id}: {e}")
        try:
            await bot.send_message(
                user_id,
                f"{EMOJI_CROSS} <b>Campaign Error!</b>\n\n<code>{e}</code>\n\nCampaign auto-paused. Dashboard se restart karein.",
                parse_mode="HTML"
            )
            await db.update_user_setting(user_id, "status", "Paused")
        except Exception:
            pass
    finally:
        active_ad_tasks.pop(user_id, None)


# --- START ADS BUTTON ---
@router.callback_query(F.data == "start_ads")
async def btn_start_ads(call: CallbackQuery, bot: Bot):
    user_id = call.from_user.id
    settings = await db.get_user_settings(user_id)
    accounts = await db.get_user_accounts(user_id)

    if not accounts:
        await call.answer("⚠️ Pehle 'Add Account' par click karke Telegram account jodein!", show_alert=True)
        return

    if not settings.get("ad_message") and not settings.get("ad_media_id"):
        await call.answer("⚠️ Pehle 'Set Ad Message' par click karke Ad text/media set karein!", show_alert=True)
        return

    # Auto-default cycle interval if not set so user is never blocked
    if not settings.get("cycle_interval") or settings.get("cycle_interval") <= 0:
        await db.update_user_setting(user_id, "cycle_interval", 300)
        settings["cycle_interval"] = 300

    # Check if already running
    if settings.get("status") == "Running" and user_id in active_ad_tasks and not active_ad_tasks[user_id].done():
        await call.answer("🚀 Ads already running hain!", show_alert=True)
        return

    await db.update_user_setting(user_id, "status", "Running")

    # Cancel previous task if lingering
    if user_id in active_ad_tasks and not active_ad_tasks[user_id].done():
        active_ad_tasks[user_id].cancel()

    # Start fresh async worker task
    task = asyncio.create_task(run_user_ad_campaign(bot, user_id))
    active_ad_tasks[user_id] = task

    await call.answer("🚀 Ad Campaign Started! Instant messages shuru ho gaye.")
    await show_dashboard(bot, call.message.chat.id, user_id, message_to_edit=call.message)

    # Send instant confirmation in chat
    try:
        acc_count = len(accounts)
        tgt = settings.get("target_type", "Groups")
        dly = settings.get("message_delay", 5)
        await bot.send_message(
            call.message.chat.id,
            f"🚀 <b>Ad Campaign Shuru Ho Chuki Hai!</b>\n\n"
            f"⚡ <b>Instant Broadcast Status:</b>\n"
            f"• {EMOJI_PLANE} <b>Active Accounts:</b> <code>{acc_count}</code>\n"
            f"• {EMOJI_TARGET} <b>Target Chats:</b> <code>{tgt}</code>\n"
            f"• {EMOJI_CLOCK} <b>Message Delay:</b> <code>{dly}s</code>\n\n"
            f"💬 <i>Aapke sabhi connected accounts se target groups me turant messages bheje ja rahe hain...</i>",
            parse_mode="HTML"
        )
    except Exception:
        pass


# --- STOP ADS BUTTON ---
@router.callback_query(F.data == "stop_ads")
async def btn_stop_ads(call: CallbackQuery, bot: Bot):
    user_id = call.from_user.id
    await db.update_user_setting(user_id, "status", "Paused")

    if user_id in active_ad_tasks:
        task = active_ad_tasks.pop(user_id)
        if not task.done():
            task.cancel()

    await call.answer("🛑 Ads Campaign Paused!")
    await show_dashboard(bot, call.message.chat.id, user_id, message_to_edit=call.message)

    try:
        await bot.send_message(
            call.message.chat.id,
            f"🛑 <b>Ads Campaign Paused!</b>\n\n"
            f"Broadcasting successfully rok di gayi hai.\n"
            f"Aap dashboard se kisi bhi waqt dobara <b>Start Ads</b> kar sakte hain.",
            parse_mode="HTML"
        )
    except Exception:
        pass


# --- COMMAND SHORTCUTS ---
@router.message(Command("start_ads"))
async def cmd_start_ads(message: Message, bot: Bot):
    user_id = message.from_user.id
    settings = await db.get_user_settings(user_id)
    accounts = await db.get_user_accounts(user_id)

    if not accounts:
        await message.answer("⚠️ Pehle 'Add Account' par click karke Telegram account jodein!")
        return

    if not settings.get("ad_message") and not settings.get("ad_media_id"):
        await message.answer("⚠️ Pehle 'Set Ad Message' par click karke Ad text/media set karein!")
        return

    if not settings.get("cycle_interval") or settings.get("cycle_interval") <= 0:
        await db.update_user_setting(user_id, "cycle_interval", 300)
        settings["cycle_interval"] = 300

    if settings.get("status") == "Running" and user_id in active_ad_tasks and not active_ad_tasks[user_id].done():
        await message.answer("🚀 Ads already running hain!")
        return

    await db.update_user_setting(user_id, "status", "Running")

    if user_id in active_ad_tasks and not active_ad_tasks[user_id].done():
        active_ad_tasks[user_id].cancel()

    task = asyncio.create_task(run_user_ad_campaign(bot, user_id))
    active_ad_tasks[user_id] = task

    await message.answer(
        f"🚀 <b>Ad Campaign Shuru Ho Chuki Hai!</b>\n\n"
        f"⚡ <b>Instant Broadcast Status:</b>\n"
        f"• {EMOJI_PLANE} <b>Active Accounts:</b> <code>{len(accounts)}</code>\n"
        f"• {EMOJI_TARGET} <b>Target Chats:</b> <code>{settings.get('target_type', 'Groups')}</code>\n\n"
        f"💬 <i>Aapke sabhi connected accounts se target groups me turant messages bheje ja rahe hain...</i>",
        parse_mode="HTML"
    )


@router.message(Command("stop_ads"))
async def cmd_stop_ads(message: Message, bot: Bot):
    user_id = message.from_user.id
    await db.update_user_setting(user_id, "status", "Paused")

    if user_id in active_ad_tasks:
        task = active_ad_tasks.pop(user_id)
        if not task.done():
            task.cancel()

    await message.answer(
        "🛑 <b>Ads Campaign Paused!</b>\n\nBroadcasting rok di gayi hai.",
        parse_mode="HTML"
    )


async def resume_active_campaigns(bot: Bot):
    """
    On bot startup, automatically resumes all ad campaigns that were in 'Running' status.
    """
    try:
        if hasattr(db, "get_active_running_users"):
            running_users = await db.get_active_running_users()
            for uid in running_users:
                if uid not in active_ad_tasks or active_ad_tasks[uid].done():
                    logger.info(f"Auto-resuming active ad campaign for user {uid}...")
                    task = asyncio.create_task(run_user_ad_campaign(bot, uid))
                    active_ad_tasks[uid] = task
    except Exception as e:
        logger.warning(f"Could not auto-resume active campaigns: {e}")
