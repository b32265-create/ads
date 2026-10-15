import logging
import asyncio
import os
import random
import re
import html
from datetime import datetime, timezone
from typing import Dict, Optional, Tuple, List, Set
from aiogram import Router, F, Bot
from aiogram.types import CallbackQuery, Message, FSInputFile, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.types import (
    User,
    UserStatusOnline,
    UserStatusRecently,
    UserStatusOffline,
    UserStatusLastWeek,
    UserStatusLastMonth,
    UserStatusEmpty
)
from telethon.errors import (
    FloodWaitError, UserBannedInChannelError, ChatWriteForbiddenError,
    UserDeactivatedBanError, AuthKeyUnregisteredError, UserDeactivatedError,
    SessionRevokedError, PeerFloodError, UserPrivacyRestrictedError,
    UserNotMutualContactError
)

import database as db
import keyboards as kb
from config import API_ID, API_HASH
from handlers.user import show_dashboard, UserStates
from dm_relay import get_or_create_client
from system_clients import get_system_client
from emojis import (
    EMOJI_WARNING, EMOJI_MOON, EMOJI_VERIFIED, EMOJI_CROSS, EMOJI_STATS,
    EMOJI_FIRE, EMOJI_CLOCK, EMOJI_ROCKET, EMOJI_PLANE, EMOJI_TARGET,
    EMOJI_MSG, EMOJI_FLASH, EMOJI_USER
)

logger = logging.getLogger("ShadowAdsBot.AutoDM")

router = Router(name="autodm_worker_router")

# Active running background tasks by user_id
active_autodm_tasks: Dict[int, asyncio.Task] = {}

# Concurrent lock & in-flight set to prevent parallel accounts from targeting the same lead simultaneously
_IN_FLIGHT_LOCK = asyncio.Lock()
_IN_FLIGHT_LEADS: Set[Tuple[int, str]] = set()

class AutoDMStates(StatesGroup):
    waiting_autodm_message = State()
    waiting_custom_rate = State()
    waiting_custom_targets = State()
    waiting_keywords = State()
    waiting_auto_reply = State()


def is_eligible_lead_user(user) -> bool:
    """
    Checks if a user is an eligible real person (not bot/deleted/self/dead).
    Allowed:
    - Real users who posted messages in groups
    - Active / Online / Recently online
    - Privacy-hidden status (status=None) - which is normal for Telegram group members
    Disallowed:
    - Bots, deleted accounts, self
    - Inactive for over a month (UserStatusLastMonth)
    - Dead or ghost accounts (UserStatusEmpty)
    """
    if not user or not isinstance(user, User):
        return False
    if getattr(user, "bot", False) or getattr(user, "deleted", False) or getattr(user, "is_self", False):
        return False

    status = getattr(user, "status", None)
    if status and isinstance(status, (UserStatusLastMonth, UserStatusEmpty)):
        return False
    return True


# Backward compatibility alias
is_latest_online_user = is_eligible_lead_user


async def is_lead_already_contacted_or_in_flight(
    user_id: int,
    lead_id: Optional[str] = None,
    username: Optional[str] = None
) -> bool:
    """
    Strict duplicate prevention across persistent database and active in-flight worker accounts.
    Returns True if this lead has EVER received a DM or is currently being messaged.
    """
    keys = []
    if lead_id:
        keys.append(str(lead_id).lower().strip())
    if username:
        clean_u = str(username).lstrip("@").lower().strip()
        if clean_u:
            keys.append(clean_u)
            keys.append(f"@{clean_u}")

    # 1. Check persistent database
    for k in keys:
        if await db.is_lead_contacted(user_id, k):
            return True

    # 2. Check in-flight concurrent memory
    async with _IN_FLIGHT_LOCK:
        for k in keys:
            if (user_id, k) in _IN_FLIGHT_LEADS:
                return True

    return False


async def reserve_lead_in_flight(
    user_id: int,
    lead_id: Optional[str] = None,
    username: Optional[str] = None
) -> List[str]:
    """
    Locks the lead in-memory so other concurrent accounts skip this lead instantly.
    """
    keys = []
    if lead_id:
        keys.append(str(lead_id).lower().strip())
    if username:
        clean_u = str(username).lstrip("@").lower().strip()
        if clean_u:
            keys.append(clean_u)
            keys.append(f"@{clean_u}")

    async with _IN_FLIGHT_LOCK:
        for k in keys:
            _IN_FLIGHT_LEADS.add((user_id, k))
    return keys


async def release_and_mark_lead(
    user_id: int,
    keys: List[str],
    mark_as_contacted: bool = True
):
    """
    Persists lead as contacted in database and frees the in-flight lock.
    """
    if mark_as_contacted:
        for k in keys:
            try:
                await db.mark_lead_contacted(user_id, k)
            except Exception:
                pass

    async with _IN_FLIGHT_LOCK:
        for k in keys:
            _IN_FLIGHT_LEADS.discard((user_id, k))


def clean_html_preview(text: str, max_chars: int = 80) -> str:
    """Safely strips HTML tags and escapes special characters for telegram entity rendering."""
    if not text:
        return ""
    clean = re.sub(r'<[^>]+>', ' ', str(text))
    clean = ' '.join(clean.split()).strip()
    if len(clean) > max_chars:
        clean = clean[:max_chars].strip() + "..."
    return html.escape(clean)


