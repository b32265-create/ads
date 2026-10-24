import os
import io
import json
import logging
import asyncio
import html
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, PhotoSize, Video, Document, FSInputFile, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

import time
from config import ADMIN_IDS
import database as db
import keyboards as kb
from banner_generator import generate_user_welcome_banner, CACHE_DIR
from middlewares.force_join import check_user_force_join
from emojis import (
    ID_HEART_FIRE, ID_DIAMOND, ID_BACK, ID_USER, ID_STAR, ID_TRASH, ID_WARNING,
    ID_FIRE, ID_PLANE, ID_MSG, ID_INTERVAL, ID_DELAY, ID_TARGET, ID_MOON,
    ID_RUNNING, ID_PAUSED, ID_SPARKLE, ID_VERIFIED, ID_GIFT, ID_FLASH, ID_MONEY,
    ID_ROCKET,
    EMOJI_FIRE, EMOJI_HEART_FIRE, EMOJI_PLANE, EMOJI_MSG, EMOJI_WARNING,
    EMOJI_INTERVAL, EMOJI_DELAY, EMOJI_TARGET, EMOJI_MOON, EMOJI_RUNNING,
    EMOJI_PAUSED, EMOJI_AI, EMOJI_VERIFIED, EMOJI_STAR, EMOJI_FLASH, EMOJI_MONEY,
    EMOJI_ROCKET, EMOJI_COOL, EMOJI_USER, EMOJI_PHONE, EMOJI_BACK, EMOJI_CROSS,
    EMOJI_CLOCK, EMOJI_STATS, EMOJI_PIN, EMOJI_GEAR, EMOJI_DIAMOND, EMOJI_SPARKLE,
    EMOJI_GIFT, EMOJI_TRASH
)

logger = logging.getLogger(__name__)

router = Router(name="user_router")

class UserStates(StatesGroup):
    waiting_ad_message = State()
    waiting_custom_interval = State()
    waiting_custom_delay = State()
    waiting_custom_cycles = State()
    waiting_exclude_groups = State()
    waiting_autojoin_links = State()
    waiting_schedule_start = State()
    waiting_schedule_end = State()
    waiting_forward_account = State()

# Persistent ultra-fast disk+RAM cache for welcome banners & log account
BANNER_FILE_IDS_PATH = os.path.join(CACHE_DIR, "banner_file_ids.json")
_USER_BANNER_FILE_ID: dict = {}
_CACHED_LOG_ACCOUNT: str = ""
_CACHED_LOG_ACCOUNT_TIME: float = 0.0

