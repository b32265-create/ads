import os
import io
import logging
import asyncio
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, PhotoSize, Video, Document, FSInputFile, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

import database as db
import keyboards as kb
from banner_generator import generate_user_welcome_banner
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
    first_name = user_info.get("first_name", "User")
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

    return (
        f"╔══════════════════════════╗\n"
        f"  {EMOJI_FIRE} <b>SHADOW ADS AUTOMATION</b> 🐲\n"
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
        f"└ {status_display}\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"💡 <i>Niche diye gaye control panel se action select karein:</i>"
    )

_CACHED_BOT_USERNAME: str = ""

async def get_bot_username(bot: Bot) -> str:
    global _CACHED_BOT_USERNAME
    if not _CACHED_BOT_USERNAME:
        bot_info = await bot.get_me()
        _CACHED_BOT_USERNAME = bot_info.username or "ALL_SHADOWS_BOT"
    return _CACHED_BOT_USERNAME

async def show_dashboard(bot: Bot, chat_id: int, user_id: int, message_to_edit: Message = None):
    """Utility to render and send/edit the exact dashboard with premium styling."""
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
        schedule_enabled=settings.get("schedule_enabled", 0)
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
    await state.clear()
    user_id = message.from_user.id
    username = message.from_user.username
    first_name = message.from_user.first_name

    # Check for referral payload: e.g. /start ref_12345678 or /start 12345678
    args = message.text.split()[1] if len(message.text.split()) > 1 else ""
    if args:
        ref_raw = args.replace("ref_", "").strip()
        if ref_raw.isdigit():
            referrer_id = int(ref_raw)
            try:
                is_counted, new_count, unlocked_reward = await db.record_user_referral(user_id, referrer_id)
                if is_counted:
                    reward_msg = (
                        f"\n\n👑 <b>CONGRATULATIONS!</b> Aapke 5 referrals pure ho gaye!\n"
                        f"<b>1-Month VIP Premium Access</b> automatically aapke account par FREE activate ho gaya hai! 🚀"
                        if unlocked_reward else
                        f"\n💡 <i>Sirf {max(0, 5 - new_count)} aur referral chahiye 1-Month Free VIP ke liye!</i>"
                    )
                    try:
                        await bot.send_message(
                            referrer_id,
                            f"╔══════════════════════════╗\n"
                            f"  🎉 <b>NEW REFERRAL JOINED!</b>\n"
                            f"╚══════════════════════════╝\n"
                            f"Aapke referral link se naya user jud gaya hai:\n"
                            f"• 👤 <b>User:</b> <code>{message.from_user.full_name}</code>\n"
                            f"• 👥 <b>Total Referrals:</b> <code>{new_count}/5</code>"
                            + reward_msg,
                            parse_mode="HTML"
                        )
                    except Exception:
                        pass
            except Exception as e:
                logger.warning(f"Error handling referral: {e}")

    # Register user in DB
    await db.get_or_create_user(user_id, username, first_name)

    # Parallel check for ban status, force join, and log account
    user_info, (is_joined, unjoined), log_account = await asyncio.gather(
        db.get_user_info(user_id),
        check_user_force_join(bot, user_id),
        db.get_log_account()
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

    # Download user avatar for custom banner compositing
    avatar_bytes = None
    try:
        photos = await bot.get_user_profile_photos(user_id, limit=1)
        if photos.total_count > 0:
            file_id = photos.photos[0][-1].file_id
            tg_file = await bot.get_file(file_id)
            avatar_bio = io.BytesIO()
            await bot.download_file(tg_file.file_path, avatar_bio)
            avatar_bytes = avatar_bio.getvalue()
    except Exception:
        pass

    # Generate personalized dynamic banner
    banner_path = generate_user_welcome_banner(
        user_id=user_id,
        username=username or "",
        first_name=first_name or "",
        avatar_bytes=avatar_bytes
    )

    log_section = ""
    if log_account:
        log_section = (
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"📡 <b>LIVE AD DELIVERY LOGS ACCOUNT:</b>\n"
            f"👉 <a href='https://t.me/{log_account}'>@{log_account}</a>\n"
            f"<i>(Is account par message karein taki campaign ke live delivery logs aapko aane lagein)</i>\n"
        )

    welcome_text = (
        f"This bot helps you to turn your <b>Alt Account</b> into an automated <b>AdsBot</b> so you can run your Auto Advertisements across Telegram.\n\n"
        f"Only AdsBot with free trial on telegram.\n"
        f"Which provide almost all premium features in free kisi bhi tarike ka bot self promotion banner nhi lagega, nah hi naam ke piche via @xyz lagega nah hi bio me koi link aayega.\n"
        f"Work as normal account with bulk power.\n\n"
        f"Start the bot to begin your impactful advertisement journey with SHADOWS.\n"
        f"{log_section}"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"Powered by: <a href='https://t.me/SHADOW_SELLER07'>@SHADOW_SELLER07</a>"
    )

    start_keyboard = [
        [InlineKeyboardButton(text="Open Control Dashboard", callback_data="back_to_dashboard", icon_custom_emoji_id=ID_FIRE)],
        [InlineKeyboardButton(text="Refer & Earn (Free VIP)", callback_data="refer_earn", icon_custom_emoji_id=ID_GIFT)],
    ]
    if log_account:
        start_keyboard.append([
            InlineKeyboardButton(text=f"Live Logs: @{log_account}", url=f"https://t.me/{log_account}", icon_custom_emoji_id=ID_STAR)
        ])
    start_keyboard.append([
        InlineKeyboardButton(text="Lifetime VIP Pass (₹100)", callback_data="premium", icon_custom_emoji_id=ID_DIAMOND)
    ])

    markup = InlineKeyboardMarkup(inline_keyboard=start_keyboard)

    if banner_path and os.path.exists(banner_path):
        try:
            await message.answer_photo(
                photo=FSInputFile(banner_path),
                caption=welcome_text,
                parse_mode="HTML",
                reply_markup=markup
            )
            return
        except Exception as e:
            logger.error(f"Error sending welcome banner: {e}")

    await message.answer(welcome_text, parse_mode="HTML", reply_markup=markup)

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
    if call.message.photo or call.message.video or call.message.animation or call.message.document:
        try:
            await call.message.delete()
        except Exception:
            pass
        await show_dashboard(bot, call.message.chat.id, call.from_user.id)
    else:
        await show_dashboard(bot, call.message.chat.id, call.from_user.id, message_to_edit=call.message)

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

    if message.photo:
        media_id = str(message.photo[-1].file_id)  # Largest photo
        media_type = "photo"
    elif message.video:
        media_id = str(message.video.file_id)
        media_type = "video"
    elif message.document:
        media_id = str(message.document.file_id)
        media_type = "document"
    elif message.animation:
        media_id = str(message.animation.file_id)
        media_type = "animation"

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
        f"💡 <i>Recommended: 5 ya 10 Minutes (FloodWait se bachne ke liye).</i>\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"👉 Niche pre-set ya custom intervals chunein:"
    )
    await call.message.edit_text(text, parse_mode="HTML", reply_markup=kb.get_interval_keyboard())

