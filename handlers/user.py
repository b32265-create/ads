import logging
import asyncio
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, PhotoSize, Video, Document
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

import database as db
import keyboards as kb
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

def build_dashboard_text(bot_username: str, accounts_count: int, settings: dict) -> str:
    ad_msg = settings.get("ad_message")
    ad_media = settings.get("ad_media_id")
    if ad_msg or ad_media:
        media_tag = f" {EMOJI_PIN}" if ad_media else ""
        ad_status = f"{EMOJI_VERIFIED} Set{media_tag}"
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
    status_display = f"{EMOJI_PAUSED} Paused" if status.lower() == "paused" else f"{EMOJI_RUNNING} Running"

    # Schedule info
    sched_enabled = settings.get("schedule_enabled", 0)
    sched_start = settings.get("schedule_start") or "--:--"
    sched_end = settings.get("schedule_end") or "--:--"
    if sched_enabled:
        sched_status = f"{EMOJI_MOON} {sched_start} → {sched_end}"
    else:
        sched_status = f"{EMOJI_PAUSED} OFF"

    return (
        f"╰┈➤ {EMOJI_MSG} @{bot_username} DASHBOARD {EMOJI_FIRE}\n\n"
        f"• {EMOJI_PLANE} Hosted Accounts: <b>{accounts_count}</b>\n"
        f"• {EMOJI_MSG} Ad Message: <b>{ad_status}</b>\n"
        f"• {EMOJI_INTERVAL} Cycle Interval: <b>{interval_display}</b>\n"
        f"• {EMOJI_DELAY} Message Delay: <b>{delay}s</b>\n"
        f"• {EMOJI_TARGET} Target: <b>{target}</b>\n"
        f"• {EMOJI_MOON} Cycles: <b>{cycles_done}/{max_c_str}</b>\n"
        f"• {EMOJI_PAUSED} Status: <b>{status_display}</b>\n"
        f"• {EMOJI_CLOCK} Schedule: <b>{sched_status}</b>\n\n"
        f"╰┈➤ Choose an action below:"
    )

_CACHED_BOT_USERNAME: str = ""

async def get_bot_username(bot: Bot) -> str:
    global _CACHED_BOT_USERNAME
    if not _CACHED_BOT_USERNAME:
        bot_info = await bot.get_me()
        _CACHED_BOT_USERNAME = bot_info.username or "ALL_SHADOWS_BOT"
    return _CACHED_BOT_USERNAME

async def show_dashboard(bot: Bot, chat_id: int, user_id: int, message_to_edit: Message = None):
    """Utility to render and send/edit the exact dashboard with premium emojis."""
    bot_username = await get_bot_username(bot)

    accounts_count, settings = await asyncio.gather(
        db.get_account_count(user_id),
        db.get_user_settings(user_id)
    )

    text = build_dashboard_text(bot_username, accounts_count, settings)
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

    # Background registration so user doesn't wait for DB roundtrips
    asyncio.create_task(db.get_or_create_user(user_id, username, first_name))

    # Fast parallel check for ban status and force join
    user_info, (is_joined, unjoined) = await asyncio.gather(
        db.get_user_info(user_id),
        check_user_force_join(bot, user_id)
    )

    if user_info and user_info.get('is_banned', 0):
        await message.answer(
            f"{EMOJI_CROSS} <b>You are banned from using this bot.</b>\n"
            "Contact admin if you think this is a mistake.",
            parse_mode="HTML"
        )
        return

    if not is_joined:
        await message.answer(
            f"{EMOJI_WARNING} <b>Access Restricted!</b>\n\n"
            "Bot ko use karne ke liye pehle niche diye gaye channels join karein:\n",
            parse_mode="HTML",
            reply_markup=kb.get_force_join_keyboard(unjoined)
        )
        return

    await show_dashboard(bot, message.chat.id, user_id)

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
    media_note = f"\n{EMOJI_PIN} <b>Current Media:</b> Set" if has_media else ""

    text = (
        f"{EMOJI_MSG} <b>Set Your Ad Message</b>\n\n"
        f"{EMOJI_STAR} <b>Current Ad:</b>\n{current_ad}{media_note}\n\n"
        f"{EMOJI_SPARKLE} <b>Naya Ad content send karein:</b>\n"
        f"• {EMOJI_MSG} <b>Text only</b> - sirf text bhejo\n"
        f"• {EMOJI_HEART_FIRE} <b>Photo/Video/Doc</b> - media bhejo (caption = ad text)\n"
        f"• Caption optional hai, bina caption ke bhi chalega"
    )
    await state.set_state(UserStates.waiting_ad_message)
    await call.message.edit_text(text, parse_mode="HTML", reply_markup=kb.get_back_keyboard())

