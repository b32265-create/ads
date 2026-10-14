import logging
import asyncio
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

import database as db
import keyboards as kb
from config import ADMIN_IDS, API_ID, API_HASH
from telethon import TelegramClient
from telethon.sessions import StringSession
from join_helper import join_telegram_target
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
    EMOJI_GIFT, EMOJI_TRASH, EMOJI_BROADCAST
)

logger = logging.getLogger(__name__)

router = Router(name="admin_router")

class AdminStates(StatesGroup):
    waiting_broadcast = State()
    waiting_fsub_id = State()
    waiting_fsub_title = State()
    waiting_fsub_link = State()
    waiting_user_search = State()
    waiting_global_setting = State()
    waiting_mass_join_link = State()
    waiting_log_account = State()

def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS

def get_admin_panel_text() -> str:
    return (
        f"╔══════════════════════════╗\n"
        f"  👨‍💻 <b>SHADOW COMMAND CENTER</b> ⚡\n"
        f"╚══════════════════════════╝\n"
        f"{EMOJI_FLASH} <i>Full administrator control over user tiers, channels, broadcast, & database settings.</i>"
    )

# --- ADMIN PANEL COMMAND ---
@router.message(Command("admin"))
async def cmd_admin(message: Message, state: FSMContext):
    await state.clear()
    if not is_admin(message.from_user.id):
        await message.answer(f"{EMOJI_CROSS} <i>Access Denied. You are not an admin.</i>", parse_mode="HTML")
        return

    await message.answer(get_admin_panel_text(), parse_mode="HTML", reply_markup=kb.get_admin_keyboard())

# --- ADMIN BACK & CLOSE ---
@router.callback_query(F.data == "admin_back")
async def admin_back(call: CallbackQuery, state: FSMContext):
    await state.clear()
    if not is_admin(call.from_user.id): return
    await call.message.edit_text(get_admin_panel_text(), parse_mode="HTML", reply_markup=kb.get_admin_keyboard())

@router.callback_query(F.data == "admin_close")
async def admin_close(call: CallbackQuery):
    await call.answer()
    await call.message.delete()

# ─────────────────────────────────────────────
# ADMIN STATS
# ─────────────────────────────────────────────
@router.callback_query(F.data == "admin_stats")
async def admin_stats(call: CallbackQuery):
    if not is_admin(call.from_user.id): return
    await call.answer()

    (
        total_users, premium_users, banned_users,
        fsub_channels, active_campaigns, global_sent, total_accounts
    ) = await asyncio.gather(
        db.get_user_count(),
        db.get_premium_user_count(),
        db.get_banned_user_count(),
        db.get_active_force_channels(),
        db.get_total_active_campaigns(),
        db.get_global_total_sent(),
        db.get_total_accounts()
    )

    text = (
        f"╔══════════════════════════╗\n"
        f"  {EMOJI_STATS} <b>SYSTEM TELEMETRY & STATS</b>\n"
        f"╚══════════════════════════╝\n"
        f"┌ {EMOJI_USER} <b>Total Registered Users:</b> <code>{total_users:,}</code>\n"
        f"├ {EMOJI_DIAMOND} <b>VIP Premium Members:</b> <code>{premium_users:,}</code>\n"
        f"├ {EMOJI_CROSS} <b>Suspended / Banned:</b> <code>{banned_users:,}</code>\n"
        f"├ {EMOJI_PLANE} <b>Total Hosted Accounts:</b> <code>{total_accounts:,}</code>\n"
        f"├ {EMOJI_ROCKET} <b>Active Campaigns Running:</b> <code>{active_campaigns:,}</code>\n"
        f"├ {EMOJI_MSG} <b>All-time Ads Broadcasted:</b> <code>{global_sent:,}</code>\n"
        f"├ {EMOJI_TARGET} <b>Active Force-Join Channels:</b> <code>{len(fsub_channels)}</code>\n"
        f"└ {EMOJI_FLASH} <b>Engine:</b> <code>aiogram 3.14 + Telethon + PostgreSQL</code>\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"🟢 <i>Database Pool: Healthy (5-30 connections active)</i>"
    )
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Back", callback_data="admin_back", icon_custom_emoji_id=ID_BACK)]
    ])
    await call.message.edit_text(text, parse_mode="HTML", reply_markup=markup)