@router.callback_query(F.data.startswith("interval_"))
async def process_interval_choice(call: CallbackQuery, bot: Bot, state: FSMContext):
    val = call.data.replace("interval_", "")
    user_id = call.from_user.id
    
    if val == "custom":
        await call.answer()
        await state.set_state(UserStates.waiting_custom_interval)
        await call.message.edit_text(
            f"╔══════════════════════════╗\n"
            f"  {EMOJI_SPARKLE} <b>CUSTOM INTERVAL</b>\n"
            f"╚══════════════════════════╝\n"
            f"Seconds me custom time enter karein:\n\n"
            f"• <code>300</code> = 5 Minutes\n"
            f"• <code>900</code> = 15 Minutes\n"
            f"• <code>1800</code> = 30 Minutes\n\n"
            f"👉 <i>Number send karein (Minimum 30s):</i>",
            parse_mode="HTML",
            reply_markup=kb.get_back_keyboard()
        )
        return
        
    seconds = int(val)
    await db.update_user_setting(user_id, "cycle_interval", seconds)
    await call.answer(f"Interval set to {format_interval(seconds)}!")
    await show_dashboard(bot, call.message.chat.id, user_id, message_to_edit=call.message)

@router.message(UserStates.waiting_custom_interval)
async def process_custom_interval(message: Message, bot: Bot, state: FSMContext):
    user_id = message.from_user.id
    try:
        seconds = int(message.text.strip())
        if seconds < 30:
            await message.answer(f"{EMOJI_WARNING} Minimum interval 30 seconds hona chahiye.", reply_markup=kb.get_back_keyboard())
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
        f"• <b>2s:</b> ⚡ Fast (Established Accounts)\n"
        f"• <b>5s:</b> 🥂 Optimal (Recommended standard)\n"
        f"• <b>15s:</b> 🛡️ Extra Safe (Fresh/New accounts)\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"👉 Niche delay select karein:"
    )
    await call.message.edit_text(text, parse_mode="HTML", reply_markup=kb.get_delay_keyboard())