@router.message(UserStates.waiting_ad_message)
async def process_ad_message(message: Message, bot: Bot, state: FSMContext):
    user_id = message.from_user.id

    # Detect media type
    ad_text = message.text or message.caption or ""
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
            f"{EMOJI_CROSS} Kuch bhi nahi mila! Text ya media (photo/video/doc) bhejo.",
            reply_markup=kb.get_back_keyboard()
        )
        return

    await db.update_user_setting(user_id, "ad_message", ad_text)
    await db.update_user_setting(user_id, "ad_media_id", media_id)
    await db.update_user_setting(user_id, "ad_media_type", media_type)
    await state.clear()

    media_note = f"\n{EMOJI_PIN} <b>Media Type:</b> {media_type}" if media_id else ""
    await message.answer(
        f"{EMOJI_VERIFIED} <b>Ad Message saved!</b>{media_note}",
        parse_mode="HTML"
    )
    await show_dashboard(bot, message.chat.id, user_id)

# --- SET INTERVAL ---
@router.callback_query(F.data == "set_interval")
async def btn_set_interval(call: CallbackQuery):
    await call.answer()
    text = (
        f"{EMOJI_INTERVAL} <b>Set Cycle Interval</b>\n\n"
        "Ek ad cycle complete hone ke baad agli cycle shuru hone ka time select karein:"
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
            f"{EMOJI_SPARKLE} <b>Enter custom interval in seconds:</b>\n(Example: <code>900</code> for 15 minutes)",
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
            await message.answer(f"{EMOJI_WARNING} Minimum interval is 30 seconds.", reply_markup=kb.get_back_keyboard())
            return
        await db.update_user_setting(user_id, "cycle_interval", seconds)
        await state.clear()
        await message.answer(f"{EMOJI_VERIFIED} Interval set to {format_interval(seconds)}!")
        await show_dashboard(bot, message.chat.id, user_id)
    except ValueError:
        await message.answer(f"{EMOJI_CROSS} Please enter a valid number of seconds.", reply_markup=kb.get_back_keyboard())

# --- SET DELAY ---
@router.callback_query(F.data == "set_delay")
async def btn_set_delay(call: CallbackQuery):
    await call.answer()
    text = (
        f"{EMOJI_DELAY} <b>Set Message Delay</b>\n\n"
        "Har group me ad post karne ke beech kitna second ka gap rakhna hai taaki FloodWait na aaye:"
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
            f"{EMOJI_SPARKLE} <b>Enter message delay in seconds:</b>\n(e.g. <code>5</code>)",
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
            await message.answer(f"{EMOJI_WARNING} Minimum delay is 1 second.", reply_markup=kb.get_back_keyboard())
            return
        await db.update_user_setting(user_id, "message_delay", seconds)
        await state.clear()
        await message.answer(f"{EMOJI_VERIFIED} Delay set to {seconds}s!")
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
        f"{EMOJI_MOON} <b>Set Ad Cycles</b>\n\n"
        "Aap kitni cycles ad run karna chahte hain select karein:"
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
            f"{EMOJI_SPARKLE} <b>Enter number of cycles:</b>\n(e.g. <code>25</code> or <code>0</code> for unlimited)",
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
        await message.answer(f"{EMOJI_VERIFIED} Cycles set to {cycle_str}!")
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
        f"{EMOJI_GIFT} <b>Exclude Groups</b>\n\n"
        f"{EMOJI_WARNING} <b>Currently Excluded:</b>\n<code>{excluded}</code>\n\n"
        "Jin groups me ads post nahi karni, unke usernames ya IDs comma se separate karke send karein:\n"
        "<i>(Example: @group1, @group2, -100123456789)</i>"
    )
    await state.set_state(UserStates.waiting_exclude_groups)
    await call.message.edit_text(text, parse_mode="HTML", reply_markup=kb.get_back_keyboard())

@router.message(UserStates.waiting_exclude_groups)
async def process_exclude_groups(message: Message, bot: Bot, state: FSMContext):
    user_id = message.from_user.id
    ex_text = message.text.strip()
    await db.update_user_setting(user_id, "exclude_groups", ex_text)
    await state.clear()
    await message.answer(f"{EMOJI_VERIFIED} <b>Excluded groups list updated!</b>", parse_mode="HTML")
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
    header = f"{EMOJI_SPARKLE} <b>AD PREVIEW</b>\n────────────────────\n"

    if media_id:
        caption = f"{header}{ad_text}" if ad_text else f"{header}<i>(No caption)</i>"
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
                await bot.send_message(call.message.chat.id, f"{header}{ad_text}", parse_mode="HTML", reply_markup=back_kb)
            
            try:
                await call.message.delete()
            except Exception:
                pass
            return
        except Exception as e:
            await call.message.edit_text(f"{header}{ad_text}\n\n{EMOJI_WARNING} <i>(Media preview error: {e})</i>", parse_mode="HTML", reply_markup=back_kb)
            return

    # Text only ad
    preview_content = f"{header}{ad_text}"
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

    text = (
        f"{EMOJI_STATS} <b>CAMPAIGN ANALYTICS</b> {EMOJI_FIRE}\n\n"
        f"• {EMOJI_PLANE} <b>Total Accounts:</b> <code>{len(accounts)}</code>\n"
        f"• {EMOJI_ROCKET} <b>Total Ads Sent:</b> <code>{data.get('total_sent', 0)}</code>\n"
        f"• {EMOJI_WARNING} <b>Failed / Skipped:</b> <code>{data.get('total_failed', 0)}</code>\n"
        f"• {EMOJI_CLOCK} <b>Last Active:</b> <code>{data.get('last_sent_at', 'Never')}</code>\n"
    )

    if accounts:
        text += f"\n{EMOJI_PHONE} <b>Per Account Stats:</b>\n"
        for acc in accounts:
            ban_tag = f" {EMOJI_CROSS}" if acc.get("is_banned") else ""
            text += (
                f"• <b>{acc.get('account_name', 'N/A')}</b>{ban_tag} — "
                f"Sent: <code>{acc.get('total_sent', 0)}</code> | "
                f"Failed: <code>{acc.get('total_failed', 0)}</code>\n"
            )

    text += f"\n{EMOJI_SPARKLE} <i>All metrics updated in real-time.</i>"
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
    status_str = f"{EMOJI_RUNNING} Enabled" if sched_enabled else f"{EMOJI_PAUSED} Disabled"

    text = (
        f"{EMOJI_CLOCK} <b>Schedule Ads</b>\n\n"
        f"• <b>Status:</b> {status_str}\n"
        f"• <b>Start Time:</b> <code>{sched_start}</code>\n"
        f"• <b>End Time:</b> <code>{sched_end}</code>\n\n"
        "<i>Set karo ki ads kab se kab tak chalein (24-hour format, e.g. 09:00 to 22:00)\n"
        "Overnight bhi support hai (e.g. 22:00 to 06:00)</i>"
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
        f"{EMOJI_CLOCK} <b>Set Schedule Start Time</b>\n\n"
        "Ads kab se shuru hon? Time enter karein:\n"
        "<i>(24-hour format, e.g. <code>09:00</code> or <code>22:30</code>)</i>",
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
            f"{EMOJI_CROSS} Invalid format! <code>HH:MM</code> format mein enter karein (e.g. <code>09:00</code>)",
            parse_mode="HTML"
        )
        return

    await db.update_user_setting(user_id, "schedule_start", clean_time)
    await state.clear()
    await message.answer(f"{EMOJI_VERIFIED} <b>Start Time set to {clean_time}</b>", parse_mode="HTML")
    await show_dashboard(bot=message.bot, chat_id=message.chat.id, user_id=user_id)

@router.callback_query(F.data == "schedule_set_end")
async def schedule_set_end(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await state.set_state(UserStates.waiting_schedule_end)
    await call.message.edit_text(
        f"{EMOJI_CLOCK} <b>Set Schedule End Time</b>\n\n"
        "Ads kab band hon? Time enter karein:\n"
        "<i>(24-hour format, e.g. <code>22:00</code> or <code>06:00</code>)</i>",
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
            f"{EMOJI_CROSS} Invalid format! <code>HH:MM</code> format mein enter karein (e.g. <code>22:00</code>)",
            parse_mode="HTML"
        )
        return

    await db.update_user_setting(user_id, "schedule_end", clean_time)
    await state.clear()
    await message.answer(f"{EMOJI_VERIFIED} <b>End Time set to {clean_time}</b>", parse_mode="HTML")
    await show_dashboard(bot=message.bot, chat_id=message.chat.id, user_id=user_id)

# --- PREMIUM ---
@router.callback_query(F.data == "premium")
async def btn_premium(call: CallbackQuery):
    await call.answer()
    text = (
        f"{EMOJI_FLASH} <b>SHADOW ADS PREMIUM</b> {EMOJI_DIAMOND}\n\n"
        "Upgrade to Premium for exclusive marketing power:\n\n"
        f"• {EMOJI_VERIFIED} <b>Unlimited Hosted Accounts</b>\n"
        f"• {EMOJI_FLASH} <b>Fast 2s Anti-ban message delay</b>\n"
        f"• {EMOJI_SPARKLE} <b>Smart Account Rotation</b>\n"
        f"• {EMOJI_TARGET} <b>Auto Joiner & Group Targeting</b>\n"
        f"• {EMOJI_ROCKET} <b>24/7 Dedicated Cloud Runner</b>\n\n"
        f"{EMOJI_MSG} Contact Admin for upgrades & pricing!"
    )
    await call.message.edit_text(text, parse_mode="HTML", reply_markup=kb.get_back_keyboard())