def get_autodm_dashboard_text(settings: dict, accounts_count: int, scraped_stats: dict = None) -> str:
    scraped_stats = scraped_stats or {"total": 0, "pending": 0, "contacted": 0}
    enabled = bool(settings.get("autodm_enabled", 0))
    status_disp = f"🟢 <b>ACTIVE & SCANNING (Every 10 Mins)</b>" if enabled else f"🔴 <b>PAUSED / IDLE</b>"
    rate = int(settings.get("autodm_rate_per_hour", 10) or 10)
    per_10m = max(1, round(rate / 6))
    mode = settings.get("autodm_target_mode", "groups")
    mode_disp = "Group 500 Msgs (Auto-Scrape & Save)" if mode == "groups" else "Custom Target List"
    
    keywords = settings.get("autodm_keywords", "") or ""
    kw_list = [k.strip() for k in keywords.replace(",", "\n").split("\n") if k.strip()]
    kw_disp = f"<code>{html.escape(', '.join(kw_list[:4]))}{'...' if len(kw_list) > 4 else ''}</code>" if kw_list else "<i>All active chatters (No filter)</i>"

    auto_reply = settings.get("autodm_auto_reply", "") or ""
    ar_disp = f"<code>{clean_html_preview(auto_reply, 40)}</code>" if auto_reply else "<i>Disabled / Not Set</i>"

    custom_targets = settings.get("autodm_custom_targets", "") or ""
    targets_count = len([x for x in custom_targets.replace(",", "\n").split("\n") if x.strip()])
    
    msg = settings.get("autodm_message") or settings.get("ad_message") or ""
    has_media = bool(settings.get("autodm_media_id") or settings.get("ad_media_id"))
    media_note = " [📎 Media Attached]" if has_media else ""
    
    total_sent = settings.get("autodm_total_sent", 0)
    total_failed = settings.get("autodm_total_failed", 0)

    clean_snippet = clean_html_preview(msg, 80) if msg else "<i>(Default Ad Message)</i>"

    leads_info = f"<code>{scraped_stats['total']} Leads</code> (<b>{scraped_stats['pending']}</b> Pending, <b>{scraped_stats['contacted']}</b> Contacted)" if mode == "groups" else f"<code>{targets_count} Targets</code>"

    return (
        f"╔══════════════════════════╗\n"
        f"  ⚡ <b>10-MINUTE AUTO DM & LEAD ENGINE</b> 🐲\n"
        f"╚══════════════════════════╝\n"
        f"Har 10 minute me groups ke <b>new 500 messages scan</b> karke active usernames ko automatically database me save aur direct DM deliver karne ka system.\n\n"
        f"📊 <b>AUTO DM CONFIGURATION & STATUS</b>\n"
        f"┌ 📱 <b>Hosted Accounts:</b> <code>{accounts_count} Active</code>\n"
        f"├ ⏱ <b>Scan & DM Cycle:</b> <code>Every 10 Minutes</code>\n"
        f"├ 🚀 <b>Delivery Speed:</b> <code>~{per_10m} DMs / 10m (~{rate}/hr per acc)</code>\n"
        f"├ 🎯 <b>Targeting Mode:</b> <code>{mode_disp}</code>\n"
        f"├ 📥 <b>Saved Usernames Pool:</b> {leads_info}\n"
        f"├ 🔍 <b>Word / Keyword Filter:</b> {kw_disp}\n"
        f"├ 🤖 <b>Lead Auto-Reply:</b> {ar_disp}\n"
        f"├ 📝 <b>DM Content:</b> {clean_snippet}{media_note}\n"
        f"├ 📤 <b>Total DMs Sent:</b> <code>{total_sent}</code>\n"
        f"├ ⚠️ <b>Total DMs Skipped:</b> <code>{total_failed}</code>\n"
        f"└ {status_disp}\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"🛡️ <b>Anti-Duplicate:</b> <code>100% Lifetime Protection (Zero Repeat DMs)</code>\n"
        f"🔄 <b>Auto-Scan:</b> <code>Scans 500 new msgs every 10 mins & saves usernames</code>\n"
        f"👥 <b>Active Leads:</b> <code>Recent chatters from active groups</code>"
    )


async def send_dm_to_lead(
    client: TelegramClient,
    target,
    dm_text: str,
    local_media: Optional[str] = None
) -> bool:
    """Delivers direct message (text or media) to a targeted user peer."""
    target_peer = getattr(target, "input_entity", None) or getattr(target, "entity", None) or target
    if local_media and os.path.exists(local_media):
        try:
            await client.send_file(
                target_peer,
                file=local_media,
                caption=dm_text or None,
                parse_mode="html"
            )
        except Exception:
            await client.send_file(
                target_peer,
                file=local_media,
                caption=dm_text or None
            )
    else:
        try:
            await client.send_message(target_peer, dm_text, parse_mode="html")
        except Exception:
            await client.send_message(target_peer, dm_text)
    return True


async def scan_and_save_group_leads(
    user_id: int,
    accounts: list,
    settings: dict,
    max_messages: int = 500
) -> int:
    """
    Scans the latest up to 500 new messages from group chats across connected accounts.
    Extracts usernames and lead IDs, applies keyword filter if set, and saves them
    into the persistent database `scraped_leads` table.
    """
    raw_kws = settings.get("autodm_keywords", "") or ""
    kw_filters = [k.strip().lower() for k in raw_kws.replace(",", "\n").split("\n") if k.strip()]

    total_new_saved = 0
    scanned_groups = set()

    for acc in accounts:
        session_str = acc.get("session_string")
        if not session_str:
            continue

        client = None
        created_here = False
        try:
            client = await get_or_create_client(acc)
            if not client or not client.is_connected():
                client = TelegramClient(StringSession(session_str), API_ID, API_HASH)
                await client.connect()
                created_here = True

            if not await client.is_user_authorized():
                continue

            async for dialog in client.iter_dialogs(limit=50):
                if not dialog.is_group:
                    continue

                group_id_str = str(dialog.id)
                if group_id_str in scanned_groups:
                    continue
                scanned_groups.add(group_id_str)

                group_title = getattr(dialog, "name", "") or getattr(dialog, "title", "Group")
                last_msg_id = await db.get_group_last_scanned_msg_id(user_id, group_id_str)

                iter_kwargs = {"limit": max_messages}
                if last_msg_id > 0:
                    iter_kwargs["min_id"] = last_msg_id

                batch_leads = []
                highest_seen_id = last_msg_id

                try:
                    async for msg in client.iter_messages(dialog.input_entity, **iter_kwargs):
                        if msg.id > highest_seen_id:
                            highest_seen_id = msg.id

                        # Keyword check
                        msg_text = (msg.text or "").strip()
                        if kw_filters:
                            msg_lower = msg_text.lower()
                            if not any(kw in msg_lower for kw in kw_filters):
                                continue

                        sender = None
                        try:
                            sender = await msg.get_sender()
                        except Exception:
                            sender = getattr(msg, "sender", None)

                        if not sender or not is_eligible_lead_user(sender):
                            continue

                        uname = getattr(sender, "username", "") or ""
                        first_name = (getattr(sender, "first_name", "") or "") + " " + (getattr(sender, "last_name", "") or "")
                        lead_id_str = str(sender.id)

                        # Must have at least a username or a valid numeric ID
                        if uname or lead_id_str:
                            batch_leads.append((uname, lead_id_str, first_name.strip(), group_id_str, group_title))

                except Exception as iter_err:
                    logger.debug(f"Could not iterate messages from {group_title} ({group_id_str}): {iter_err}")

                if highest_seen_id > last_msg_id:
                    await db.update_group_last_scanned_msg_id(user_id, group_id_str, highest_seen_id)

                if batch_leads:
                    new_saved = await db.save_scraped_leads_batch(user_id, batch_leads)
                    total_new_saved += new_saved

        except Exception as acc_err:
            logger.error(f"Error scanning groups with account {acc.get('id')}: {acc_err}")
        finally:
            if created_here and client:
                try:
                    await client.disconnect()
                except Exception:
                    pass

    return total_new_saved