# ─────────────────────────────────────────────
# BROADCAST SYSTEM
# ─────────────────────────────────────────────
@router.callback_query(F.data == "admin_broadcast")
async def admin_broadcast_prompt(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id): return
    await call.answer()

    await state.set_state(AdminStates.waiting_broadcast)
    text = (
        f"╔══════════════════════════╗\n"
        f"  {EMOJI_BROADCAST} <b>GLOBAL BROADCAST</b>\n"
        f"╚══════════════════════════╝\n"
        f"Aap jo message sabhi registered bot users ko bhejna chahte hain, wo yahan send karein.\n\n"
        f"<i>(Supports Text, Photos, Videos, Documents, Stickers, and Forwards)</i>\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"👉 <i>Message forward ya type karke bhejein:</i>"
    )
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Cancel", callback_data="admin_back", icon_custom_emoji_id=ID_BACK)]
    ])
    await call.message.edit_text(text, parse_mode="HTML", reply_markup=markup)

@router.message(AdminStates.waiting_broadcast)
async def process_admin_broadcast(message: Message, bot: Bot, state: FSMContext):
    if not is_admin(message.from_user.id): return
    await state.clear()

    users = await db.get_all_user_ids()
    status_msg = await message.answer(f"{EMOJI_CLOCK} <i>Broadcasting to {len(users):,} users in background...</i>", parse_mode="HTML")

    sent_count = 0
    fail_count = 0

    for uid in users:
        try:
            await message.copy_to(chat_id=uid)
            sent_count += 1
            await asyncio.sleep(0.04)  # Rate limiting
        except Exception:
            fail_count += 1

    await status_msg.edit_text(
        f"╔══════════════════════════╗\n"
        f"  {EMOJI_VERIFIED} <b>BROADCAST DISPATCHED!</b>\n"
        f"╚══════════════════════════╝\n"
        f"• {EMOJI_VERIFIED} Successfully Delivered: <code>{sent_count:,}</code>\n"
        f"• {EMOJI_CROSS} Failed / Blocked: <code>{fail_count:,}</code>",
        parse_mode="HTML"
    )

# ─────────────────────────────────────────────
# USER MANAGEMENT
# ─────────────────────────────────────────────
@router.callback_query(F.data == "admin_users")
async def admin_users_menu(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id): return
    await call.answer()

    total, premium, banned = await asyncio.gather(
        db.get_user_count(),
        db.get_premium_user_count(),
        db.get_banned_user_count()
    )

    text = (
        f"╔══════════════════════════╗\n"
        f"  {EMOJI_USER} <b>USER MANAGEMENT DIRECTORY</b>\n"
        f"╚══════════════════════════╝\n"
        f"• 👥 <b>Total Users:</b> <code>{total:,}</code>\n"
        f"• 💎 <b>VIP Members:</b> <code>{premium:,}</code>\n"
        f"• 🚫 <b>Suspended:</b> <code>{banned:,}</code>\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"Kisi user ki details dekhne ya unhe VIP / Ban karne ke liye unka <b>Telegram ID</b> ya <b>@username</b> yahan send karein:"
    )
    await state.set_state(AdminStates.waiting_user_search)
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Back to Admin", callback_data="admin_back", icon_custom_emoji_id=ID_BACK)]
    ])
    await call.message.edit_text(text, parse_mode="HTML", reply_markup=markup)

@router.message(AdminStates.waiting_user_search)
async def process_user_search(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id): return

    query = message.text.strip()
    user = await db.search_user_by_id_or_username(query)

    if not user:
        await message.answer(
            f"{EMOJI_CROSS} User <code>{query}</code> nahi mila database me.\n\nDobara try karein ya sahi ID bhejein:",
            parse_mode="HTML"
        )
        return

    await state.clear()
    await _show_user_management(message, user)