def load_banner_file_ids():
    global _USER_BANNER_FILE_ID
    try:
        if os.path.exists(BANNER_FILE_IDS_PATH):
            with open(BANNER_FILE_IDS_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                _USER_BANNER_FILE_ID = {int(k): v for k, v in data.items()}
    except Exception as e:
        logger.warning(f"Could not load banner file ids: {e}")

def save_banner_file_id(user_id: int, file_id: str):
    _USER_BANNER_FILE_ID[user_id] = file_id
    try:
        with open(BANNER_FILE_IDS_PATH, "w", encoding="utf-8") as f:
            json.dump(_USER_BANNER_FILE_ID, f)
    except Exception as e:
        logger.warning(f"Could not persist banner file id: {e}")

load_banner_file_ids()

def format_interval(seconds: int) -> str:
    if not seconds or seconds <= 0:
        return "Not Set"
    if seconds >= 3600:
        hours = seconds // 3600
        mins = (seconds % 3600) // 60
        return f"{hours}h {mins}m" if mins else f"{hours}h"
    if seconds >= 60:
        return f"{seconds // 60}m"
    return f"{seconds}s"

def build_dashboard_text(bot_username: str, accounts_count: int, settings: dict, user_info: dict = None) -> str:
    user_info = user_info or {}
    is_premium = user_info.get("is_premium", 0)
    first_name = html.escape(str(user_info.get("first_name") or "User"))
    tier_badge = f"{EMOJI_DIAMOND} <b>VIP PRO</b>" if is_premium else f"{EMOJI_FLASH} <b>Standard Free</b>"
    limit_note = "<i>(Unlimited ∞)</i>" if is_premium else "<i>(Max 5)</i>"

    ad_msg = settings.get("ad_message")
    ad_media = settings.get("ad_media_id")
    media_type = settings.get("ad_media_type")
    if ad_msg or ad_media:
        type_str = f" [{media_type.upper()}]" if media_type else ""
        ad_status = f"{EMOJI_VERIFIED} Set{type_str}"
    else:
        ad_status = f"{EMOJI_WARNING} Not Set"

    interval = settings.get("cycle_interval", 0)
    interval_display = format_interval(interval)
    if interval_display == "Not Set":
        interval_display = f"{EMOJI_WARNING} Not Set"

    delay = settings.get("message_delay", 5)
    target = settings.get("target_type", "Groups")

    max_c = settings.get("max_cycles", 0)
    max_c_str = "∞" if max_c == 0 else str(max_c)
    cycles_done = settings.get("completed_cycles", 0)

    status = settings.get("status", "Paused")
    if status.lower() == "running":
        status_display = f"{EMOJI_RUNNING} <b>ACTIVE & BROADCASTING</b>"
    else:
        status_display = f"{EMOJI_PAUSED} <b>IDLE / PAUSED</b>"

    sched_enabled = settings.get("schedule_enabled", 0)
    sched_start = settings.get("schedule_start") or "--:--"
    sched_end = settings.get("schedule_end") or "--:--"
    if sched_enabled:
        sched_status = f"{EMOJI_RUNNING} {sched_start} ➔ {sched_end}"
    else:
        sched_status = f"{EMOJI_PAUSED} OFF"

    mgr_enabled = settings.get("manager_enabled", 1)
    mgr_status = f"{EMOJI_VERIFIED} ON" if mgr_enabled else f"{EMOJI_PAUSED} OFF"

    autodm_enabled = settings.get("autodm_enabled", 0)
    autodm_rate = settings.get("autodm_rate_per_round") or 1
    autodm_interval = settings.get("autodm_interval_minutes", 5)
    autodm_status = f"{EMOJI_RUNNING} ON ({autodm_rate}/{autodm_interval}m)" if autodm_enabled else f"{EMOJI_PAUSED} OFF"

    return (
        f"╔══════════════════════════╗\n"
        f"  {EMOJI_FIRE} <b>ATOMIC ADS AUTOMATION</b> 🐲\n"
        f"╚══════════════════════════╝\n"
        f"👤 <b>User:</b> {first_name} | {tier_badge}\n"
        f"🤖 <b>Bot:</b> @{bot_username}\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"📊 <b>CAMPAIGN OVERVIEW & CONFIG</b>\n"
        f"┌ {EMOJI_PLANE} <b>Hosted Accounts:</b> <code>{accounts_count}</code> {limit_note}\n"
        f"├ {EMOJI_MSG} <b>Ad Content:</b> <b>{ad_status}</b>\n"
        f"├ {EMOJI_TARGET} <b>Target Chats:</b> <code>{target}</code>\n"
        f"├ {EMOJI_INTERVAL} <b>Cycle Interval:</b> <code>{interval_display}</code>\n"
        f"├ {EMOJI_DELAY} <b>Message Delay:</b> <code>{delay}s</code>\n"
        f"├ {EMOJI_MOON} <b>Progress Cycles:</b> <code>{cycles_done} / {max_c_str}</code>\n"
        f"├ {EMOJI_CLOCK} <b>Schedule Window:</b> <code>{sched_status}</code>\n"
        f"├ {EMOJI_USER} <b>Manager Account:</b> <code>{mgr_status}</code>\n"
        f"├ 🤖 <b>AI Auto-Reply & Deal:</b> <code>⚡ Smart Assistant Ready</code>\n"
        f"└ {status_display}\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"💡 <i>Niche diye gaye control panel se action select karein:</i>"
    )

_CACHED_BOT_USERNAME: str = ""

async def get_bot_username(bot: Bot) -> str:
    global _CACHED_BOT_USERNAME
    if not _CACHED_BOT_USERNAME:
        bot_info = await bot.get_me()
        _CACHED_BOT_USERNAME = bot_info.username or "Atomic_Ads_Robot"
    return _CACHED_BOT_USERNAME

async def check_user_system_accounts_status(user_id: int):
    """
    Checks if Log and Manager accounts are configured, and whether user has messaged them.
    If user has disabled manager_enabled in their settings, manager account is not required for them!
    Returns: (is_required: bool, is_all_ok: bool, log_acc: str, has_log: bool, mgr_acc: str, has_mgr: bool)
    """
    settings = await db.get_user_settings(user_id)
    user_mgr_enabled = settings.get("manager_enabled", 1)

    log_acc = await db.get_log_account()
    mgr_acc = await db.get_manager_account() if user_mgr_enabled else None
    has_log, has_mgr = await db.has_user_messaged_accounts(user_id)

    req_log = bool(log_acc)
    req_mgr = bool(mgr_acc)

    if not req_log and not req_mgr:
        return False, True, "", True, "", True

    ok_log = (not req_log) or has_log
    ok_mgr = (not req_mgr) or has_mgr
    is_all_ok = ok_log and ok_mgr

    return True, is_all_ok, (log_acc or ""), has_log, (mgr_acc or ""), has_mgr

def build_accounts_verification_ui(log_acc: str, has_log: bool, mgr_acc: str, has_mgr: bool):
    status_items = []
    keyboard = []

    if log_acc:
        st_icon = f"{EMOJI_VERIFIED} <b>Verified</b>" if has_log else f"{EMOJI_CROSS} <b>Pending (Message 'Hi')</b>"
        status_items.append(f"📡 <b>Live Logs Account:</b> <a href='https://t.me/{log_acc}'>@{log_acc}</a>\n   └ Status: {st_icon}")
        if not has_log:
            keyboard.append([InlineKeyboardButton(text=f"📡 Message @{log_acc} (Send 'Hi')", url=f"https://t.me/{log_acc}")])

    if mgr_acc:
        st_icon = f"{EMOJI_VERIFIED} <b>Verified</b>" if has_mgr else f"{EMOJI_CROSS} <b>Pending (Message 'Hi')</b>"
        status_items.append(f"👔 <b>Lead Manager Account:</b> <a href='https://t.me/{mgr_acc}'>@{mgr_acc}</a>\n   └ Status: {st_icon}")
        if not has_mgr:
            keyboard.append([InlineKeyboardButton(text=f"👔 Message @{mgr_acc} (Send 'Hi')", url=f"https://t.me/{mgr_acc}")])

    accounts_block = "\n\n".join(status_items)

    text = (
        f"╔══════════════════════════╗\n"
        f"  🔐 <b>MANDATORY ACTIVATION REQUIRED</b>\n"
        f"╚══════════════════════════╝\n"
        f"Bot ko use karne ke liye aapko official <b>Log Account</b> aur <b>Manager Account</b> ko direct message (e.g. <i>'Hi'</i>) bhejna <b>compulsory</b> hai.\n\n"
        f"🛡️ <b>Kyu compulsory hai?</b>\n"
        f"Telegram peer-flood restriction ke kaaran, jab tak aap un accounts ko pehle message nahi karte, tab tak bot aapko live ad delivery logs aur lead inquiries forward nahi kar sakta.\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"{accounts_block}\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"👉 <i>Accounts ke link par click karke 'Hi' bhejein, fir neeche 'Check Verification' dabayein!</i>"
    )

    keyboard.append([
        InlineKeyboardButton(text="✅ Check Verification / Unlock", callback_data="check_accounts_messaged")
    ])

    return text, InlineKeyboardMarkup(inline_keyboard=keyboard)

async def show_dashboard(bot: Bot, chat_id: int, user_id: int, message_to_edit: Message = None):
    """Utility to render and send/edit the exact dashboard with premium styling."""
    if user_id not in ADMIN_IDS:
        is_required, is_all_ok, log_acc, has_log, mgr_acc, has_mgr = await check_user_system_accounts_status(user_id)
        if is_required and not is_all_ok:
            text, markup = build_accounts_verification_ui(log_acc, has_log, mgr_acc, has_mgr)
            if message_to_edit:
                try:
                    await message_to_edit.edit_text(text, reply_markup=markup, parse_mode="HTML")
                    return
                except Exception:
                    pass
            await bot.send_message(chat_id, text, reply_markup=markup, parse_mode="HTML")
            return

    bot_username = await get_bot_username(bot)

    accounts_count, settings, user_info = await asyncio.gather(
        db.get_account_count(user_id),
        db.get_user_settings(user_id),
        db.get_user_info(user_id)
    )

    text = build_dashboard_text(bot_username, accounts_count, settings, user_info)
    markup = kb.get_dashboard_keyboard(
        msg_delay=settings.get("message_delay", 5),
        target=settings.get("target_type", "Groups"),
        schedule_enabled=settings.get("schedule_enabled", 0),
        manager_enabled=settings.get("manager_enabled", 1)
    )

    if message_to_edit:
        try:
            await message_to_edit.edit_text(text, reply_markup=markup, parse_mode="HTML")
            return
        except Exception:
            pass

    await bot.send_message(chat_id, text, reply_markup=markup, parse_mode="HTML")


# --- START COMMAND ---
@router.message(CommandStart())
async def cmd_start(message: Message, bot: Bot, state: FSMContext):
    try:
        await state.clear()
        user_id = message.from_user.id
        username = message.from_user.username
        first_name = message.from_user.first_name

        # 1. Register user in DB first (0ms if already known in RAM cache)
        await db.get_or_create_user(user_id, username, first_name)

        # 2. Check for referral payload: e.g. /start ref_12345678 or /start 12345678
        args = message.text.split()[1] if len(message.text.split()) > 1 else ""
        if args:
            ref_raw = args.replace("ref_", "").strip()
            if ref_raw.isdigit():
                referrer_id = int(ref_raw)
                try:
                    is_counted, new_count, unlocked_reward = await db.record_user_referral(user_id, referrer_id)
                    if is_counted:
                        reward_msg = (
                            f"\n\n🎁 <b>BONUS REWARD ACTIVATED!</b>\n"
                            f"Har 1 referral par <b>2 Days VIP Premium Access FREE</b> milta hai!\n"
                            f"Aapke account par <b>+2 Days VIP Access</b> automatically add ho gaya hai! 🚀"
                        )
                        try:
                            safe_full_name = html.escape(message.from_user.full_name or "New User")
                            await bot.send_message(
                                referrer_id,
                                f"╔══════════════════════════╗\n"
                                f"  🎉 <b>NEW REFERRAL JOINED!</b>\n"
                                f"╚══════════════════════════╝\n"
                                f"Aapke referral link se naya user jud gaya hai:\n"
                                f"• 👤 <b>User:</b> <code>{safe_full_name}</code>\n"
                                f"• 👥 <b>Total Referrals:</b> <code>{new_count}</code>"
                                + reward_msg,
                                parse_mode="HTML"
                            )
                            try:
                                from account_branding import sync_all_user_accounts_branding
                                asyncio.create_task(sync_all_user_accounts_branding(referrer_id, bot=bot))
                            except Exception:
                                pass
                        except Exception as ref_err:
                            logger.warning(f"Could not notify referrer {referrer_id}: {ref_err}")
                except Exception as e:
                    logger.warning(f"Error handling referral: {e}")

        # 3. Parallel check for user info and force join
        user_info, (is_joined, unjoined) = await asyncio.gather(
            db.get_user_info(user_id),
            check_user_force_join(bot, user_id)
        )

        if user_info and user_info.get('is_banned', 0):
            await message.answer(
                f"╔══════════════════════════╗\n"
                f"  {EMOJI_CROSS} <b>ACCOUNT SUSPENDED</b>\n"
                f"╚══════════════════════════╝\n"
                f"Aapka account system dwara ban kar diya gaya hai.\n\n"
                f"Contact admin if you think this is an error.",
                parse_mode="HTML"
            )
            return

        if not is_joined:
            await message.answer(
                f"╔══════════════════════════╗\n"
                f"  {EMOJI_WARNING} <b>ACCESS RESTRICTED</b>\n"
                f"╚══════════════════════════╝\n"
                f"Bot ko use karne ke liye pehle hamare official channels join karein:\n\n"
                f"<i>Join karne ke baad 'Joined / Try Again' par click karein.</i>",
                parse_mode="HTML",
                reply_markup=kb.get_force_join_keyboard(unjoined)
            )
            return

        # 4. 🚀 DIRECT TO CONTROL DASHBOARD (Instant sub-100ms response!)
        await show_dashboard(bot, message.chat.id, user_id)

    except Exception as e:
        logger.exception(f"Unhandled error in cmd_start for user {message.from_user.id}: {e}")
        try:
            await message.answer(
                f"⚠️ <b>Bot Start Error</b>\n\n"
                f"Kuch technical issue ke kaaran request process nahi ho saki.\n"
                f"Kripya <code>/start</code> dobara try karein.",
                parse_mode="HTML"
            )
        except Exception:
            pass

# --- VERIFY FORCE JOIN ---
@router.callback_query(F.data == "verify_force_join")
async def verify_force_join(call: CallbackQuery, bot: Bot):
    user_id = call.from_user.id
    is_joined, unjoined = await check_user_force_join(bot, user_id)
    if not is_joined:
        await call.answer("You haven't joined all channels yet! Please join and try again.", show_alert=True)
        return
        
    await call.answer("Verified successfully!")
    await show_dashboard(bot, call.message.chat.id, user_id, message_to_edit=call.message)

# --- BACK TO DASHBOARD ---
@router.callback_query(F.data == "back_to_dashboard")
async def back_to_dash(call: CallbackQuery, bot: Bot, state: FSMContext):
    await state.clear()
    await call.answer()
    user_id = call.from_user.id
    if user_id not in ADMIN_IDS:
        is_required, is_all_ok, log_acc, has_log, mgr_acc, has_mgr = await check_user_system_accounts_status(user_id)
        if is_required and not is_all_ok:
            text, markup = build_accounts_verification_ui(log_acc, has_log, mgr_acc, has_mgr)
            if call.message.photo or call.message.video or call.message.animation or call.message.document:
                try:
                    await call.message.delete()
                except Exception:
                    pass
                await bot.send_message(call.message.chat.id, text, reply_markup=markup, parse_mode="HTML")
            else:
                await call.message.edit_text(text, reply_markup=markup, parse_mode="HTML")
            return

    if call.message.photo or call.message.video or call.message.animation or call.message.document:
        try:
            await call.message.delete()
        except Exception:
            pass
        await show_dashboard(bot, call.message.chat.id, call.from_user.id)
    else:
        await show_dashboard(bot, call.message.chat.id, call.from_user.id, message_to_edit=call.message)

# --- CHECK MANDATORY ACCOUNTS MESSAGED ---
@router.callback_query(F.data == "check_accounts_messaged")
async def callback_check_accounts_messaged(call: CallbackQuery, bot: Bot):
    user_id = call.from_user.id
    is_required, is_all_ok, log_acc, has_log, mgr_acc, has_mgr = await check_user_system_accounts_status(user_id)
    if user_id in ADMIN_IDS:
        is_all_ok = True

    if not is_all_ok:
        missing = []
        if log_acc and not has_log:
            missing.append(f"• 📡 Logs: @{log_acc}")
        if mgr_acc and not has_mgr:
            missing.append(f"• 👔 Manager: @{mgr_acc}")
        alert_txt = (
            "⚠️ Verification Incomplete!\n\n"
            "Aapne abhi tak in accounts ko message nahi bheja hai:\n"
            + "\n".join(missing) + "\n\n"
            "Kripya direct message me 'Hi' bhej kar confirm karein."
        )
        await call.answer(alert_txt, show_alert=True)

        text, markup = build_accounts_verification_ui(log_acc, has_log, mgr_acc, has_mgr)
        if not (call.message.photo or call.message.video):
            try:
                await call.message.edit_text(text, reply_markup=markup, parse_mode="HTML")
            except Exception:
                pass
        return

    await call.answer("🎉 Verification Successful! Control Dashboard unlocked.", show_alert=True)
    if call.message.photo or call.message.video:
        try:
            await call.message.delete()
        except Exception:
            pass
        await show_dashboard(bot, call.message.chat.id, user_id)
    else:
        await show_dashboard(bot, call.message.chat.id, user_id, message_to_edit=call.message)

# --- TOGGLE MANAGER ACCOUNT ---
@router.callback_query(F.data == "toggle_manager_account")
async def callback_toggle_manager_account(call: CallbackQuery, bot: Bot):
    user_id = call.from_user.id
    settings = await db.get_user_settings(user_id)
    current = settings.get("manager_enabled", 1)
    new_val = 0 if current else 1

    await db.update_user_setting(user_id, "manager_enabled", new_val)

    if new_val:
        alert_msg = "🟢 Manager Account Relay: ENABLED (ON)!\nAapke accounts ke lead DMs manager account par sync honge."
    else:
        alert_msg = "🔴 Manager Account Relay: DISABLED (OFF)!\nAapke accounts ke lead DMs manager account par forward nahi honge."

    await call.answer(alert_msg, show_alert=True)
    await show_dashboard(bot, call.message.chat.id, user_id, message_to_edit=call.message)

# --- SET AD MESSAGE (Text + Media) ---
@router.callback_query(F.data == "set_ad_msg")
async def btn_set_ad_msg(call: CallbackQuery, state: FSMContext):
    await call.answer()
    user_id = call.from_user.id
    settings = await db.get_user_settings(user_id)
    current_ad = settings.get("ad_message") or "None"
    has_media = bool(settings.get("ad_media_id"))
    media_note = f"\n📎 <b>Media Attached:</b> Yes" if has_media else ""

    text = (
        f"╔══════════════════════════╗\n"
        f"  {EMOJI_MSG} <b>SET ADVERT CONTENT</b>\n"
        f"╚══════════════════════════╝\n"
        f"{EMOJI_STAR} <b>Current Active Ad:</b>\n"
        f"<blockquote>{current_ad}</blockquote>{media_note}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"{EMOJI_SPARKLE} <b>Supported Ad Formats:</b>\n"
        f"• {EMOJI_MSG} <b>Text Message:</b> Sirf text type karke bhejein\n"
        f"• {EMOJI_HEART_FIRE} <b>Media (Photo/Video/Doc):</b> Media send karein (Caption = Ad text)\n"
        f"• {EMOJI_PIN} Caption optional hai (Bina caption bhi chalega)\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"👉 <i>Abhi apna naya ad content ya media yahan send karein:</i>"
    )
    await state.set_state(UserStates.waiting_ad_message)
    await call.message.edit_text(text, parse_mode="HTML", reply_markup=kb.get_back_keyboard())

@router.message(UserStates.waiting_ad_message)
async def process_ad_message(message: Message, bot: Bot, state: FSMContext):
    user_id = message.from_user.id

    # Detect media type and preserve HTML / custom premium emojis
    ad_text = message.html_text if (message.text or message.caption) else ""
    media_id = None
    media_type = None

    os.makedirs("assets/ad_media", exist_ok=True)
    if message.photo:
        media_type = "photo"
        local_path = f"assets/ad_media/{user_id}.jpg"
        try:
            await bot.download(message.photo[-1], destination=local_path)
            media_id = local_path
        except Exception:
            media_id = str(message.photo[-1].file_id)
    elif message.video:
        media_type = "video"
        local_path = f"assets/ad_media/{user_id}.mp4"
        try:
            await bot.download(message.video, destination=local_path)
            media_id = local_path
        except Exception:
            media_id = str(message.video.file_id)
    elif message.document:
        media_type = "document"
        local_path = f"assets/ad_media/{user_id}_doc.dat"
        try:
            await bot.download(message.document, destination=local_path)
            media_id = local_path
        except Exception:
            media_id = str(message.document.file_id)
    elif message.animation:
        media_type = "animation"
        local_path = f"assets/ad_media/{user_id}_anim.mp4"
        try:
            await bot.download(message.animation, destination=local_path)
            media_id = local_path
        except Exception:
            media_id = str(message.animation.file_id)

    if not ad_text and not media_id:
        await message.answer(
            f"{EMOJI_CROSS} <b>Kuch bhi receive nahi hua!</b>\nText ya media (photo/video/doc) bhejein.",
            parse_mode="HTML",
            reply_markup=kb.get_back_keyboard()
        )
        return

    await db.update_user_setting(user_id, "ad_message", ad_text)
    await db.update_user_setting(user_id, "ad_media_id", media_id)
    await db.update_user_setting(user_id, "ad_media_type", media_type)
    await state.clear()

    media_note = f"\n📎 <b>Media Format:</b> <code>{media_type.upper()}</code>" if media_id else ""
    await message.answer(
        f"{EMOJI_VERIFIED} <b>Ad Content Saved Successfully!</b>{media_note}\n\n"
        f"Aap <b>Preview Ad</b> button se apna naya ad check kar sakte hain.",
        parse_mode="HTML"
    )
    await show_dashboard(bot, message.chat.id, user_id)

# --- SET INTERVAL ---
@router.callback_query(F.data == "set_interval")
async def btn_set_interval(call: CallbackQuery):
    await call.answer()
    text = (
        f"╔══════════════════════════╗\n"
        f"  {EMOJI_INTERVAL} <b>CYCLE INTERVAL CONFIG</b>\n"
        f"╚══════════════════════════╝\n"
        f"Ek campaign cycle complete hone ke baad agli cycle shuru hone ka pause time select karein.\n\n"
        f"• 👑 <b>1 Min / 5 Mins:</b> VIP Turbo Speed\n"
        f"• ⏱️ <b>10 Mins / 30 Mins:</b> Standard Free Intervals\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"👉 Niche pre-set ya custom intervals chunein:"
    )
    await call.message.edit_text(text, parse_mode="HTML", reply_markup=kb.get_interval_keyboard())

@router.callback_query(F.data.startswith("interval_"))
async def process_interval_choice(call: CallbackQuery, bot: Bot, state: FSMContext):
    val = call.data.replace("interval_", "")
    user_id = call.from_user.id
    user_info = await db.get_user_info(user_id)
    is_vip = bool(user_info and user_info.get("is_premium", 0)) or (user_id in ADMIN_IDS)
    
    if val == "custom":
        await call.answer()
        await state.set_state(UserStates.waiting_custom_interval)
        await call.message.edit_text(
            f"╔══════════════════════════╗\n"
            f"  {EMOJI_SPARKLE} <b>CUSTOM INTERVAL</b>\n"
            f"╚══════════════════════════╝\n"
            f"Seconds me custom time enter karein:\n\n"
            f"• <code>600</code> = 10 Minutes\n"
            f"• <code>900</code> = 15 Minutes\n"
            f"• <code>1800</code> = 30 Minutes\n\n"
            f"👑 <i>Note: 1m aur 5m intervals sirf VIP members ke liye hain.</i>\n\n"
            f"👉 <i>Number send karein (Free: Minimum 600s / 10m):</i>",
            parse_mode="HTML",
            reply_markup=kb.get_back_keyboard()
        )
        return
        
    seconds = int(val)
    if not is_vip and seconds <= 300:
        await call.answer("👑 1 Min aur 5 Mins intervals sirf VIP members ke liye hain!", show_alert=True)
        await btn_premium(call)
        return

    await db.update_user_setting(user_id, "cycle_interval", seconds)
    await call.answer(f"Interval set to {format_interval(seconds)}!")
    await show_dashboard(bot, call.message.chat.id, user_id, message_to_edit=call.message)

@router.message(UserStates.waiting_custom_interval)
async def process_custom_interval(message: Message, bot: Bot, state: FSMContext):
    user_id = message.from_user.id
    user_info = await db.get_user_info(user_id)
    is_vip = bool(user_info and user_info.get("is_premium", 0)) or (user_id in ADMIN_IDS)
    try:
        seconds = int(message.text.strip())
        if seconds < 30:
            await message.answer(f"{EMOJI_WARNING} Minimum interval 30 seconds hona chahiye.", reply_markup=kb.get_back_keyboard())
            return
        if not is_vip and seconds <= 300:
            prem_kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="💎 Upgrade to VIP (₹100)", callback_data="premium")],
                [InlineKeyboardButton(text="🔙 Back to Dashboard", callback_data="back_to_dashboard")]
            ])
            await message.answer(
                f"⚠️ <b>VIP Access Required</b>\n\n"
                f"1m se 5m turbo intervals sirf <b>VIP Members</b> ke liye available hain.\n"
                f"Free members ke liye minimum interval 10 minutes (600s) hai.\n\n"
                f"👉 VIP upgrade karein ya 10m+ set karein:",
                parse_mode="HTML",
                reply_markup=prem_kb
            )
            return
        await db.update_user_setting(user_id, "cycle_interval", seconds)
        await state.clear()
        await message.answer(f"{EMOJI_VERIFIED} <b>Interval updated to {format_interval(seconds)}!</b>", parse_mode="HTML")
        await show_dashboard(bot, message.chat.id, user_id)
    except ValueError:
        await message.answer(f"{EMOJI_CROSS} Please enter a valid number of seconds.", reply_markup=kb.get_back_keyboard())