async def dispatch_single_account_autodm(
    bot: Bot,
    user_id: int,
    acc: dict,
    settings: dict,
    local_media: Optional[str] = None,
    round_quota: int = 2
) -> Tuple[int, int]:
    """
    Sends direct messages from one account for this 10-minute round.
    Pulls from scraped leads pool or custom target list.
    """
    session_str = acc.get("session_string")
    if not session_str:
        return 0, 0

    acc_id = acc.get("id")
    acc_name = acc.get("account_name") or acc.get("phone_number") or f"Account_{acc_id}"
    dm_text = settings.get("autodm_message") or settings.get("ad_message") or ""
    mode = settings.get("autodm_target_mode", "groups")

    client = None
    created_here = False
    sent_count = 0
    fail_count = 0

    try:
        client = await get_or_create_client(acc)
        if not client or not client.is_connected():
            client = TelegramClient(StringSession(session_str), API_ID, API_HASH)
            await client.connect()
            created_here = True

        if not await client.is_user_authorized():
            return 0, 0

        # Fetch candidate leads
        candidate_leads = []
        if mode == "custom_list":
            raw_targets = settings.get("autodm_custom_targets", "") or ""
            targets = [x.strip() for x in raw_targets.replace(",", "\n").split("\n") if x.strip()]
            for t in targets:
                clean_t = t.lstrip("@").strip()
                if clean_t:
                    candidate_leads.append({"username": clean_t, "lead_id": ""})
        else:
            # Mode Groups: Pull uncontacted leads from scraped_leads pool in DB
            db_leads = await db.get_pending_scraped_leads(user_id, limit=round_quota * 4)
            candidate_leads = db_leads

        for lead in candidate_leads:
            c_chk = await db.get_user_settings(user_id)
            if not c_chk.get("autodm_enabled", 0):
                break
            if sent_count >= round_quota:
                break

            uname = (lead.get("username") or "").lstrip("@").strip()
            lead_id_str = str(lead.get("lead_id") or "").strip()

            if not uname and not lead_id_str:
                continue

            # Check duplicate / in-flight
            if await is_lead_already_contacted_or_in_flight(user_id, lead_id=lead_id_str, username=uname):
                if lead_id_str or uname:
                    await db.mark_scraped_lead_contacted(user_id, lead_id_str, uname)
                continue

            # Reserve in-flight lock
            reserved_keys = await reserve_lead_in_flight(user_id, lead_id=lead_id_str, username=uname)

            # Resolve entity/peer
            target_peer = None
            try:
                if uname:
                    target_peer = await client.get_input_entity(uname)
                elif lead_id_str and lead_id_str.isdigit():
                    target_peer = await client.get_input_entity(int(lead_id_str))
            except Exception as ent_err:
                logger.debug(f"Could not resolve entity for lead {uname or lead_id_str}: {ent_err}")
                await release_and_mark_lead(user_id, reserved_keys, mark_as_contacted=True)
                await db.mark_scraped_lead_contacted(user_id, lead_id_str, uname)
                continue

            if not target_peer:
                await release_and_mark_lead(user_id, reserved_keys, mark_as_contacted=True)
                await db.mark_scraped_lead_contacted(user_id, lead_id_str, uname)
                continue

            lead_disp = f"@{uname}" if uname else f"ID: {lead_id_str}"

            try:
                await send_dm_to_lead(client, target_peer, dm_text, local_media)
                sent_count += 1
                await db.increment_autodm_stats(user_id, sent=1, failed=0)
                await db.mark_scraped_lead_contacted(user_id, lead_id_str, uname)

                # Send live log
                log_client = get_system_client("log")
                if log_client and log_client.is_connected():
                    try:
                        await log_client.send_message(
                            user_id,
                            f"⚡ <b>[AUTO DM DELIVERED]</b>\n"
                            f"• <b>Account:</b> {acc_name}\n"
                            f"• <b>Lead:</b> {lead_disp}\n"
                            f"• <b>Source:</b> 10-Min Scraped Lead ✅\n"
                            f"• <b>Status:</b> Success ✅",
                            parse_mode="html"
                        )
                    except Exception:
                        pass

                # Anti-flood sleep (20-30s)
                sleep_dur = random.randint(20, 30)
                await asyncio.sleep(sleep_dur)

            except PeerFloodError:
                logger.warning(f"PeerFlood on account {acc_name}. Backing off for this round.")
                fail_count += 1
                await db.increment_autodm_stats(user_id, sent=0, failed=1)
                break
            except FloodWaitError as fe:
                logger.warning(f"FloodWait {fe.seconds}s on {acc_name}")
                fail_count += 1
                await db.increment_autodm_stats(user_id, sent=0, failed=1)
                break
            except (UserPrivacyRestrictedError, UserNotMutualContactError):
                fail_count += 1
                await db.increment_autodm_stats(user_id, sent=0, failed=1)
                await db.mark_scraped_lead_contacted(user_id, lead_id_str, uname)
            except Exception as e:
                logger.debug(f"Auto DM error to {lead_disp}: {e}")
                fail_count += 1
                await db.increment_autodm_stats(user_id, sent=0, failed=1)
                await db.mark_scraped_lead_contacted(user_id, lead_id_str, uname)
            finally:
                await release_and_mark_lead(user_id, reserved_keys, mark_as_contacted=True)

    except Exception as acc_err:
        logger.error(f"Error in Auto DM dispatch for account {acc_name}: {acc_err}")
    finally:
        if created_here and client:
            try:
                await client.disconnect()
            except Exception:
                pass

    return sent_count, fail_count