async def _show_user_management(message_or_call, user: dict):
    uid = user['user_id']
    uname = f"@{user['username']}" if user.get('username') else "N/A"
    fname = user.get('first_name', 'N/A')
    is_banned = user.get('is_banned', 0)
    is_premium = user.get('is_premium', 0)
    joined = str(user.get('joined_at', 'N/A'))[:16]

    acc_count, analytics = await asyncio.gather(
        db.get_account_count(uid),
        db.get_analytics(uid)
    )

    status_tag = f"{EMOJI_CROSS} Banned" if is_banned else (f"{EMOJI_DIAMOND} VIP PRO" if is_premium else f"{EMOJI_VERIFIED} Standard Free")

    text = (
        f"╔══════════════════════════╗\n"
        f"  {EMOJI_USER} <b>USER DOSSIER & SETTINGS</b>\n"
        f"╚══════════════════════════╝\n"
        f"• 👤 <b>Name:</b> {fname}\n"
        f"• 🏷️ <b>Username:</b> {uname}\n"
        f"• 🆔 <b>User ID:</b> <code>{uid}</code>\n"
        f"• 📅 <b>Registered:</b> <code>{joined}</code>\n"
        f"• 🎖️ <b>Tier:</b> {status_tag}\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"┌ 📱 <b>Hosted Accounts:</b> <code>{acc_count}</code>\n"
        f"├ 🚀 <b>Total Ads Dispatched:</b> <code>{analytics.get('total_sent', 0):,}</code>\n"
        f"└ ⚠️ <b>Failed / Skipped:</b> <code>{analytics.get('total_failed', 0):,}</code>\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"👉 <i>Select administrative action:</i>"
    )

    ban_btn_text = "Unban User" if is_banned else "Ban User"
    ban_cb = f"admin_unban_{uid}" if is_banned else f"admin_ban_{uid}"
    ban_icon = ID_VERIFIED if is_banned else ID_WARNING

    prem_btn_text = "Demote to Free" if is_premium else "Grant VIP Premium"
    prem_cb = f"admin_unpremium_{uid}" if is_premium else f"admin_premium_{uid}"
    prem_icon = ID_DIAMOND

    markup = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=ban_btn_text, callback_data=ban_cb, icon_custom_emoji_id=ban_icon),
            InlineKeyboardButton(text=prem_btn_text, callback_data=prem_cb, icon_custom_emoji_id=prem_icon),
        ],
        [InlineKeyboardButton(text="Back to Admin", callback_data="admin_back", icon_custom_emoji_id=ID_BACK)]
    ])

    if hasattr(message_or_call, 'answer'):
        await message_or_call.answer(text, parse_mode="HTML", reply_markup=markup)
    else:
        await message_or_call.message.edit_text(text, parse_mode="HTML", reply_markup=markup)

@router.callback_query(F.data.startswith("admin_ban_"))
async def admin_ban_user(call: CallbackQuery, bot: Bot):
    if not is_admin(call.from_user.id): return
    uid = int(call.data.replace("admin_ban_", ""))
    await db.set_user_banned(uid, True)
    await call.answer("User banned!", show_alert=True)
    try:
        await bot.send_message(uid, f"{EMOJI_CROSS} <b>You have been banned from using this bot.</b>", parse_mode="HTML")
    except Exception:
        pass
    user = await db.get_user_info(uid)
    if user:
        await _show_user_management(call, user)

@router.callback_query(F.data.startswith("admin_unban_"))
async def admin_unban_user(call: CallbackQuery, bot: Bot):
    if not is_admin(call.from_user.id): return
    uid = int(call.data.replace("admin_unban_", ""))
    await db.set_user_banned(uid, False)
    await call.answer("User unbanned!", show_alert=True)
    try:
        await bot.send_message(uid, f"{EMOJI_VERIFIED} <b>Your ban has been lifted. You can use the bot again!</b>", parse_mode="HTML")
    except Exception:
        pass
    user = await db.get_user_info(uid)
    if user:
        await _show_user_management(call, user)

@router.callback_query(F.data.startswith("admin_premium_"))
async def admin_grant_premium(call: CallbackQuery, bot: Bot):
    if not is_admin(call.from_user.id): return
    uid = int(call.data.replace("admin_premium_", ""))
    await db.set_user_premium(uid, True)
    await call.answer("VIP Premium granted!", show_alert=True)
    try:
        await bot.send_message(
            uid,
            f"╔══════════════════════════╗\n"
            f"  {EMOJI_DIAMOND} <b>VIP PRO UPGRADE UNLOCKED!</b> 🎉\n"
            f"╚══════════════════════════╝\n"
            f"Aapke account par VIP status activate kar diya gaya hai!\n\n"
            f"• Unlimited Accounts Hosting\n"
            f"• Priority Cloud Routing\n\n"
            f"Use /start to access your upgraded features.",
            parse_mode="HTML"
        )
    except Exception:
        pass
    user = await db.get_user_info(uid)
    if user:
        await _show_user_management(call, user)