@router.callback_query(F.data.startswith("delay_"))
async def process_delay_choice(call: CallbackQuery, bot: Bot, state: FSMContext):
    val = call.data.replace("delay_", "")
    user_id = call.from_user.id
    
    if val == "custom":
        await call.answer()
        await state.set_state(UserStates.waiting_custom_delay)
        await call.message.edit_text(
            f"╔══════════════════════════╗\n"
            f"  {EMOJI_SPARKLE} <b>CUSTOM DELAY</b>\n"
            f"╚══════════════════════════╝\n"
            f"Messages ke beech seconds me gap enter karein:\n"
            f"<i>(Example: <code>7</code> ya <code>12</code>)</i>",
            parse_mode="HTML",
            reply_markup=kb.get_back_keyboard()
        )
        return
        
    seconds = int(val)
    await db.update_user_setting(user_id, "message_delay", seconds)
    await call.answer(f"Delay set to {seconds}s!")
    await show_dashboard(bot, call.message.chat.id, user_id, message_to_edit=call.message)

@router.message(UserStates.waiting_custom_delay)
async def process_custom_delay(message: Message, bot: Bot, state: FSMContext):
    user_id = message.from_user.id
    try:
        seconds = int(message.text.strip())
        if seconds < 1:
            await message.answer(f"{EMOJI_WARNING} Minimum delay 1 second hona chahiye.", reply_markup=kb.get_back_keyboard())
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
        f"• <b>Unlimited (∞):</b> 24/7 continuous advertising\n"
        f"• <b>Fixed Cycles:</b> Targeted amount complete hote hi auto-pause\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"👉 Select cycle mode below:"
    )
    await call.message.edit_text(text, parse_mode="HTML", reply_markup=kb.get_cycles_keyboard())

@router.callback_query(F.data.startswith("cycles_"))
async def process_cycles_choice(call: CallbackQuery, bot: Bot, state: FSMContext):
    val = call.data.replace("cycles_", "")
    user_id = call.from_user.id
    
    if val == "custom":
        await call.answer()
        await state.set_state(UserStates.waiting_custom_cycles)
        await call.message.edit_text(
            f"╔══════════════════════════╗\n"
            f"  {EMOJI_SPARKLE} <b>CUSTOM CYCLES</b>\n"
            f"╚══════════════════════════╝\n"
            f"Total cycles ka number enter karein:\n"
            f"<i>(Example: <code>25</code> ya <code>0</code> for Unlimited)</i>",
            parse_mode="HTML",
            reply_markup=kb.get_back_keyboard()
        )
        return
        
    num = int(val)
    await db.update_user_setting(user_id, "max_cycles", num)
    cycle_str = "Unlimited (∞)" if num == 0 else str(num)
    await call.answer(f"Cycles set to {cycle_str}!")
    await show_dashboard(bot, call.message.chat.id, user_id, message_to_edit=call.message)