async def run_user_autodm_campaign(bot: Bot, user_id: int):
    """
    Continuous background daemon that executes Auto DM rounds every 10 minutes:
    1. Scans the latest 500 new messages from joined groups and saves their usernames into the database.
    2. Sends DMs to the saved active leads from all connected accounts.
    3. Repeats automatically every 10 minutes when new messages arrive.
    """
    logger.info(f"Starting 10-Minute Auto DM campaign for user {user_id}")
    try:
        while True:
            settings = await db.get_user_settings(user_id)
            if not settings or not settings.get("autodm_enabled", 0):
                logger.info(f"Auto DM loop stopped for user {user_id}")
                break

            accounts = await db.get_user_accounts(user_id)
            if not accounts:
                await db.update_user_setting(user_id, "autodm_enabled", 0)
                await bot.send_message(
                    user_id,
                    f"{EMOJI_WARNING} <b>Auto DM Paused!</b>\n\nKoi active account nahi mila. Pehle accounts add karein.",
                    parse_mode="HTML"
                )
                break

            dm_message = settings.get("autodm_message") or settings.get("ad_message")
            dm_media = settings.get("autodm_media_id") or settings.get("ad_media_id")
            if not dm_message and not dm_media:
                await db.update_user_setting(user_id, "autodm_enabled", 0)
                await bot.send_message(
                    user_id,
                    f"{EMOJI_WARNING} <b>Auto DM Paused!</b>\n\nDM message ya media content set nahi hai. 'Set DM Message' se set karein.",
                    parse_mode="HTML"
                )
                break

            # Rate per 10-minute round per account (e.g., 12/hr = 2 per 10m round)
            hourly_rate = int(settings.get("autodm_rate_per_hour", 10) or 10)
            round_quota = max(1, round(hourly_rate / 6))

            # Local media caching
            local_media = None
            if dm_media:
                if os.path.exists(dm_media):
                    local_media = dm_media
                else:
                    try:
                        os.makedirs("assets/ad_cache", exist_ok=True)
                        file_info = await bot.get_file(dm_media)
                        ext = file_info.file_path.split(".")[-1] if file_info.file_path and "." in file_info.file_path else "dat"
                        target_path = f"assets/ad_cache/autodm_{user_id}.{ext}"
                        await bot.download_file(file_info.file_path, destination=target_path)
                        local_media = target_path
                    except Exception as dl_err:
                        logger.warning(f"Could not cache Auto DM media: {dl_err}")

            # STEP 1: Scan 500 new messages from groups and save usernames
            new_scraped_count = 0
            mode = settings.get("autodm_target_mode", "groups")
            if mode == "groups":
                try:
                    new_scraped_count = await scan_and_save_group_leads(user_id, accounts, settings, max_messages=500)
                except Exception as sc_err:
                    logger.error(f"Error scanning group leads for user {user_id}: {sc_err}")

            # STEP 2: Send DMs from all accounts in parallel
            tasks = [
                dispatch_single_account_autodm(bot, user_id, acc, settings, local_media, round_quota)
                for acc in accounts
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            total_sent_this_round = 0
            total_fail_this_round = 0
            for res in results:
                if isinstance(res, tuple):
                    s, f = res
                    total_sent_this_round += s
                    total_fail_this_round += f

            # STEP 3: Round notification with scraped stats
            leads_stats = await db.get_scraped_leads_stats(user_id)
            try:
                scrape_line = f"• 📥 <b>New Usernames Saved:</b> <code>+{new_scraped_count} Leads</code>\n" if mode == "groups" else ""
                pool_line = f"• 👥 <b>Total Saved in DB:</b> <code>{leads_stats['total']} Leads</code> (<code>{leads_stats['pending']}</code> Pending)\n" if mode == "groups" else ""

                await bot.send_message(
                    user_id,
                    f"⚡ <b>10-Minute Auto DM & Scan Round Completed!</b>\n\n"
                    f"{scrape_line}"
                    f"{pool_line}"
                    f"• {EMOJI_VERIFIED} <b>DMs Sent This Round:</b> <code>{total_sent_this_round} DMs</code>\n"
                    f"• {EMOJI_CROSS} <b>Skipped / Privacy:</b> <code>{total_fail_this_round}</code>\n"
                    f"• {EMOJI_CLOCK} Agli round theek <b>10 minutes</b> baad new 500 messages scan karke shuru hogi...",
                    parse_mode="HTML"
                )
            except Exception:
                pass

            # Sleep 10 minutes (600 seconds) with responsive cancellation check
            for _ in range(120): # 120 x 5s = 600s = 10 mins
                await asyncio.sleep(5)
                c_chk = await db.get_user_settings(user_id)
                if not c_chk or not c_chk.get("autodm_enabled", 0):
                    break

    except asyncio.CancelledError:
        logger.info(f"Auto DM loop cancelled for user {user_id}")
    except Exception as e:
        logger.error(f"Fatal error in Auto DM for user {user_id}: {e}")
    finally:
        active_autodm_tasks.pop(user_id, None)


async def render_autodm_dashboard(user_id: int):
    settings = await db.get_user_settings(user_id)
    accounts = await db.get_user_accounts(user_id)
    leads_stats = await db.get_scraped_leads_stats(user_id)
    text = get_autodm_dashboard_text(settings, len(accounts), leads_stats)
    markup = kb.get_autodm_keyboard(
        enabled=bool(settings.get("autodm_enabled", 0)),
        rate=settings.get("autodm_rate_per_hour", 10),
        target_mode=settings.get("autodm_target_mode", "groups"),
        pending_leads=leads_stats.get("pending", 0)
    )
    return text, markup


# --- UI HANDLERS ---
@router.callback_query(F.data == "auto_dm_menu")
async def btn_autodm_menu(call: CallbackQuery, bot: Bot, state: FSMContext):
    await state.clear()
    await call.answer()
    user_id = call.from_user.id
    text, markup = await render_autodm_dashboard(user_id)
    try:
        if call.message.photo or call.message.video or call.message.animation or call.message.document:
            try:
                await call.message.delete()
            except Exception:
                pass
            await bot.send_message(call.message.chat.id, text, reply_markup=markup, parse_mode="HTML")
        else:
            await call.message.edit_text(text, reply_markup=markup, parse_mode="HTML")
    except Exception as e:
        logger.warning(f"Error updating auto_dm_menu: {e}")
        try:
            try:
                await call.message.delete()
            except Exception:
                pass
            await bot.send_message(call.message.chat.id, text, reply_markup=markup, parse_mode="HTML")
        except Exception:
            await bot.send_message(call.message.chat.id, re.sub(r'<[^>]+>', '', text), reply_markup=markup)


@router.callback_query(F.data == "toggle_autodm_active")
async def btn_toggle_autodm_active(call: CallbackQuery, bot: Bot):
    user_id = call.from_user.id
    settings = await db.get_user_settings(user_id)
    accounts = await db.get_user_accounts(user_id)

    current_state = bool(settings.get("autodm_enabled", 0))

    if not current_state:
        # User wants to START Auto DM
        if not accounts:
            await call.answer("⚠️ Pehle 'Add Account' par click karke Telegram accounts jodein!", show_alert=True)
            return

        dm_msg = settings.get("autodm_message") or settings.get("ad_message")
        dm_media = settings.get("autodm_media_id") or settings.get("ad_media_id")
        if not dm_msg and not dm_media:
            await call.answer("⚠️ Pehle 'Set DM Message' par click karke message ya media set karein!", show_alert=True)
            return

        await db.update_user_setting(user_id, "autodm_enabled", 1)

        # Cancel lingering task if any
        if user_id in active_autodm_tasks and not active_autodm_tasks[user_id].done():
            active_autodm_tasks[user_id].cancel()

        task = asyncio.create_task(run_user_autodm_campaign(bot, user_id))
        active_autodm_tasks[user_id] = task

        rate = settings.get("autodm_rate_per_hour", 10)
        mode = settings.get("autodm_target_mode", "groups")

        await call.answer("⚡ 10-Minute Auto DM Started! Scanning 500 msgs...")
        try:
            await bot.send_message(
                call.message.chat.id,
                f"⚡ <b>10-Minute Auto DM Started Successfully!</b>\n\n"
                f"• {EMOJI_PLANE} <b>Active Accounts:</b> <code>{len(accounts)}</code>\n"
                f"• {EMOJI_CLOCK} <b>Scan & Send Cycle:</b> <code>Every 10 Minutes</code>\n"
                f"• {EMOJI_TARGET} <b>Targeting:</b> <code>{mode.upper()}</code>\n"
                f"• 📥 <b>Process:</b> <i>Har 10 minute me new 500 messages scan honge, usernames save honge aur safe anti-flood DMs dispatch honge.</i>",
                parse_mode="HTML"
            )
        except Exception:
            pass
    else:
        # User wants to STOP Auto DM
        await db.update_user_setting(user_id, "autodm_enabled", 0)
        if user_id in active_autodm_tasks:
            task = active_autodm_tasks.pop(user_id)
            if not task.done():
                task.cancel()
        await call.answer("🛑 Auto DM Paused!")

    text, markup = await render_autodm_dashboard(user_id)
    await call.message.edit_text(text, reply_markup=markup, parse_mode="HTML")


# --- SET DM CONTENT ---
@router.callback_query(F.data == "set_autodm_message")
async def btn_set_autodm_message(call: CallbackQuery, state: FSMContext):
    await call.answer()
    text = (
        f"╔══════════════════════════╗\n"
        f"  {EMOJI_MSG} <b>SET AUTO DM CONTENT</b>\n"
        f"╚══════════════════════════╝\n"
        f"Direct messages ke liye apna custom promotional message, offer, link ya photo/video send karein.\n\n"
        f"💡 <i>Tip: Agar aap yahan set nahi karte, toh aapka Main Dashboard wala Ad Message hi use hoga.</i>\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"👉 <i>Abhi apna DM content ya media yahan send karein:</i>"
    )
    await state.set_state(AutoDMStates.waiting_autodm_message)
    await call.message.edit_text(text, parse_mode="HTML", reply_markup=kb.get_autodm_back_keyboard())


@router.message(AutoDMStates.waiting_autodm_message)
async def process_autodm_message(message: Message, bot: Bot, state: FSMContext):
    user_id = message.from_user.id
    ad_text = message.html_text if (message.text or message.caption) else ""
    media_id = None
    media_type = None

    os.makedirs("assets/ad_media", exist_ok=True)
    if message.photo:
        media_type = "photo"
        local_path = f"assets/ad_media/autodm_{user_id}.jpg"
        try:
            await bot.download(message.photo[-1], destination=local_path)
            media_id = local_path
        except Exception:
            media_id = str(message.photo[-1].file_id)
    elif message.video:
        media_type = "video"
        local_path = f"assets/ad_media/autodm_{user_id}.mp4"
        try:
            await bot.download(message.video, destination=local_path)
            media_id = local_path
        except Exception:
            media_id = str(message.video.file_id)
    elif message.document:
        media_type = "document"
        local_path = f"assets/ad_media/autodm_{user_id}_doc.dat"
        try:
            await bot.download(message.document, destination=local_path)
            media_id = local_path
        except Exception:
            media_id = str(message.document.file_id)
    elif message.animation:
        media_type = "animation"
        local_path = f"assets/ad_media/autodm_{user_id}_anim.mp4"
        try:
            await bot.download(message.animation, destination=local_path)
            media_id = local_path
        except Exception:
            media_id = str(message.animation.file_id)

    if not ad_text and not media_id:
        await message.answer(
            f"{EMOJI_CROSS} <b>Kuch bhi receive nahi hua!</b> Text ya media bhejein.",
            parse_mode="HTML",
            reply_markup=kb.get_autodm_back_keyboard()
        )
        return

    await db.update_user_setting(user_id, "autodm_message", ad_text)
    await db.update_user_setting(user_id, "autodm_media_id", media_id)
    await db.update_user_setting(user_id, "autodm_media_type", media_type)
    await state.clear()

    await message.answer(
        f"{EMOJI_VERIFIED} <b>Auto DM Message Saved Successfully!</b>\n\nAb aap Auto DM start kar sakte hain.",
        parse_mode="HTML"
    )

    text, markup = await render_autodm_dashboard(user_id)
    await bot.send_message(message.chat.id, text, reply_markup=markup, parse_mode="HTML")


# --- SET HOURLY RATE ---
@router.callback_query(F.data == "set_autodm_rate")
async def btn_set_autodm_rate(call: CallbackQuery):
    await call.answer()
    text = (
        f"╔══════════════════════════╗\n"
        f"  ⏱ <b>SET AUTO DM RATE LIMIT</b>\n"
        f"╚══════════════════════════╝\n"
        f"Har 10 minute me accounts se kitne DMs send karne hain select karein:\n\n"
        f"• <b>1 DM / 10m (~6/hr):</b> Stealth & Ultra-Safe\n"
        f"• <b>2 DMs / 10m (~12/hr):</b> Recommended & Fast\n"
        f"• <b>3 DMs / 10m (~18/hr):</b> High Output\n"
        f"• <b>5 DMs / 10m (~30/hr):</b> Turbo (Purane Warm-up Accounts)\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"👉 Select rate below:"
    )
    await call.message.edit_text(text, parse_mode="HTML", reply_markup=kb.get_autodm_rate_keyboard())


@router.callback_query(F.data.startswith("autodm_rate_"))
async def btn_select_autodm_rate(call: CallbackQuery, state: FSMContext, bot: Bot):
    user_id = call.from_user.id
    val = call.data.replace("autodm_rate_", "")
    if val == "custom":
        await call.answer()
        await state.set_state(AutoDMStates.waiting_custom_rate)
        await call.message.edit_text(
            f"✏️ <b>Enter Custom Hourly Limit:</b>\n\n1 ghante me kitne DMs bhejne hain number enter karein (e.g. <code>12</code> ya <code>18</code>):",
            parse_mode="HTML",
            reply_markup=kb.get_autodm_back_keyboard()
        )
        return

    try:
        rate = int(val)
        await db.update_user_setting(user_id, "autodm_rate_per_hour", rate)
        await call.answer(f"✅ Rate set to ~{rate} DMs/hour!")
    except Exception:
        pass

    text, markup = await render_autodm_dashboard(user_id)
    await call.message.edit_text(text, reply_markup=markup, parse_mode="HTML")


@router.message(AutoDMStates.waiting_custom_rate)
async def process_custom_rate(message: Message, bot: Bot, state: FSMContext):
    user_id = message.from_user.id
    try:
        rate = int(message.text.strip())
        if rate <= 0 or rate > 50:
            await message.answer("⚠️ Kripya 1 se 50 ke beech number enter karein.")
            return
        await db.update_user_setting(user_id, "autodm_rate_per_hour", rate)
        await state.clear()
        await message.answer(f"✅ <b>Hourly Limit updated: ~{rate} DMs / hour!</b>", parse_mode="HTML")
    except ValueError:
        await message.answer("⚠️ Kripya valid number enter karein.")
        return

    text, markup = await render_autodm_dashboard(user_id)
    await bot.send_message(message.chat.id, text, reply_markup=markup, parse_mode="HTML")


# --- TOGGLE TARGETING MODE ---
@router.callback_query(F.data == "toggle_autodm_mode")
async def btn_toggle_autodm_mode(call: CallbackQuery, bot: Bot):
    user_id = call.from_user.id
    settings = await db.get_user_settings(user_id)
    current_mode = settings.get("autodm_target_mode", "groups")
    new_mode = "custom_list" if current_mode == "groups" else "groups"
    await db.update_user_setting(user_id, "autodm_target_mode", new_mode)
    
    label = "Custom Username List" if new_mode == "custom_list" else "Group 500 Msgs (Auto-Scrape & Save)"
    await call.answer(f"Targeting: {label}")

    text, markup = await render_autodm_dashboard(user_id)
    await call.message.edit_text(text, reply_markup=markup, parse_mode="HTML")


# --- VIEW & EXPORT SCRAPED LEADS ---
@router.callback_query(F.data == "autodm_view_leads")
async def btn_autodm_view_leads(call: CallbackQuery):
    await call.answer()
    user_id = call.from_user.id
    stats = await db.get_scraped_leads_stats(user_id)
    recent_leads = await db.get_all_scraped_leads_list(user_id, limit=8)

    sample_lines = []
    for l in recent_leads:
        uname = f"@{l['username']}" if l.get('username') else f"ID: {l.get('lead_id')}"
        status_tag = "✅ Sent" if l.get('is_contacted') else "⏳ Pending"
        grp = l.get('group_title') or "Group"
        sample_lines.append(f"• <b>{uname}</b> — {status_tag} <i>({grp[:20]})</i>")

    sample_disp = "\n".join(sample_lines) if sample_lines else "<i>Abhi koi leads scrape nahi hue hain. 'Start Auto DM' ya 'Scan & Send Now' karein.</i>"

    text = (
        f"╔══════════════════════════╗\n"
        f"  👥 <b>SAVED SCRAPED LEADS POOL</b>\n"
        f"╚══════════════════════════╝\n"
        f"Groups ke last 500 messages scan karke jo active usernames save kiye gaye hain unki summary:\n\n"
        f"📊 <b>DATABASE OVERVIEW:</b>\n"
        f"┌ 📥 <b>Total Scraped Leads:</b> <code>{stats['total']}</code>\n"
        f"├ ⏳ <b>Pending DMs:</b> <code>{stats['pending']} Leads</code>\n"
        f"└ ✅ <b>Already Delivered:</b> <code>{stats['contacted']} Leads</code>\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"🔍 <b>Recent Discovered Leads:</b>\n"
        f"{sample_disp}\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"💡 <i>Aap sabhi usernames ko .TXT file me export kar sakte hain ya clear kar sakte hain.</i>"
    )

    kb_leads = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📥 Export Leads (.TXT)", callback_data="autodm_export_leads"),
            InlineKeyboardButton(text="🗑 Clear Saved Leads", callback_data="autodm_clear_scraped"),
        ],
        [
            InlineKeyboardButton(text="Back to Auto DM", callback_data="auto_dm_menu")
        ]
    ])
    await call.message.edit_text(text, reply_markup=kb_leads, parse_mode="HTML")