@router.callback_query(F.data.startswith("admin_unpremium_"))
async def admin_remove_premium(call: CallbackQuery, bot: Bot):
    if not is_admin(call.from_user.id): return
    uid = int(call.data.replace("admin_unpremium_", ""))
    await db.set_user_premium(uid, False)
    await call.answer("Premium removed!", show_alert=True)
    try:
        await bot.send_message(uid, f"{EMOJI_WARNING} <b>Your VIP Premium access has been downgraded to standard free tier.</b>", parse_mode="HTML")
    except Exception:
        pass
    user = await db.get_user_info(uid)
    if user:
        await _show_user_management(call, user)

# ─────────────────────────────────────────────
# FORCE JOIN MANAGEMENT
# ─────────────────────────────────────────────
@router.callback_query(F.data == "admin_fsub")
async def admin_fsub_list(call: CallbackQuery):
    if not is_admin(call.from_user.id): return
    await call.answer()

    channels = await db.get_active_force_channels()
    text = (
        f"╔══════════════════════════╗\n"
        f"  {EMOJI_TARGET} <b>FORCE JOIN CHANNELS</b>\n"
        f"╚══════════════════════════╝\n"
        f"Users ko bot access karne se pehle in channels ko join karna zaroori hai.\n\n"
        f"📢 <b>Currently Configured:</b> <code>{len(channels)} Channels</code>\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"👉 Naya channel add karne ke liye 'Add New Channel' click karein:"
    )
    await call.message.edit_text(text, parse_mode="HTML", reply_markup=kb.get_admin_fsub_keyboard(channels))

@router.callback_query(F.data == "admin_add_fsub")
async def admin_add_fsub_step1(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id): return
    await call.answer()

    await state.set_state(AdminStates.waiting_fsub_id)
    text = (
        f"╔══════════════════════════╗\n"
        f"  {EMOJI_HEART_FIRE} <b>ADD CHANNEL (STEP 1/3)</b>\n"
        f"╚══════════════════════════╝\n"
        f"Channel ka <b>Username</b> ya <b>ID</b> enter karein:\n"
        f"<i>(Example: @MyChannel ya -1001234567890)</i>\n\n"
        f"⚠️ <i>Important: Bot ka us channel me Admin hona zaroori hai!</i>"
    )
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Cancel", callback_data="admin_fsub", icon_custom_emoji_id=ID_BACK)]
    ])
    await call.message.edit_text(text, parse_mode="HTML", reply_markup=markup)

@router.message(AdminStates.waiting_fsub_id)
async def admin_add_fsub_step2(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id): return
    ch_id = message.text.strip()
    await state.update_data(channel_id=ch_id)

    await state.set_state(AdminStates.waiting_fsub_title)
    await message.answer(
        f"{EMOJI_PIN} <b>Enter Channel Display Title (Step 2/3):</b>\n(Example: <code>Official Updates</code>)",
        parse_mode="HTML"
    )

@router.message(AdminStates.waiting_fsub_title)
async def admin_add_fsub_step3(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id): return
    title = message.text.strip()
    await state.update_data(title=title)

    await state.set_state(AdminStates.waiting_fsub_link)
    await message.answer(
        f"{EMOJI_TARGET} <b>Enter Invite Link (Step 3/3):</b>\n(Example: <code>https://t.me/MyChannel</code>)",
        parse_mode="HTML"
    )