# --- SET DELAY ---
@router.callback_query(F.data == "set_delay")
async def btn_set_delay(call: CallbackQuery):
    await call.answer()
    text = (
        f"╔══════════════════════════╗\n"
        f"  {EMOJI_DELAY} <b>MESSAGE DISPATCH DELAY</b>\n"
        f"╚══════════════════════════╝\n"
        f"Har chat me ad post karne ke beech kitna delay rakhna hai:\n\n"
        f"• 👑 <b>1s:</b> Turbo VIP Speed\n"
        f"• ⏳ <b>5s:</b> Standard Speed\n"
        f"• ⏱️ <b>10s:</b> Safe Speed\n"
        f"• 🛡️ <b>30s:</b> Extra Safe (New Accounts)\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"👉 Niche delay select karein:"
    )
    await call.message.edit_text(text, parse_mode="HTML", reply_markup=kb.get_delay_keyboard())

@router.callback_query(F.data.startswith("delay_"))
async def process_delay_choice(call: CallbackQuery, bot: Bot, state: FSMContext):
    val = call.data.replace("delay_", "")
    user_id = call.from_user.id
    user_info = await db.get_user_info(user_id)
    is_vip = bool(user_info and user_info.get("is_premium", 0)) or (user_id in ADMIN_IDS)
    
    if val == "custom":
        await call.answer()
        await state.set_state(UserStates.waiting_custom_delay)
        await call.message.edit_text(
            f"╔══════════════════════════╗\n"
            f"  {EMOJI_SPARKLE} <b>CUSTOM DELAY</b>\n"
            f"╚══════════════════════════╝\n"
            f"Messages ke beech seconds me gap enter karein:\n"
            f"<i>(Example: <code>10</code> ya <code>15</code>)</i>\n\n"
            f"👑 <i>Note: 1s se 5s turbo delay sirf VIP members ke liye hai.</i>\n\n"
            f"👉 <i>Number send karein:</i>",
            parse_mode="HTML",
            reply_markup=kb.get_back_keyboard()
        )
        return
        
    seconds = int(val)
    if not is_vip and seconds == 1:
        await call.answer("👑 1s Turbo Delay sirf VIP members ke liye hai!", show_alert=True)
        await btn_premium(call)
        return

    await db.update_user_setting(user_id, "message_delay", seconds)
    await call.answer(f"Delay set to {seconds}s!")
    await show_dashboard(bot, call.message.chat.id, user_id, message_to_edit=call.message)