@router.callback_query(F.data == "autodm_export_leads")
async def btn_autodm_export_leads(call: CallbackQuery, bot: Bot):
    user_id = call.from_user.id
    leads = await db.get_all_scraped_leads_list(user_id, limit=10000)
    if not leads:
        await call.answer("⚠️ Koi leads save nahi hain!", show_alert=True)
        return

    await call.answer("📄 Exporting leads file...")
    os.makedirs("assets/exports", exist_ok=True)
    export_path = f"assets/exports/scraped_leads_{user_id}.txt"
    with open(export_path, "w", encoding="utf-8") as f:
        f.write(f"SHADOW ADS BOT - SCRAPED LEADS EXPORT\n")
        f.write(f"Total Leads: {len(leads)}\n")
        f.write("="*50 + "\n\n")
        for idx, l in enumerate(leads, 1):
            uname = f"@{l['username']}" if l.get('username') else f"ID: {l.get('lead_id')}"
            status = "DELIVERED" if l.get('is_contacted') else "PENDING"
            grp = l.get('group_title') or "Group"
            f.write(f"{idx}. {uname} | Name: {l.get('first_name', '')} | Status: {status} | Source: {grp}\n")

    doc = FSInputFile(export_path, filename=f"scraped_leads_{user_id}.txt")
    await bot.send_document(
        call.message.chat.id,
        document=doc,
        caption=f"📁 <b>Scraped Leads Export</b>\n\nTotal <code>{len(leads)}</code> leads successfully exported!",
        parse_mode="HTML"
    )