@router.message(AdminStates.waiting_fsub_link)
async def admin_add_fsub_finish(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id): return
    link = message.text.strip()
    data = await state.get_data()

    ch_id = data.get("channel_id")
    title = data.get("title")

    await db.add_force_channel(ch_id, title, link)
    await state.clear()

    await message.answer(
        f"╔══════════════════════════╗\n"
        f"  {EMOJI_VERIFIED} <b>CHANNEL CONFIGURED!</b>\n"
        f"╚══════════════════════════╝\n"
        f"• <b>Title:</b> {title}\n"
        f"• <b>Identifier:</b> <code>{ch_id}</code>\n"
        f"• <b>Link:</b> {link}",
        parse_mode="HTML"
    )

@router.callback_query(F.data.startswith("admin_del_fsub_"))
async def admin_delete_fsub(call: CallbackQuery):
    if not is_admin(call.from_user.id): return
    ch_id = call.data.replace("admin_del_fsub_", "")
    await db.remove_force_channel(ch_id)
    await call.answer("Channel removed from Force Join!")
    await admin_fsub_list(call)

# ─────────────────────────────────────────────
# GLOBAL SETTINGS
# ─────────────────────────────────────────────
@router.callback_query(F.data == "admin_settings")
async def admin_global_settings(call: CallbackQuery):
    if not is_admin(call.from_user.id): return
    await call.answer()

    settings = await db.get_all_bot_settings()
    maintenance = settings.get("maintenance_mode", "0")
    max_accs = settings.get("max_accounts_per_user", "5")

    maintenance_text = f"{EMOJI_PAUSED} ON (Maintenance Active)" if maintenance == "1" else f"{EMOJI_RUNNING} OFF (Live for all)"

    text = (
        f"╔══════════════════════════╗\n"
        f"  {EMOJI_GEAR} <b>GLOBAL ENGINE CONFIGURATION</b>\n"
        f"╚══════════════════════════╝\n"
        f"• {EMOJI_WARNING} <b>Maintenance Mode:</b> {maintenance_text}\n"
        f"• {EMOJI_USER} <b>Free Account Cap:</b> <code>{max_accs} Accounts/User</code>\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"👉 <i>Niche settings badal sakte hain:</i>"
    )
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="Toggle Maintenance",
                callback_data="admin_toggle_maintenance",
                icon_custom_emoji_id=ID_WARNING
            )
        ],
        [
            InlineKeyboardButton(text="Set Max Accounts/User", callback_data="admin_set_max_accounts", icon_custom_emoji_id=ID_USER)
        ],
        [InlineKeyboardButton(text="Back to Admin", callback_data="admin_back", icon_custom_emoji_id=ID_BACK)]
    ])
    await call.message.edit_text(text, parse_mode="HTML", reply_markup=markup)

@router.callback_query(F.data == "admin_toggle_maintenance")
async def admin_toggle_maintenance(call: CallbackQuery):
    if not is_admin(call.from_user.id): return
    current = await db.get_bot_setting("maintenance_mode", "0")
    new_val = "0" if current == "1" else "1"
    await db.set_bot_setting("maintenance_mode", new_val)
    status = "ON (Bot is now under maintenance)" if new_val == "1" else "OFF (Bot is live)"
    await call.answer(f"Maintenance: {status}", show_alert=True)
    await admin_global_settings(call)

@router.callback_query(F.data == "admin_set_max_accounts")
async def admin_set_max_accounts_prompt(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id): return
    await call.answer()
    await state.set_state(AdminStates.waiting_global_setting)
    await state.update_data(setting_key="max_accounts_per_user")
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Cancel", callback_data="admin_settings", icon_custom_emoji_id=ID_BACK)]
    ])
    await call.message.edit_text(
        f"╔══════════════════════════╗\n"
        f"  {EMOJI_USER} <b>FREE ACCOUNT LIMIT CAP</b>\n"
        f"╚══════════════════════════╝\n"
        f"Standard free users ke liye maximum account limit number enter karein:\n\n"
        f"<i>(Example: <code>3</code> ya <code>5</code> ya <code>10</code>)</i>",
        parse_mode="HTML",
        reply_markup=markup
    )

@router.message(AdminStates.waiting_global_setting)
async def process_global_setting(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id): return
    data = await state.get_data()
    key = data.get("setting_key", "")
    value = message.text.strip()

    if key == "max_accounts_per_user":
        try:
            int(value)
        except ValueError:
            await message.answer(f"{EMOJI_CROSS} Valid positive integer enter karein!")
            return

    await db.set_bot_setting(key, value)
    await state.clear()
    await message.answer(f"{EMOJI_VERIFIED} <b>Global parameter updated!</b>\n<code>{key}</code> = <code>{value}</code>", parse_mode="HTML")