@router.message(UserStates.waiting_custom_delay)
async def process_custom_delay(message: Message, bot: Bot, state: FSMContext):
    user_id = message.from_user.id
    user_info = await db.get_user_info(user_id)
    is_vip = bool(user_info and user_info.get("is_premium", 0)) or (user_id in ADMIN_IDS)
    try:
        seconds = int(message.text.strip())
        if seconds < 1:
            await message.answer(f"{EMOJI_WARNING} Minimum delay 1 second hona chahiye.", reply_markup=kb.get_back_keyboard())
            return
        if not is_vip and seconds <= 5:
            prem_kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="💎 Upgrade to VIP (₹100)", callback_data="premium")],
                [InlineKeyboardButton(text="🔙 Back to Dashboard", callback_data="back_to_dashboard")]
            ])
            await message.answer(
                f"⚠️ <b>VIP Access Required</b>\n\n"
                f"1s se 5s turbo delay sirf <b>VIP Members</b> ke liye available hai.\n"
                f"Free members ke liye minimum delay 10s hai.\n\n"
                f"👉 VIP upgrade karein:",
                parse_mode="HTML",
                reply_markup=prem_kb
            )
            return
        await db.update_user_setting(user_id, "message_delay", seconds)
        await state.clear()
        await message.answer(f"{EMOJI_VERIFIED} <b>Delay updated to {seconds}s!</b>", parse_mode="HTML")
        await show_dashboard(bot, message.chat.id, user_id)
    except ValueError:
        await message.answer(f"{EMOJI_CROSS} Please enter a valid number of seconds.", reply_markup=kb.get_back_keyboard())