@router.callback_query(F.data == "autodm_clear_scraped")
async def btn_autodm_clear_scraped(call: CallbackQuery):
    user_id = call.from_user.id
    await db.clear_scraped_leads(user_id)
    await call.answer("🗑 Saved Leads pool clear kar diya gaya!", show_alert=True)
    text, markup = await render_autodm_dashboard(user_id)
    await call.message.edit_text(text, reply_markup=markup, parse_mode="HTML")


# --- SET TARGET LEADS (CUSTOM LIST) ---
@router.callback_query(F.data == "set_autodm_targets")
async def btn_set_autodm_targets(call: CallbackQuery, state: FSMContext):
    await call.answer()
    text = (
        f"╔══════════════════════════╗\n"
        f"  👥 <b>CUSTOM TARGET LEADS LIST</b>\n"
        f"╚══════════════════════════╝\n"
        f"Jin usernames ya user IDs ko private message bhejna chahte hain unhe yahan paste karein.\n\n"
        f"• Format: Har username ko nayi line me paste karein:\n"
        f"<code>@username1\n@username2\n@username3</code>\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"👉 <i>Paste your list here:</i>"
    )
    await state.set_state(AutoDMStates.waiting_custom_targets)
    await call.message.edit_text(text, parse_mode="HTML", reply_markup=kb.get_autodm_back_keyboard())