# ─────────────────────────────────────────────
# LOG ACCOUNT MANAGEMENT
# ─────────────────────────────────────────────
@router.callback_query(F.data == "admin_log_account")
async def admin_log_account_view(call: CallbackQuery):
    if not is_admin(call.from_user.id): return
    await call.answer()
    
    current_log = await db.get_log_account()
    log_display = f"@{current_log}" if current_log else "<i>Not Set (Disabled)</i>"
    
    text = (
        f"╔══════════════════════════╗\n"
        f"  📡 <b>LIVE LOG ACCOUNT CONFIG</b>\n"
        f"╚══════════════════════════╝\n"
        f"Aap ek official Telegram Log Account ya Channel set kar sakte hain.\n"
        f"Jab user bot start karega, toh usse is Log Account ka direct link milega, jahan se wo apne automated ads ke live delivery logs dekh sakega.\n\n"
        f"┌ 📡 <b>Current Log Account:</b> <code>{log_display}</code>\n"
        f"└ ⚙️ <b>Status:</b> {'🟢 Active' if current_log else '🔴 Inactive'}\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"Niche button se naya account username set ya clear karein:"
    )
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Set / Change Log Account", callback_data="admin_set_log_acc", icon_custom_emoji_id=ID_STAR)],
        [InlineKeyboardButton(text="Remove / Clear Log Account", callback_data="admin_clear_log_acc", icon_custom_emoji_id=ID_TRASH)],
        [InlineKeyboardButton(text="Back to Admin", callback_data="admin_back", icon_custom_emoji_id=ID_BACK)]
    ])
    await call.message.edit_text(text, parse_mode="HTML", reply_markup=markup)

@router.callback_query(F.data == "admin_clear_log_acc")
async def admin_clear_log_account(call: CallbackQuery):
    if not is_admin(call.from_user.id): return
    await db.set_log_account("")
    await call.answer("Log account cleared!", show_alert=True)
    await admin_log_account_view(call)

@router.callback_query(F.data == "admin_set_log_acc")
async def admin_set_log_account_prompt(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id): return
    await call.answer()
    await state.set_state(AdminStates.waiting_log_account)
    
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Cancel", callback_data="admin_log_account", icon_custom_emoji_id=ID_BACK)]
    ])
    await call.message.edit_text(
        f"╔══════════════════════════╗\n"
        f"  📡 <b>ENTER LOG ACCOUNT USERNAME</b>\n"
        f"╚══════════════════════════╝\n"
        f"Log account ya bot ka Telegram username enter karein:\n\n"
        f"<i>(Example: <code>@shadow_logs_bot</code> ya <code>shadow_logs</code>)</i>",
        parse_mode="HTML",
        reply_markup=markup
    )

@router.message(AdminStates.waiting_log_account)
async def process_set_log_account(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id): return
    val = message.text.strip().replace("@", "")
    if not val:
        await message.answer(f"{EMOJI_CROSS} Invalid username.")
        return
    await db.set_log_account(val)
    await state.clear()
    await message.answer(
        f"╔══════════════════════════╗\n"
        f"  {EMOJI_VERIFIED} <b>LOG ACCOUNT UPDATED!</b>\n"
        f"╚══════════════════════════╝\n"
        f"Naya Log Account set ho gaya: <b>@{val}</b>\n"
        f"Users ko welcome screen par iska connection badge show hoga.",
        parse_mode="HTML",
        reply_markup=kb.get_admin_keyboard()
    )

# ─────────────────────────────────────────────
# MASS JOIN TO ALL ACCOUNTS (10-SECOND TIMER GAP)
# ─────────────────────────────────────────────
_mass_join_cancelled = False
_is_mass_join_running = False