# --- TOGGLE TARGET ---
@router.callback_query(F.data == "toggle_target")
async def btn_toggle_target(call: CallbackQuery, bot: Bot):
    user_id = call.from_user.id
    settings = await db.get_user_settings(user_id)
    current_target = settings.get("target_type", "Groups")
    
    # Toggle cycle: Groups -> Channels -> All -> Groups
    next_target = {"Groups": "Channels", "Channels": "All", "All": "Groups"}.get(current_target, "Groups")
    await call.answer(f"Target: {next_target}")
    await db.update_user_setting(user_id, "target_type", next_target)
    await show_dashboard(bot, call.message.chat.id, user_id, message_to_edit=call.message)

# --- SET CYCLES ---
@router.callback_query(F.data == "set_cycles")
async def btn_set_cycles(call: CallbackQuery):
    await call.answer()
    text = (
        f"╔══════════════════════════╗\n"
        f"  {EMOJI_MOON} <b>AD CAMPAIGN CYCLES</b>\n"
        f"╚══════════════════════════╝\n"
        f"Puri group list me ads kitni bar broadcast karni hai select karein:\n\n"
        f"• <b>5, 10, 15, 20:</b> Fixed cycle options\n"
        f"• 👑 <b>Unlimited (∞):</b> 24/7 continuous advertising (VIP only)\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"👉 Select cycle mode below:"
    )
    await call.message.edit_text(text, parse_mode="HTML", reply_markup=kb.get_cycles_keyboard())

@router.callback_query(F.data.startswith("cycles_"))
async def process_cycles_choice(call: CallbackQuery, bot: Bot, state: FSMContext):
    val = call.data.replace("cycles_", "")
    user_id = call.from_user.id
    user_info = await db.get_user_info(user_id)
    is_vip = bool(user_info and user_info.get("is_premium", 0)) or (user_id in ADMIN_IDS)
    
    if val == "custom":
        await call.answer()
        await state.set_state(UserStates.waiting_custom_cycles)
        await call.message.edit_text(
            f"╔══════════════════════════╗\n"
            f"  {EMOJI_SPARKLE} <b>CUSTOM CYCLES</b>\n"
            f"╚══════════════════════════╝\n"
            f"Total cycles ka number enter karein:\n"
            f"<i>(Example: <code>15</code> ya <code>20</code>)</i>\n\n"
            f"👑 <i>Note: Unlimited (∞) cycles sirf VIP members ke liye hai.</i>",
            parse_mode="HTML",
            reply_markup=kb.get_back_keyboard()
        )
        return
        
    num = int(val)
    if not is_vip and num == 0:
        await call.answer("👑 Unlimited (∞) Cycles sirf VIP members ke liye hai!", show_alert=True)
        await btn_premium(call)
        return

    await db.update_user_setting(user_id, "max_cycles", num)
    cycle_str = "Unlimited (∞)" if num == 0 else str(num)
    await call.answer(f"Cycles set to {cycle_str}!")
    await show_dashboard(bot, call.message.chat.id, user_id, message_to_edit=call.message)

@router.message(UserStates.waiting_custom_cycles)
async def process_custom_cycles(message: Message, bot: Bot, state: FSMContext):
    user_id = message.from_user.id
    user_info = await db.get_user_info(user_id)
    is_vip = bool(user_info and user_info.get("is_premium", 0)) or (user_id in ADMIN_IDS)
    try:
        num = int(message.text.strip())
        if num < 0:
            raise ValueError
        if not is_vip and num == 0:
            prem_kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="💎 Upgrade to VIP (₹100)", callback_data="premium")],
                [InlineKeyboardButton(text="🔙 Back to Dashboard", callback_data="back_to_dashboard")]
            ])
            await message.answer(
                f"⚠️ <b>VIP Access Required</b>\n\n"
                f"Unlimited (∞) cycles sirf <b>VIP Members</b> ke liye available hain.\n\n"
                f"👉 VIP upgrade karein ya 1 se 20 cycles set karein:",
                parse_mode="HTML",
                reply_markup=prem_kb
            )
            return
        await db.update_user_setting(user_id, "max_cycles", num)
        cycle_str = "Unlimited (∞)" if num == 0 else str(num)
        await state.clear()
        await message.answer(f"{EMOJI_VERIFIED} <b>Cycles set to {cycle_str}!</b>", parse_mode="HTML")
        await show_dashboard(bot, message.chat.id, user_id)
    except ValueError:
        await message.answer(f"{EMOJI_CROSS} Please enter a valid number (0 or positive integer).", reply_markup=kb.get_back_keyboard())