@router.message(AutoDMStates.waiting_custom_targets)
async def process_custom_targets(message: Message, bot: Bot, state: FSMContext):
    user_id = message.from_user.id
    raw = message.text.strip()
    targets = [x.strip() for x in raw.replace(",", "\n").split("\n") if x.strip()]

    await db.update_user_setting(user_id, "autodm_custom_targets", "\n".join(targets))
    await db.update_user_setting(user_id, "autodm_target_mode", "custom_list")
    await state.clear()

    await message.answer(f"✅ <b>{len(targets)} Target Leads successfully saved!</b>", parse_mode="HTML")

    text, markup = await render_autodm_dashboard(user_id)
    await bot.send_message(message.chat.id, text, reply_markup=markup, parse_mode="HTML")


# --- SET KEYWORDS (WORD FILTER) ---
@router.callback_query(F.data == "set_autodm_keywords")
async def btn_set_autodm_keywords(call: CallbackQuery, state: FSMContext):
    await call.answer()
    user_id = call.from_user.id
    settings = await db.get_user_settings(user_id)
    current_kws = settings.get("autodm_keywords", "") or ""

    text = (
        f"╔══════════════════════════╗\n"
        f"  🔍 <b>GROUP CHAT KEYWORD FILTER</b>\n"
        f"╚══════════════════════════╝\n"
        f"Group chats ke <b>last 500 messages</b> me se ONLY unhi users ko save aur DM kiya jayega jo aapka specific word/keyword likhenge!\n\n"
        f"• <b>Current Keywords:</b> <code>{current_kws or 'None (All active chatters)'}</code>\n\n"
        f"💡 <i>Example keywords:</i>\n"
        f"<code>buy\nsell\nescrow\nprice\nneed</code>\n\n"
        f"👉 <i>Aap ek ya multiple keywords har line me likh kar send karein.\nFilter band karne ke liye <code>clear</code> ya <code>off</code> likhein:</i>"
    )
    await state.set_state(AutoDMStates.waiting_keywords)
    await call.message.edit_text(text, parse_mode="HTML", reply_markup=kb.get_autodm_back_keyboard())


@router.message(AutoDMStates.waiting_keywords)
async def process_autodm_keywords(message: Message, bot: Bot, state: FSMContext):
    user_id = message.from_user.id
    raw = message.text.strip()

    if raw.lower() in ("clear", "off", "none", "disable", "remove"):
        await db.update_user_setting(user_id, "autodm_keywords", "")
        await state.clear()
        await message.answer("✅ <b>Keyword Filter Disabled!</b> Ab last 500 msgs ke sabhi active chatters target honge.", parse_mode="HTML")
    else:
        kws = [k.strip().lower() for k in raw.replace(",", "\n").split("\n") if k.strip()]
        val = "\n".join(kws)
        await db.update_user_setting(user_id, "autodm_keywords", val)
        await state.clear()
        await message.answer(
            f"✅ <b>Word Filter Saved!</b>\n\nAb GC ke last 500 messages me se ONLY in words ko likhne wale users ko DM jayega:\n<code>{', '.join(kws)}</code>",
            parse_mode="HTML"
        )

    text, markup = await render_autodm_dashboard(user_id)
    await bot.send_message(message.chat.id, text, reply_markup=markup, parse_mode="HTML")