@router.callback_query(F.data == "admin_mass_join")
async def admin_mass_join_prompt(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id): return
    await call.answer()

    total_accs = await db.get_total_accounts()
    
    text = (
        f"╔══════════════════════════╗\n"
        f"  {EMOJI_ROCKET} <b>MASS JOIN TO ALL ACCOUNTS</b>\n"
        f"╚══════════════════════════╝\n"
        f"Yahan Public username ya Private invite link enter karein.\n"
        f"Bot sabhi <b>{total_accs:,}</b> hosted active accounts se <b>10 seconds ke timer gap</b> par 1-by-1 us link ko join karwayega:\n\n"
        f"• <b>Public Channel/Group:</b> <code>@username</code> ya <code>https://t.me/username</code>\n"
        f"• <b>Private Invite Link:</b> <code>https://t.me/+inviteHash</code> ya <code>https://t.me/joinchat/...</code>\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"🛡️ <i>Anti-Ban Safety: 10s gap per account enforced.</i>\n\n"
        f"👉 <i>Channel/Group link yahan send karein:</i>"
    )
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Cancel", callback_data="admin_back", icon_custom_emoji_id=ID_BACK)]
    ])
    await state.set_state(AdminStates.waiting_mass_join_link)
    await call.message.edit_text(text, parse_mode="HTML", reply_markup=markup)

@router.callback_query(F.data == "cancel_mass_join")
async def admin_cancel_mass_join(call: CallbackQuery):
    if not is_admin(call.from_user.id): return
    global _mass_join_cancelled
    _mass_join_cancelled = True
    await call.answer("🛑 Mass Join cancel request sent! It will stop after the current account.", show_alert=True)

@router.message(AdminStates.waiting_mass_join_link)
async def process_admin_mass_join(message: Message, bot: Bot, state: FSMContext):
    if not is_admin(message.from_user.id): return
    global _is_mass_join_running, _mass_join_cancelled
    
    if _is_mass_join_running:
        await message.answer(
            f"{EMOJI_WARNING} <b>Ek Mass Join already background me run ho raha hai!</b>\n"
            f"Kripya uske complete hone ka wait karein ya Cancel button dabayein.",
            parse_mode="HTML",
            reply_markup=kb.get_admin_keyboard()
        )
        return

    link = message.text.strip()
    if not link:
        await message.answer(f"{EMOJI_CROSS} Invalid link.", reply_markup=kb.get_admin_keyboard())
        return

    await state.clear()
    accounts = await db.get_all_active_accounts()
    if not accounts:
        await message.answer(
            f"╔══════════════════════════╗\n"
            f"  {EMOJI_WARNING} <b>NO ACTIVE ACCOUNTS</b>\n"
            f"╚══════════════════════════╝\n"
            f"Database me koi active account nahi mila.",
            parse_mode="HTML",
            reply_markup=kb.get_admin_keyboard()
        )
        return

    total = len(accounts)
    est_sec = total * 10
    est_str = f"{est_sec // 60}m {est_sec % 60}s" if est_sec >= 60 else f"{est_sec}s"

    cancel_markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Stop / Cancel Mass Join", callback_data="cancel_mass_join", icon_custom_emoji_id=ID_PAUSED)]
    ])

    status_msg = await message.answer(
        f"╔══════════════════════════╗\n"
        f"  {EMOJI_ROCKET} <b>MASS JOIN INITIATED</b>\n"
        f"╚══════════════════════════╝\n"
        f"┌ 🔗 <b>Target:</b> <code>{link}</code>\n"
        f"├ 📱 <b>Total Accounts:</b> <code>{total}</code>\n"
        f"├ ⏱️ <b>Timer Gap:</b> <code>10 seconds</code>\n"
        f"└ ⏳ <b>Estimated Time:</b> <code>~{est_str}</code>\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"🔄 <i>Mass join background me chalu ho gaya hai. Har account 10s ke gap me join karega...</i>",
        parse_mode="HTML",
        reply_markup=cancel_markup
    )

    _mass_join_cancelled = False
    _is_mass_join_running = True

    asyncio.create_task(
        run_mass_join_worker(
            bot=bot,
            admin_chat_id=message.chat.id,
            status_message_id=status_msg.message_id,
            target_link=link,
            accounts=accounts
        )
    )