# --- AI ASSISTANT ATO REPLY & DEAL ---
@router.callback_query(F.data == "ai_assistant_autoreply")
async def btn_ai_assistant_autoreply(call: CallbackQuery):
    await call.answer()
    text = (
        f"╔══════════════════════════╗\n"
        f"  🤖 <b>AI ATO REPLY & DEAL</b> ⚡\n"
        f"╚══════════════════════════╝\n"
        f"Koi bhi user ads wali I'd me msg karega usko atomic reply dega User ke set ada wala msg ke hisab se.\n\n"
        f"👑 <b>User ko ai assistant deal karega!</b>\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"💡 <i>AI Deal & Auto-Reply unlock karne ke liye Premium join karein:</i>"
    )
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💎 Buy Premium (₹100)", callback_data="premium")],
        [InlineKeyboardButton(text="🔙 Back to Dashboard", callback_data="back_to_dashboard")]
    ])
    await call.message.edit_text(text, parse_mode="HTML", reply_markup=markup)

# --- EXCLUDE GROUPS ---
@router.callback_query(F.data == "exclude_groups")
async def btn_exclude_groups(call: CallbackQuery, state: FSMContext):
    await call.answer()
    user_id = call.from_user.id
    settings = await db.get_user_settings(user_id)
    excluded = settings.get("exclude_groups") or "None"
    
    text = (
        f"╔══════════════════════════╗\n"
        f"  {EMOJI_GIFT} <b>EXCLUDE SPECIFIC CHATS</b>\n"
        f"╚══════════════════════════╝\n"
        f"🚫 <b>Currently Blacklisted:</b>\n"
        f"<blockquote>{excluded}</blockquote>\n\n"
        f"Jin chats me ads post nahi karni, unke usernames ya IDs comma se separate karke send karein:\n"
        f"<i>(Example: @spamchat, @alerts, -100123456789)</i>"
    )
    await state.set_state(UserStates.waiting_exclude_groups)
    await call.message.edit_text(text, parse_mode="HTML", reply_markup=kb.get_back_keyboard())

@router.message(UserStates.waiting_exclude_groups)
async def process_exclude_groups(message: Message, bot: Bot, state: FSMContext):
    user_id = message.from_user.id
    ex_text = message.text.strip()
    await db.update_user_setting(user_id, "exclude_groups", ex_text)
    await state.clear()
    await message.answer(f"{EMOJI_VERIFIED} <b>Excluded chats blacklist updated!</b>", parse_mode="HTML")
    await show_dashboard(bot, message.chat.id, user_id)

# --- PREVIEW AD ---
@router.callback_query(F.data == "preview_ad")
async def btn_preview_ad(call: CallbackQuery, bot: Bot):
    user_id = call.from_user.id
    settings = await db.get_user_settings(user_id)
    ad_text = settings.get("ad_message") or ""
    media_id = settings.get("ad_media_id")
    media_type = settings.get("ad_media_type")

    if not ad_text and not media_id:
        await call.answer("Aapne abhi tak koi ad set nahi kiya hai! Pehle 'Set Ad Message' karein.", show_alert=True)
        return

    await call.answer()
    back_kb = kb.get_back_keyboard()
    header = (
        f"╔══════════════════════════╗\n"
        f"  {EMOJI_SPARKLE} <b>LIVE ADVERT PREVIEW</b> ✨\n"
        f"╚══════════════════════════╝\n"
    )
    footer = (
        f"\n━━━━━━━━━━━━━━━━━━━━━\n"
        f"📌 <i>Yeh advert aapke sabhi connected accounts se target chats me bheja jayega.</i>"
    )

    if media_id:
        caption = f"{header}{ad_text}{footer}" if ad_text else f"{header}<i>(No caption)</i>{footer}"
        file_to_send = FSInputFile(media_id) if (isinstance(media_id, str) and os.path.exists(media_id)) else media_id
        try:
            if media_type == "photo":
                await bot.send_photo(call.message.chat.id, photo=file_to_send, caption=caption, parse_mode="HTML", reply_markup=back_kb)
            elif media_type == "video":
                await bot.send_video(call.message.chat.id, video=file_to_send, caption=caption, parse_mode="HTML", reply_markup=back_kb)
            elif media_type == "animation":
                await bot.send_animation(call.message.chat.id, animation=file_to_send, caption=caption, parse_mode="HTML", reply_markup=back_kb)
            elif media_type == "document":
                await bot.send_document(call.message.chat.id, document=file_to_send, caption=caption, parse_mode="HTML", reply_markup=back_kb)
            else:
                await bot.send_message(call.message.chat.id, f"{header}{ad_text}{footer}", parse_mode="HTML", reply_markup=back_kb)
            
            try:
                await call.message.delete()
            except Exception:
                pass
            return
        except Exception as e:
            await call.message.edit_text(f"{header}{ad_text}\n\n{EMOJI_WARNING} <i>(Media preview error: {e})</i>{footer}", parse_mode="HTML", reply_markup=back_kb)
            return

    # Text only ad
    preview_content = f"{header}<blockquote>{ad_text}</blockquote>{footer}"
    await call.message.edit_text(preview_content, parse_mode="HTML", reply_markup=back_kb)

# --- ANALYTICS ---
@router.callback_query(F.data == "analytics")
async def btn_analytics(call: CallbackQuery):
    await call.answer()
    user_id = call.from_user.id
    data, accounts = await asyncio.gather(
        db.get_analytics(user_id),
        db.get_user_accounts_all(user_id)
    )

    total_sent = data.get('total_sent', 0)
    total_failed = data.get('total_failed', 0)
    success_rate = "100"
    if (total_sent + total_failed) > 0:
        success_rate = f"{(total_sent / (total_sent + total_failed) * 100):.1f}"

    text = (
        f"╔══════════════════════════╗\n"
        f"  {EMOJI_STATS} <b>CAMPAIGN ANALYTICS</b> {EMOJI_FIRE}\n"
        f"╚══════════════════════════╝\n"
        f"📈 <b>Lifetime Ads Dispatched:</b> <code>{total_sent:,}</code>\n"
        f"⚠️ <b>Failed / Skipped:</b> <code>{total_failed:,}</code>\n"
        f"🎯 <b>Delivery Success Rate:</b> <code>{success_rate}%</code>\n"
        f"🕒 <b>Last Active:</b> <code>{data.get('last_sent_at', 'Never')}</code>\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"{EMOJI_PHONE} <b>HOSTED ACCOUNTS BREAKDOWN ({len(accounts)})</b>\n"
    )

    if accounts:
        for idx, acc in enumerate(accounts, 1):
            ban_tag = f" [{EMOJI_CROSS} BANNED]" if acc.get("is_banned") else f" [{EMOJI_VERIFIED} ACTIVE]"
            text += (
                f"{idx}. <b>{acc.get('account_name', 'Telegram')}</b> {ban_tag}\n"
                f"   └ 🚀 Sent: <code>{acc.get('total_sent', 0)}</code> | ⚠️ Failed: <code>{acc.get('total_failed', 0)}</code>\n"
            )
    else:
        text += f"<i>Koi account connected nahi hai.</i>\n"

    text += (
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"{EMOJI_SPARKLE} <i>All metrics updated in real-time via Supabase PostgreSQL.</i>"
    )
    await call.message.edit_text(text, parse_mode="HTML", reply_markup=kb.get_back_keyboard())