@router.message(UserStates.waiting_custom_cycles)
async def process_custom_cycles(message: Message, bot: Bot, state: FSMContext):
    user_id = message.from_user.id
    try:
        num = int(message.text.strip())
        if num < 0:
            raise ValueError
        await db.update_user_setting(user_id, "max_cycles", num)
        cycle_str = "Unlimited (∞)" if num == 0 else str(num)
        await state.clear()
        await message.answer(f"{EMOJI_VERIFIED} <b>Cycles set to {cycle_str}!</b>", parse_mode="HTML")
        await show_dashboard(bot, message.chat.id, user_id)
    except ValueError:
        await message.answer(f"{EMOJI_CROSS} Please enter a valid number (0 or positive integer).", reply_markup=kb.get_back_keyboard())

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
        try:
            if media_type == "photo":
                await bot.send_photo(call.message.chat.id, photo=media_id, caption=caption, parse_mode="HTML", reply_markup=back_kb)
            elif media_type == "video":
                await bot.send_video(call.message.chat.id, video=media_id, caption=caption, parse_mode="HTML", reply_markup=back_kb)
            elif media_type == "animation":
                await bot.send_animation(call.message.chat.id, animation=media_id, caption=caption, parse_mode="HTML", reply_markup=back_kb)
            elif media_type == "document":
                await bot.send_document(call.message.chat.id, document=media_id, caption=caption, parse_mode="HTML", reply_markup=back_kb)
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
        f"╔══════════════════════════╗\n"
        f"  {EMOJI_DIAMOND} <b>SHADOW VIP MEMBERSHIP</b> {EMOJI_ROCKET}\n"
        f"╚══════════════════════════╝\n"
        f"Automate your telegram marketing at scale with VIP power:\n\n"
        f"⚡ <b>Unlimited Hosted Accounts</b>\n"
        f"   └ <i>Host 10, 50, ya 100+ accounts bina kisi limit ke</i>\n\n"
        f"🛡️ <b>Anti-Ban Matrix & Rotation</b>\n"
        f"   └ <i>Smart account switching & FloodWait evasion</i>\n\n"
        f"🚀 <b>Ultra-Fast 2s Message Delay</b>\n"
        f"   └ <i>Turbocharged broadcast speed across target chats</i>\n\n"
        f"🌐 <b>Auto-Joiner & Group Targeting</b>\n"
        f"   └ <i>Accounts se automatically public & private groups join karein</i>\n\n"
        f"👑 <b>Priority 24/7 Cloud Engine</b>\n"
        f"   └ <i>Dedicated high-speed background worker pipeline</i>\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"{EMOJI_MONEY} <b>VIP PRICING & REWARDS:</b>\n"
        f"• 🎁 <b>1 Month VIP Access:</b> <code>5 Referrals</code> <i>(100% FREE!)</i>\n"
        f"• 💎 <b>Lifetime VIP Access:</b> <code>₹100 / $1.20</code>\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"👑 <b>Powered by:</b> <a href='https://t.me/SHADOW_SELLER07'>@SHADOW_SELLER07</a>\n\n"
        f"💬 <b>Instant VIP Activation Ke Liye Contact Karein:</b>\n"
        f"👉 <a href='https://t.me/SHADOW_SELLER07'>@SHADOW_SELLER07</a>"
    )
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Contact @SHADOW_SELLER07", url="https://t.me/SHADOW_SELLER07")],
        [InlineKeyboardButton(text="Refer 5 Friends (Free VIP)", callback_data="refer_earn", icon_custom_emoji_id=ID_GIFT)],
        [InlineKeyboardButton(text="Back to Dashboard", callback_data="back_to_dashboard", icon_custom_emoji_id=ID_BACK)]
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

    filled = min(ref_count, 5)
    progress_bar = "🟩" * filled + "⬜" * (5 - filled)
    ref_link = f"https://t.me/{bot_user}?start=ref_{user_id}"

    if ref_count >= 5 or is_premium:
        status_line = f"🎉 <b>Status:</b> <code>1-Month VIP Active & Unlocked!</code>"
    else:
        status_line = f"🎯 <b>Remaining:</b> <code>{5 - ref_count} more referrals needed for FREE VIP</code>"

    text = (
        f"╔══════════════════════════╗\n"
        f"  🎁 <b>REFER & EARN FREE VIP</b> {EMOJI_ROCKET}\n"
        f"╚══════════════════════════╝\n"
        f"Apne dosto ko bot refer karein aur <b>1-Month VIP Access bilkul FREE</b> payein!\n\n"
        f"┌ 👥 <b>Your Successful Referrals:</b> <code>{ref_count}</code> / <code>5</code>\n"
        f"├ 📊 <b>Progress:</b> {progress_bar}\n"
        f"└ {status_line}\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"🔗 <b>Your Exclusive Referral Link:</b>\n"
        f"<code>{ref_link}</code>\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"💡 <i>Upar diye gaye link ko copy karke dosto ya groups me share karein. Jaise hi 5 users bot start karenge, aapka 1 Month VIP automatically unlock ho jayega!</i>\n\n"
        f"👑 <b>Powered by:</b> <a href='https://t.me/SHADOW_SELLER07'>@SHADOW_SELLER07</a>"
    )

    share_text = "Turn your Alt account into an automated Telegram AdsBot with free trial and bulk power!"
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Share Link with Friends", url=f"https://t.me/share/url?url={ref_link}&text={share_text}")],
        [InlineKeyboardButton(text="Back to Dashboard", callback_data="back_to_dashboard", icon_custom_emoji_id=ID_BACK)]
    ])

    if call.message.photo:
        await call.message.delete()
        await call.message.answer(text, parse_mode="HTML", reply_markup=markup)
    else:
        await call.message.edit_text(text, parse_mode="HTML", reply_markup=markup)