async def run_mass_join_worker(bot: Bot, admin_chat_id: int, status_message_id: int, target_link: str, accounts: list):
    global _is_mass_join_running, _mass_join_cancelled
    total = len(accounts)
    success = 0
    already = 0
    failed = 0
    was_cancelled = False

    cancel_markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Stop / Cancel Mass Join", callback_data="cancel_mass_join", icon_custom_emoji_id=ID_PAUSED)]
    ])

    for idx, acc in enumerate(accounts, start=1):
        if _mass_join_cancelled:
            was_cancelled = True
            logger.info("Mass join stopped by admin cancellation.")
            break

        phone = acc.get("phone_number", "Unknown")
        acc_name = acc.get("account_name", phone)
        session_str = acc.get("session_string")

        if not session_str:
            failed += 1
            continue

        try:
            client = TelegramClient(StringSession(session_str), API_ID, API_HASH)
            await client.connect()
            if not await client.is_user_authorized():
                failed += 1
                await client.disconnect()
            else:
                ok, note = await join_telegram_target(client, target_link)
                await client.disconnect()
                if ok:
                    if "Already" in note:
                        already += 1
                    else:
                        success += 1
                else:
                    failed += 1
                    logger.warning(f"Mass join fail for {phone}: {note}")
        except Exception as e:
            failed += 1
            logger.error(f"Mass join error for {phone}: {e}")

        # Update progress card every 3 accounts or when finished/cancelled
        if idx % 3 == 0 or idx == total or _mass_join_cancelled:
            try:
                progress_pct = int((idx / total) * 100)
                await bot.edit_message_text(
                    chat_id=admin_chat_id,
                    message_id=status_message_id,
                    text=(
                        f"╔══════════════════════════╗\n"
                        f"  {EMOJI_ROCKET} <b>MASS JOIN IN PROGRESS ({progress_pct}%)</b>\n"
                        f"╚══════════════════════════╝\n"
                        f"┌ 🔗 <b>Target:</b> <code>{target_link}</code>\n"
                        f"├ 📱 <b>Processed:</b> <code>{idx}/{total} accounts</code>\n"
                        f"├ {EMOJI_VERIFIED} <b>New Joined:</b> <code>{success}</code>\n"
                        f"├ {EMOJI_USER} <b>Already Member:</b> <code>{already}</code>\n"
                        f"└ {EMOJI_CROSS} <b>Failed/Banned:</b> <code>{failed}</code>\n"
                        f"━━━━━━━━━━━━━━━━━━━━━\n"
                        f"👤 <i>Current: {acc_name} ({phone})</i>\n"
                        f"⏱️ <i>Waiting 10s timer gap before next account...</i>"
                    ),
                    parse_mode="HTML",
                    reply_markup=cancel_markup
                )
            except Exception:
                pass

        # 10 second timer gap between accounts (with responsive cancel checks)
        if idx < total and not _mass_join_cancelled:
            for _ in range(10):
                if _mass_join_cancelled:
                    was_cancelled = True
                    break
                await asyncio.sleep(1)

    _is_mass_join_running = False

    # Send final summary card
    status_header = f"{EMOJI_WARNING} <b>MASS JOIN STOPPED BY ADMIN</b>" if was_cancelled else f"{EMOJI_VERIFIED} <b>MASS JOIN COMPLETED!</b>"
    try:
        await bot.edit_message_text(
            chat_id=admin_chat_id,
            message_id=status_message_id,
            text=(
                f"╔══════════════════════════╗\n"
                f"  {status_header}\n"
                f"╚══════════════════════════╝\n"
                f"┌ 🔗 <b>Target:</b> <code>{target_link}</code>\n"
                f"├ 📱 <b>Total Accounts:</b> <code>{total}</code>\n"
                f"├ {EMOJI_VERIFIED} <b>Successfully Joined:</b> <code>{success}</code>\n"
                f"├ {EMOJI_USER} <b>Already Members:</b> <code>{already}</code>\n"
                f"└ {EMOJI_CROSS} <b>Failed / Inaccessible:</b> <code>{failed}</code>\n"
                f"━━━━━━━━━━━━━━━━━━━━━\n"
                f"⏱️ <i>Timer Gap: 10 seconds per account enforced</i>\n"
                f"💎 <i>Fleet execution finished.</i>"
            ),
            parse_mode="HTML",
            reply_markup=kb.get_admin_keyboard()
        )
    except Exception:
        pass