# --- SCHEDULE ADS ---
@router.callback_query(F.data == "schedule_ads")
async def btn_schedule_ads(call: CallbackQuery):
    await call.answer()
    user_id = call.from_user.id
    settings = await db.get_user_settings(user_id)

    sched_enabled = settings.get("schedule_enabled", 0)
    sched_start = settings.get("schedule_start") or "Not Set"
    sched_end = settings.get("schedule_end") or "Not Set"
    status_str = f"{EMOJI_RUNNING} <b>ENABLED</b>" if sched_enabled else f"{EMOJI_PAUSED} <b>DISABLED</b>"

    text = (
        f"╔══════════════════════════╗\n"
        f"  {EMOJI_CLOCK} <b>SCHEDULED BROADCASTS</b>\n"
        f"╚══════════════════════════╝\n"
        f"• <b>Status:</b> {status_str}\n"
        f"• <b>Active Window:</b> <code>{sched_start}</code> ➔ <code>{sched_end}</code>\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"💡 <b>Automated Scheduler:</b>\n"
        f"Schedule enable karne par ads sirf is specified time window me hi run hongi.\n"
        f"<i>(Overnight bhi fully supported hai, e.g. 22:00 to 07:00)</i>"
    )
    markup = kb.get_schedule_keyboard(sched_enabled)
    await call.message.edit_text(text, parse_mode="HTML", reply_markup=markup)

@router.callback_query(F.data == "schedule_toggle")
async def schedule_toggle(call: CallbackQuery, bot: Bot):
    user_id = call.from_user.id
    settings = await db.get_user_settings(user_id)
    current = settings.get("schedule_enabled", 0)
    new_val = 0 if current else 1
    await db.update_user_setting(user_id, "schedule_enabled", new_val)
    status = "Enabled" if new_val else "Disabled"
    await call.answer(f"Schedule {status}!")
    await btn_schedule_ads(call)

@router.callback_query(F.data == "schedule_set_start")
async def schedule_set_start(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await state.set_state(UserStates.waiting_schedule_start)
    await call.message.edit_text(
        f"╔══════════════════════════╗\n"
        f"  {EMOJI_CLOCK} <b>SET SCHEDULE START TIME</b>\n"
        f"╚══════════════════════════╝\n"
        f"Ads kab se broadcast hona shuru hon? Time enter karein:\n\n"
        f"<i>(24-hour format, e.g. <code>09:00</code> ya <code>22:30</code>)</i>",
        parse_mode="HTML",
        reply_markup=kb.get_back_keyboard()
    )

@router.message(UserStates.waiting_schedule_start)
async def process_schedule_start(message: Message, state: FSMContext):
    user_id = message.from_user.id
    time_str = message.text.strip()
    try:
        parts = time_str.split(":")
        assert len(parts) == 2
        h, m = int(parts[0]), int(parts[1])
        assert 0 <= h <= 23 and 0 <= m <= 59
        clean_time = f"{h:02d}:{m:02d}"
    except Exception:
        await message.answer(
            f"{EMOJI_CROSS} Invalid format! <code>HH:MM</code> format me enter karein (e.g. <code>09:00</code>)",
            parse_mode="HTML"
        )
        return

    await db.update_user_setting(user_id, "schedule_start", clean_time)
    await state.clear()
    await message.answer(f"{EMOJI_VERIFIED} <b>Start Time updated to {clean_time}</b>", parse_mode="HTML")
    await show_dashboard(bot=message.bot, chat_id=message.chat.id, user_id=user_id)

@router.callback_query(F.data == "schedule_set_end")
async def schedule_set_end(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await state.set_state(UserStates.waiting_schedule_end)
    await call.message.edit_text(
        f"╔══════════════════════════╗\n"
        f"  {EMOJI_CLOCK} <b>SET SCHEDULE END TIME</b>\n"
        f"╚══════════════════════════╝\n"
        f"Ads kab pause/stop hon? Time enter karein:\n\n"
        f"<i>(24-hour format, e.g. <code>22:00</code> ya <code>06:00</code>)</i>",
        parse_mode="HTML",
        reply_markup=kb.get_back_keyboard()
    )

@router.message(UserStates.waiting_schedule_end)
async def process_schedule_end(message: Message, state: FSMContext):
    user_id = message.from_user.id
    time_str = message.text.strip()
    try:
        parts = time_str.split(":")
        assert len(parts) == 2
        h, m = int(parts[0]), int(parts[1])
        assert 0 <= h <= 23 and 0 <= m <= 59
        clean_time = f"{h:02d}:{m:02d}"
    except Exception:
        await message.answer(
            f"{EMOJI_CROSS} Invalid format! <code>HH:MM</code> format me enter karein (e.g. <code>22:00</code>)",
            parse_mode="HTML"
        )
        return

    await db.update_user_setting(user_id, "schedule_end", clean_time)
    await state.clear()
    await message.answer(f"{EMOJI_VERIFIED} <b>End Time updated to {clean_time}</b>", parse_mode="HTML")
    await show_dashboard(bot=message.bot, chat_id=message.chat.id, user_id=user_id)

# --- PREMIUM ---
@router.callback_query(F.data == "premium")
async def btn_premium(call: CallbackQuery):
    await call.answer()
    text = (
        f"""╔══════════════════════════╗
  💎 <b>ATOMIC VIP MEMBERSHIP</b> 🚀
╚══════════════════════════╝
Automate your Telegram marketing at maximum scale with VIP power:

📱 <b>Host 50+ Accounts Without Limit</b>
   └ <i>Host 10, 50, ya 100+ accounts bina kisi restriction ke</i>

⏱️ <b>Minimum Cycle Interval: 1 Minute</b>
   └ <i>Non-stop automated campaign rotation every 60 seconds</i>

⚡ <b>Minimum Message Delay: 1 Second</b>
   └ <i>Ultra-fast turbocharged dispatch speed across target chats</i>

🌐 <b>Auto-Join Public & Private Groups</b>
   └ <i>Accounts se automatically unlimited channels/groups join karein</i>

🛡️ <b>No Bio Link & Zero Ad Promotion</b>
   └ <i>Aapke accounts 100% clean rahenge, name/bio me koi bot promo nahi aayega</i>

👑 <b>Dedicated 24/7 Customer Support</b>
   └ <i>Priority instant help & setup assistance 24/7 available</i>

━━━━━━━━━━━━━━━━━━━━━
💸 <b>VIP PRICING & REWARDS:</b>
• 🎁 <b>Referral Rewards:</b> <code>1 Referral = 2 Days VIP Access FREE</code>
• 💎 <b>Lifetime VIP Access:</b> <code>₹100 / $1.20</code>
━━━━━━━━━━━━━━━━━━━━━
👑 <b>Owner:</b> <a href='https://t.me/Tanweer07'>@Tanweer07</a>
🛠️ <b>Support:</b> <a href='https://t.me/TANWEER_SUPPORT'>@TANWEER_SUPPORT</a>

💬 <b>Instant VIP Activation Ke Liye Contact Karein:</b>
👉 <a href='https://t.me/Tanweer07'>@Tanweer07</a>"""
    )
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👑 Owner", url="https://t.me/Tanweer07")],
        [InlineKeyboardButton(text="💬 Support", url="https://t.me/TANWEER_SUPPORT")],
        [InlineKeyboardButton(text="🎁 Refer Friends (Free VIP)", callback_data="refer_earn")],
        [InlineKeyboardButton(text="🔙 Back to Dashboard", callback_data="back_to_dashboard")]
    ])
    if call.message.photo:
        await call.message.delete()
        await call.message.answer(text, parse_mode="HTML", reply_markup=markup)
    else:
        await call.message.edit_text(text, parse_mode="HTML", reply_markup=markup)