# --- SET AUTO-REPLY TO LEADS ---
@router.callback_query(F.data == "set_autodm_autoreply")
async def btn_set_autodm_autoreply(call: CallbackQuery, state: FSMContext):
    await call.answer()
    user_id = call.from_user.id
    settings = await db.get_user_settings(user_id)
    current_ar = settings.get("autodm_auto_reply", "") or ""

    text = (
        f"╔══════════════════════════╗\n"
        f"  🤖 <b>SET AUTO-REPLY TO LEADS</b>\n"
        f"╚══════════════════════════╝\n"
        f"Jab koi lead aapke account ke DM me response/reply dega, toh aapka account usse <b>automatically</b> yeh message reply kar dega!\n\n"
        f"• <b>Current Auto-Reply:</b>\n"
        f"<blockquote>{current_ar or 'None (Disabled)'}</blockquote>\n\n"
        f"👉 <i>Apna auto-response message text yahan send karein.\nAuto-reply band karne ke liye <code>clear</code> ya <code>off</code> likhein:</i>"
    )
    await state.set_state(AutoDMStates.waiting_auto_reply)
    await call.message.edit_text(text, parse_mode="HTML", reply_markup=kb.get_autodm_back_keyboard())


@router.message(AutoDMStates.waiting_auto_reply)
async def process_autodm_autoreply(message: Message, bot: Bot, state: FSMContext):
    user_id = message.from_user.id
    raw = (message.html_text or message.text or "").strip()

    if raw.lower() in ("clear", "off", "none", "disable", "remove"):
        await db.update_user_setting(user_id, "autodm_auto_reply", None)
        await state.clear()
        await message.answer("✅ <b>Auto-Reply Disabled!</b> Leads ko koi automatic reply nahi jayega.", parse_mode="HTML")
    else:
        await db.update_user_setting(user_id, "autodm_auto_reply", raw)
        await state.clear()
        await message.answer(
            f"✅ <b>Lead Auto-Reply Saved!</b>\n\nJab bhi koi lead aapke account ko DM me reply karega, usse automatically yeh reply bhej diya jayega:\n\n<blockquote>{raw}</blockquote>",
            parse_mode="HTML"
        )

    text, markup = await render_autodm_dashboard(user_id)
    await bot.send_message(message.chat.id, text, reply_markup=markup, parse_mode="HTML")


# --- SCAN & SEND NOW (MANUAL TRIGGER) ---
@router.callback_query(F.data == "autodm_send_now")
async def btn_autodm_send_now(call: CallbackQuery, bot: Bot):
    user_id = call.from_user.id
    settings = await db.get_user_settings(user_id)
    accounts = await db.get_user_accounts(user_id)

    if not accounts:
        await call.answer("⚠️ Pehle accounts add karein!", show_alert=True)
        return

    dm_msg = settings.get("autodm_message") or settings.get("ad_message")
    dm_media = settings.get("autodm_media_id") or settings.get("ad_media_id")
    if not dm_msg and not dm_media:
        await call.answer("⚠️ Pehle 'Set DM Message' set karein!", show_alert=True)
        return

    await call.answer("🚀 500 Messages Scan aur DM dispatch shuru ho raha hai...")
    await bot.send_message(
        call.message.chat.id,
        f"🚀 <b>Manual 10-Min Scan & DM Batch Started!</b>\n\n"
        f"1. Groups ke 500 new messages scan karke usernames save kiye ja rahe hain...\n"
        f"2. Sabhi {len(accounts)} accounts se targeted DMs dispatch ho rahe hain...",
        parse_mode="HTML"
    )

    hourly_rate = int(settings.get("autodm_rate_per_hour", 10) or 10)
    round_quota = max(1, round(hourly_rate / 6))
    local_media = None
    if dm_media and os.path.exists(dm_media):
        local_media = dm_media

    async def run_manual_batch():
        new_scraped = 0
        mode = settings.get("autodm_target_mode", "groups")
        if mode == "groups":
            try:
                new_scraped = await scan_and_save_group_leads(user_id, accounts, settings, max_messages=500)
            except Exception as e:
                logger.error(f"Manual scan error: {e}")

        tasks = [
            dispatch_single_account_autodm(bot, user_id, acc, settings, local_media, round_quota)
            for acc in accounts
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        s_total = sum(r[0] for r in results if isinstance(r, tuple))
        f_total = sum(r[1] for r in results if isinstance(r, tuple))
        leads_stats = await db.get_scraped_leads_stats(user_id)

        try:
            await bot.send_message(
                user_id,
                f"✅ <b>Manual Batch Completed!</b>\n\n"
                f"• 📥 <b>New Usernames Saved:</b> <code>+{new_scraped} Leads</code>\n"
                f"• 👥 <b>Total Saved in DB:</b> <code>{leads_stats['total']} Leads</code> (<code>{leads_stats['pending']}</code> Pending)\n"
                f"• 📤 <b>Sent This Batch:</b> <code>{s_total} DMs</code>\n"
                f"• ⚠️ <b>Skipped/Privacy:</b> <code>{f_total}</code>",
                parse_mode="HTML"
            )
        except Exception:
            pass

    asyncio.create_task(run_manual_batch())


# --- RESET LEADS DB ---
@router.callback_query(F.data == "autodm_reset_leads")
async def btn_autodm_reset_leads(call: CallbackQuery):
    user_id = call.from_user.id
    await db.clear_contacted_leads(user_id)
    await call.answer("♻️ Contacted Leads database clear ho gaya! Ab sabhi leads ko dobara DM bheja ja sakta hai.", show_alert=True)
    text, markup = await render_autodm_dashboard(user_id)
    await call.message.edit_text(text, reply_markup=markup, parse_mode="HTML")


# --- AUTO-RESUME ON STARTUP ---
async def resume_active_autodm_campaigns(bot: Bot):
    """Resumes all active Auto DM tasks upon bot reboot."""
    try:
        if hasattr(db, "get_active_autodm_users"):
            running_users = await db.get_active_autodm_users()
            for uid in running_users:
                if uid not in active_autodm_tasks or active_autodm_tasks[uid].done():
                    logger.info(f"Auto-resuming 10-Minute Auto DM campaign for user {uid}...")
                    task = asyncio.create_task(run_user_autodm_campaign(bot, uid))
                    active_autodm_tasks[uid] = task
    except Exception as e:
        logger.warning(f"Could not auto-resume Auto DM campaigns: {e}")
