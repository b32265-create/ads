import logging
import asyncio
from datetime import datetime, time as dtime
from typing import Dict
from aiogram import Router, F, Bot
from aiogram.types import CallbackQuery
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
from emojis import (
    EMOJI_WARNING, EMOJI_MOON, EMOJI_VERIFIED, EMOJI_CROSS, EMOJI_STATS,
    EMOJI_FIRE, EMOJI_CLOCK, EMOJI_ROCKET
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

async def send_ad_to_dialog(client: TelegramClient, dialog_id: int, settings: dict) -> bool:
    """
    Send ad (text or media) to a single dialog.
    Returns True on success, False on failure.
    """
    ad_message = settings.get("ad_message") or ""
    ad_media_id = settings.get("ad_media_id")
    ad_media_type = settings.get("ad_media_type")

    if ad_media_id and ad_media_type:
        # Media ad: send file with caption
        await client.send_file(
            dialog_id,
            file=int(ad_media_id),
            caption=ad_message or None
        )
    else:
        await client.send_message(dialog_id, ad_message)
    return True


async def run_user_ad_campaign(bot: Bot, user_id: int):
    """
    Background worker that posts ads to groups/channels in automated cycles.
    Supports: media ads, anti-ban detection, schedule, cycle notifications.
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
                    # Outside schedule window - wait and check again
                    logger.info(f"User {user_id}: Outside schedule window, waiting 60s...")
                    await asyncio.sleep(60)
                    continue

            # 3. Verify ad message is set
            ad_message = settings.get("ad_message")
            if not ad_message and not settings.get("ad_media_id"):
                await db.update_user_setting(user_id, "status", "Paused")
                await bot.send_message(
                    user_id,
                    f"{EMOJI_WARNING} <b>Ad Campaign Paused!</b>\n\n"
                    "Ad message ya media set nahi hai. Dashboard se pehle ad set karein.",
                    parse_mode="HTML"
                )
                break

            delay = settings.get("message_delay", 5)
            interval = settings.get("cycle_interval", 600)
            target_type = settings.get("target_type", "Groups").lower()
            excluded_raw = settings.get("exclude_groups", "") or ""
            excluded = [x.strip().lower() for x in excluded_raw.split(",") if x.strip()]

            # 4. Fetch user's active (non-banned) accounts
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

            cycle_sent = 0
            cycle_failed = 0
            banned_accounts = []

            # 5. Post ads using each account
            for acc in accounts:
                # Check cancellation
                current_st = await db.get_user_settings(user_id)
                if current_st.get("status", "Paused").lower() != "running":
                    break

                session_str = acc.get("session_string")
                if not session_str:
                    continue

                acc_id = acc.get("id")
                acc_sent = 0
                acc_failed = 0
                client = None

                try:
                    client = TelegramClient(StringSession(session_str), API_ID, API_HASH)
                    await client.connect()
                    if not await client.is_user_authorized():
                        logger.warning(f"Account {acc.get('phone_number')} not authorized, marking banned")
                        await db.mark_account_banned(acc_id)
                        banned_accounts.append(acc.get("account_name", acc.get("phone_number")))
                        continue

                    # Iterate over dialogs (groups/supergroups/channels)
                    async for dialog in client.iter_dialogs(limit=200):
                        # Verify cancellation again
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

                        # Check exclusions
                        chat_title = (dialog.title or "").lower()
                        chat_uname = (dialog.entity.username or "").lower() if hasattr(dialog.entity, "username") and dialog.entity.username else ""
                        chat_id_str = str(dialog.id).lower()

                        if any(ex in chat_title or ex in chat_uname or ex == chat_id_str for ex in excluded):
                            continue

                        # Send the ad message!
                        try:
                            await send_ad_to_dialog(client, dialog.id, settings)
                            cycle_sent += 1
                            acc_sent += 1
                            await db.increment_analytics(user_id, sent_count=1, failed_count=0)
                            await asyncio.sleep(delay)

                        except FloodWaitError as fe:
                            wait_sec = min(fe.seconds, 120)
                            logger.warning(f"FloodWait {fe.seconds}s on acc {acc.get('phone_number')}")
                            await asyncio.sleep(wait_sec)

                        except (UserBannedInChannelError, ChatWriteForbiddenError):
                            cycle_failed += 1
                            acc_failed += 1
                            await db.increment_analytics(user_id, sent_count=0, failed_count=1)

                        except ACCOUNT_DEAD_ERRORS as dead_err:
                            # Account is banned/deactivated - mark and stop using it
                            logger.warning(f"Account {acc.get('phone_number')} DEAD: {dead_err}")
                            await db.mark_account_banned(acc_id)
                            banned_accounts.append(acc.get("account_name", acc.get("phone_number")))
                            break

                        except Exception as post_err:
                            logger.debug(f"Post error to {dialog.id}: {post_err}")
                            cycle_failed += 1
                            acc_failed += 1
                            await db.increment_analytics(user_id, sent_count=0, failed_count=1)

                except ACCOUNT_DEAD_ERRORS as dead_err:
                    logger.warning(f"Account {acc.get('phone_number')} DEAD on connect: {dead_err}")
                    await db.mark_account_banned(acc_id)
                    banned_accounts.append(acc.get("account_name", acc.get("phone_number")))
                except Exception as acc_err:
                    logger.error(f"Error on account {acc.get('phone_number')}: {acc_err}")
                finally:
                    if acc_sent > 0 or acc_failed > 0:
                        await db.update_account_stats(acc_id, sent=acc_sent, failed=acc_failed)
                    if client:
                        try:
                            await client.disconnect()
                        except Exception:
                            pass

            # 6. Notify user about banned accounts (if any)
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

            # 7. Cycle finished - update counter
            new_cycles = settings.get("completed_cycles", 0) + 1
            await db.update_user_setting(user_id, "completed_cycles", new_cycles)

            # 8. Send detailed cycle notification
            total_analytics = await db.get_analytics(user_id)
            notif_msg = (
                f"{EMOJI_MOON} <b>Cycle #{new_cycles} Complete!</b>\n\n"
                f"• {EMOJI_VERIFIED} Sent this cycle: <code>{cycle_sent}</code>\n"
                f"• {EMOJI_CROSS} Failed this cycle: <code>{cycle_failed}</code>\n"
                f"• {EMOJI_STATS} Total All-time Sent: <code>{total_analytics.get('total_sent', 0)}</code>\n"
            )

            max_c = settings.get("max_cycles", 0)
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

    if not settings.get("cycle_interval"):
        await call.answer("⚠️ Pehle 'Set Interval' se cycle interval set karein!", show_alert=True)
        return

    # Check if already running
    if settings.get("status") == "Running" and user_id in active_ad_tasks:
        await call.answer("🚀 Ads already running hain!", show_alert=True)
        return

    await db.update_user_setting(user_id, "status", "Running")

    # Cancel previous task if lingering
    if user_id in active_ad_tasks and not active_ad_tasks[user_id].done():
        active_ad_tasks[user_id].cancel()

    # Start fresh async worker task
    task = asyncio.create_task(run_user_ad_campaign(bot, user_id))
    active_ad_tasks[user_id] = task

    await call.answer("🚀 Ad Campaign Started!")
    await show_dashboard(bot, call.message.chat.id, user_id, message_to_edit=call.message)


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