# --- REFER & EARN SYSTEM ---
@router.callback_query(F.data == "refer_earn")
async def btn_refer_earn(call: CallbackQuery, bot: Bot):
    await call.answer()
    user_id = call.from_user.id
    bot_user = await get_bot_username(bot)

    stats = await db.get_user_referral_stats(user_id)
    ref_count = stats.get("referral_count", 0)
    is_premium = stats.get("is_premium", 0)
    vip_days_earned = ref_count * 2
    ref_link = f"https://t.me/{bot_user}?start=ref_{user_id}"

    status_line = f"🎉 <b>VIP Status:</b> <code>🟢 ACTIVE</code>" if is_premium else f"⚪ <b>VIP Status:</b> <code>Standard Free</code>"

    text = (
        f"╔══════════════════════════╗\n"
        f"  🎁 <b>REFER & EARN FREE VIP</b> {EMOJI_ROCKET}\n"
        f"╚══════════════════════════╝\n"
        f"Apne dosto ko bot refer karein aur <b>1 Referral = 2 Days VIP Access bilkul FREE</b> payein!\n\n"
        f"┌ 👥 <b>Your Successful Referrals:</b> <code>{ref_count}</code>\n"
        f"├ 🎁 <b>VIP Days Earned:</b> <code>+{vip_days_earned} Days</code>\n"
        f"└ {status_line}\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"🔗 <b>Your Exclusive Referral Link:</b>\n"
        f"<code>{ref_link}</code>\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"💡 <i>Upar diye gaye link ko copy karke dosto ya groups me share karein. Har 1 naye user ke bot start karne par aapko turant +2 Days VIP Access automatically milta jayega!</i>\n\n"
        f"👑 <b>Owner:</b> <a href='https://t.me/Tanweer07'>@Tanweer07</a> | <b>Support:</b> <a href='https://t.me/TANWEER_SUPPORT'>@TANWEER_SUPPORT</a>"
    )

    share_text = "Turn your Alt account into an automated Telegram AdsBot with free trial and bulk power!"
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔗 Share Link with Friends", url=f"https://t.me/share/url?url={ref_link}&text={share_text}")],
        [InlineKeyboardButton(text="🔙 Back to Dashboard", callback_data="back_to_dashboard")]
    ])

    if call.message.photo:
        await call.message.delete()
        await call.message.answer(text, parse_mode="HTML", reply_markup=markup)
    else:
        await call.message.edit_text(text, parse_mode="HTML", reply_markup=markup)


# ─────────────────────────────────────────────
# CUSTOMER FORWARD ACCOUNT CONFIGURATION
# ─────────────────────────────────────────────
@router.callback_query(F.data == "set_forward_account")
async def btn_set_forward_account(call: CallbackQuery):
    await call.answer()
    user_id = call.from_user.id
    current_fwd = await db.get_user_forward_account(user_id)
    fwd_display = f"@{current_fwd}" if current_fwd else "<i>Not Set (Bot Chat Only)</i>"

    text = (
        f"╔══════════════════════════╗\n"
        f"  📲 <b>LEAD DM FORWARDING ACCOUNT</b>\n"
        f"╚══════════════════════════╝\n"
        f"Jab aapke alt accounts par ads chalengi aur koi lead DM karegi:\n"
        f"• Bot aapko automatically yahan notification aur reply link dega.\n"
        f"• Agar aap chahte hain ki DMs direct aapke personal Telegram account par forward hon, toh niche apna Main Account username enter karein.\n\n"
        f"┌ 📲 <b>Current Forward Account:</b> <code>{fwd_display}</code>\n"
        f"└ ⚙️ <b>Status:</b> {'🟢 Active' if current_fwd else '⚪ Inactive (Bot Only)'}\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"Niche button se naya account username set ya clear karein:"
    )
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📲 Set / Change Main Account", callback_data="user_set_fwd_acc")],
        [InlineKeyboardButton(text="🗑️ Remove / Clear Main Account", callback_data="user_clear_fwd_acc")],
        [InlineKeyboardButton(text="🔙 Back to Dashboard", callback_data="back_to_dashboard")]
    ])

    if call.message.photo:
        await call.message.delete()
        await call.message.answer(text, parse_mode="HTML", reply_markup=markup)
    else:
        await call.message.edit_text(text, parse_mode="HTML", reply_markup=markup)

@router.callback_query(F.data == "user_clear_fwd_acc")
async def user_clear_forward_account(call: CallbackQuery):
    await db.set_user_forward_account(call.from_user.id, "")
    await call.answer("Forward account removed! DMs will be delivered in bot.", show_alert=True)
    await btn_set_forward_account(call)

@router.callback_query(F.data == "user_set_fwd_acc")
async def user_set_forward_account_prompt(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await state.set_state(UserStates.waiting_forward_account)
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Cancel", callback_data="set_forward_account")]
    ])
    text = (
        f"╔══════════════════════════╗\n"
        f"  📲 <b>ENTER YOUR MAIN TELEGRAM HANDLE</b>\n"
        f"╚══════════════════════════╝\n"
        f"Apne main personal account ka username enter karein:\n\n"
        f"<i>(Example: <code>@my_main_account</code> ya numeric Chat ID)</i>"
    )
    if call.message.photo:
        await call.message.delete()
        await call.message.answer(text, parse_mode="HTML", reply_markup=markup)
    else:
        await call.message.edit_text(text, parse_mode="HTML", reply_markup=markup)

@router.message(UserStates.waiting_forward_account)
async def process_set_forward_account(message: Message, state: FSMContext):
    clean = message.text.strip().replace("@", "")
    if not clean:
        await message.answer(f"{EMOJI_CROSS} Invalid username.")
        return
    await db.set_user_forward_account(message.from_user.id, clean)
    await state.clear()
    await message.answer(
        f"╔══════════════════════════╗\n"
        f"  {EMOJI_VERIFIED} <b>MAIN ACCOUNT SAVED!</b>\n"
        f"╚══════════════════════════╝\n"
        f"Ab aapke alt accounts par aane wale lead DMs <b>@{clean}</b> ko bhi forward honge!",
        parse_mode="HTML",
        reply_markup=kb.get_back_keyboard()
    )


# ─────────────────────────────────────────────
# TWO-WAY LEAD REPLY HANDLER (REPLY VIA ALT ACCOUNT)
# ─────────────────────────────────────────────
@router.message(F.reply_to_message)
async def handle_customer_lead_reply(message: Message, bot: Bot):
    if not message.reply_to_message:
        return

    reply_msg_id = message.reply_to_message.message_id
    user_id = message.from_user.id
    reply_text = message.text or message.caption or ""

    from dm_relay import send_reply_from_alt
    success, reply_info = await send_reply_from_alt(
        user_id=user_id,
        bot_message_id=reply_msg_id,
        reply_text=reply_text,
        bot=bot
    )

    if success:
        await message.reply(
            f"╔══════════════════════════╗\n"
            f"  {EMOJI_VERIFIED} <b>REPLY DELIVERED TO LEAD!</b>\n"
            f"╚══════════════════════════╝\n"
            f"{reply_info}\n\n"
            f"💬 <b>Your Reply:</b>\n"
            f"<blockquote>{reply_text}</blockquote>",
            parse_mode="HTML"
        )

