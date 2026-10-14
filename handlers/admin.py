import logging
import asyncio
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

import database as db
import keyboards as kb
from config import ADMIN_IDS

logger = logging.getLogger(__name__)

router = Router(name="admin_router")

class AdminStates(StatesGroup):
    waiting_broadcast = State()
    waiting_fsub_id = State()
    waiting_fsub_title = State()
    waiting_fsub_link = State()
    waiting_user_search = State()
    waiting_global_setting = State()

def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS

def get_admin_panel_text() -> str:
    return (
        "❖ ━━━━ 👨‍💻 <b>ADMIN CONTROL PANEL</b> ━━━━ ❖\n\n"
        "⚡ <i>Manage users, Force Join channels, broadcast updates, and view system statistics.</i>"
    )

# --- ADMIN PANEL COMMAND ---
@router.message(Command("admin"))
async def cmd_admin(message: Message, state: FSMContext):
    await state.clear()
    if not is_admin(message.from_user.id):
        await message.answer("⛔ <i>Access Denied. You are not an admin.</i>", parse_mode="HTML")
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
        "📊 <b>BOT SYSTEM STATISTICS</b>\n\n"
        f"• 👥 <b>Total Users:</b> <code>{total_users}</code>\n"
        f"• 💎 <b>Premium Users:</b> <code>{premium_users}</code>\n"
        f"• 🚫 <b>Banned Users:</b> <code>{banned_users}</code>\n"
        f"• ✈️ <b>Hosted Accounts:</b> <code>{total_accounts}</code>\n"
        f"• 🚀 <b>Active Campaigns:</b> <code>{active_campaigns}</code>\n"
        f"• 📣 <b>Total Ads Sent (All Users):</b> <code>{global_sent}</code>\n"
        f"• 📢 <b>Force Join Channels:</b> <code>{len(fsub_channels)}</code>\n"
        f"• ⚡ <b>Engine:</b> <code>aiogram 3.x + Telethon</code>\n"
    )
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Back", callback_data="admin_back")]
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
        "✉️ <b>BROADCAST MESSAGE</b>\n\n"
        "Aap jo message sabhi bot users ko bhejna chahte hain, wo yahan send karein.\n"
        "<i>(Supports Text, Photos, Videos, Documents, Forwards)</i>"
    )
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Cancel", callback_data="admin_back")]
    ])
    await call.message.edit_text(text, parse_mode="HTML", reply_markup=markup)

@router.message(AdminStates.waiting_broadcast)
async def process_broadcast(message: Message, bot: Bot, state: FSMContext):
    if not is_admin(message.from_user.id): return

    user_ids = await db.get_all_user_ids()
    total = len(user_ids)

    status_msg = await message.answer(f"🚀 <i>Broadcasting to {total} users...</i>", parse_mode="HTML")

    sent = 0
    failed = 0

    for idx, uid in enumerate(user_ids, 1):
        try:
            await message.copy_to(chat_id=uid)
            sent += 1
            await asyncio.sleep(0.05)  # Rate limit protection
        except Exception:
            failed += 1

        if idx % 25 == 0 or idx == total:
            try:
                await status_msg.edit_text(
                    f"🚀 <b>Broadcasting in progress:</b>\n\n"
                    f"• Progress: <code>{idx}/{total}</code>\n"
                    f"• Success: <code>{sent}</code>\n"
                    f"• Failed / Blocked: <code>{failed}</code>",
                    parse_mode="HTML"
                )
            except Exception:
                pass

    await state.clear()
    await status_msg.edit_text(
        f"✅ <b>Broadcast Completed!</b>\n\n"
        f"• Total Users: <code>{total}</code>\n"
        f"• Successfully Delivered: <code>{sent}</code>\n"
        f"• Blocked / Failed: <code>{failed}</code>",
        parse_mode="HTML"
    )

# ─────────────────────────────────────────────
# USER MANAGEMENT
# ─────────────────────────────────────────────
@router.callback_query(F.data == "admin_users")
async def admin_users_menu(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id): return
    await call.answer()

    total = await db.get_user_count()
    premium = await db.get_premium_user_count()
    banned = await db.get_banned_user_count()

    text = (
        "👥 <b>USER MANAGEMENT</b>\n\n"
        f"• Total Users: <code>{total}</code>\n"
        f"• Premium Users: <code>{premium}</code>\n"
        f"• Banned Users: <code>{banned}</code>\n\n"
        "User ka <b>ID ya @username</b> enter karke usse search karein:"
    )
    await state.set_state(AdminStates.waiting_user_search)
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Back to Admin", callback_data="admin_back")]
    ])
    await call.message.edit_text(text, parse_mode="HTML", reply_markup=markup)

@router.message(AdminStates.waiting_user_search)
async def process_user_search(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id): return

    query = message.text.strip()
    user = await db.search_user_by_id_or_username(query)

    if not user:
        await message.answer(
            f"❌ User <code>{query}</code> nahi mila.\n\nDobara try karein:",
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
    joined = user.get('joined_at', 'N/A')

    acc_count, analytics = await asyncio.gather(
        db.get_account_count(uid),
        db.get_analytics(uid)
    )

    text = (
        f"👤 <b>USER PROFILE</b>\n\n"
        f"• <b>Name:</b> {fname}\n"
        f"• <b>Username:</b> {uname}\n"
        f"• <b>User ID:</b> <code>{uid}</code>\n"
        f"• <b>Joined:</b> <code>{joined}</code>\n"
        f"• <b>Status:</b> {'🚫 Banned' if is_banned else ('💎 Premium' if is_premium else '✅ Normal')}\n"
        f"• <b>Accounts:</b> <code>{acc_count}</code>\n"
        f"• <b>Total Ads Sent:</b> <code>{analytics.get('total_sent', 0)}</code>\n"
        f"• <b>Total Failed:</b> <code>{analytics.get('total_failed', 0)}</code>\n"
    )

    ban_btn_text = "✅ Unban User" if is_banned else "🚫 Ban User"
    ban_cb = f"admin_unban_{uid}" if is_banned else f"admin_ban_{uid}"
    prem_btn_text = "❌ Remove Premium" if is_premium else "💎 Grant Premium"
    prem_cb = f"admin_unpremium_{uid}" if is_premium else f"admin_premium_{uid}"

    markup = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=ban_btn_text, callback_data=ban_cb),
            InlineKeyboardButton(text=prem_btn_text, callback_data=prem_cb),
        ],
        [InlineKeyboardButton(text="🔙 Back to Admin", callback_data="admin_back")]
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
    await call.answer("🚫 User banned!", show_alert=True)
    # Notify the banned user
    try:
        await bot.send_message(uid, "🚫 <b>You have been banned from using this bot.</b>", parse_mode="HTML")
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
    await call.answer("✅ User unbanned!", show_alert=True)
    try:
        await bot.send_message(uid, "✅ <b>Your ban has been lifted. You can use the bot again!</b>", parse_mode="HTML")
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
    await call.answer("💎 Premium granted!", show_alert=True)
    try:
        await bot.send_message(
            uid,
            "🎉 <b>Congratulations! You have been granted Premium access!</b>\n\n"
            "💎 Enjoy all premium features. Use /start to continue.",
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
    await call.answer("❌ Premium removed!", show_alert=True)
    try:
        await bot.send_message(uid, "⚠️ <b>Your Premium access has been removed.</b>", parse_mode="HTML")
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
        "📢 <b>FORCE JOIN CHANNELS</b>\n\n"
        "Bot use karne se pehle users ko in channels ko join karna padega.\n"
        f"Active Channels: <b>{len(channels)}</b>\n\n"
        "Naya channel add karne ke liye 'Add New Channel' par click karein:"
    )
    await call.message.edit_text(text, parse_mode="HTML", reply_markup=kb.get_admin_fsub_keyboard(channels))

@router.callback_query(F.data == "admin_add_fsub")
async def admin_add_fsub_step1(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id): return
    await call.answer()

    await state.set_state(AdminStates.waiting_fsub_id)
    text = (
        "➕ <b>Add Force Join Channel (Step 1/3)</b>\n\n"
        "Channel ka <b>Username</b> ya <b>ID</b> enter karein:\n"
        "<i>(Example: @MyChannel ya -1001234567890)</i>\n\n"
        "⚠️ <i>Note: Make sure bot is an Admin in the channel!</i>"
    )
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Cancel", callback_data="admin_fsub")]
    ])
    await call.message.edit_text(text, parse_mode="HTML", reply_markup=markup)

@router.message(AdminStates.waiting_fsub_id)
async def admin_add_fsub_step2(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id): return
    ch_id = message.text.strip()
    await state.update_data(channel_id=ch_id)

    await state.set_state(AdminStates.waiting_fsub_title)
    await message.answer(
        "📝 <b>Enter Channel Display Title (Step 2/3):</b>\n(Example: <code>Main Updates Channel</code>)",
        parse_mode="HTML"
    )

@router.message(AdminStates.waiting_fsub_title)
async def admin_add_fsub_step3(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id): return
    title = message.text.strip()
    await state.update_data(title=title)

    await state.set_state(AdminStates.waiting_fsub_link)
    await message.answer(
        "🔗 <b>Enter Channel Invite Link (Step 3/3):</b>\n(Example: <code>https://t.me/MyChannel</code>)",
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
        f"✅ <b>Channel Added Successfully!</b>\n\n"
        f"• <b>Title:</b> {title}\n"
        f"• <b>Channel ID:</b> <code>{ch_id}</code>\n"
        f"• <b>Link:</b> {link}",
        parse_mode="HTML"
    )

@router.callback_query(F.data.startswith("admin_del_fsub_"))
async def admin_delete_fsub(call: CallbackQuery):
    if not is_admin(call.from_user.id): return
    ch_id = call.data.replace("admin_del_fsub_", "")
    await db.remove_force_channel(ch_id)
    await call.answer("✅ Channel removed from Force Join!")
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

    maintenance_text = "🔴 ON" if maintenance == "1" else "🟢 OFF"

    text = (
        "⚙️ <b>GLOBAL BOT SETTINGS</b>\n\n"
        f"• 🔧 <b>Maintenance Mode:</b> {maintenance_text}\n"
        f"• 👤 <b>Max Accounts / User:</b> <code>{max_accs}</code>\n\n"
        "Settings badalne ke liye niche buttons use karein:"
    )
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="🔧 Toggle Maintenance",
                callback_data="admin_toggle_maintenance"
            )
        ],
        [
            InlineKeyboardButton(text="👤 Set Max Accounts/User", callback_data="admin_set_max_accounts")
        ],
        [InlineKeyboardButton(text="🔙 Back to Admin", callback_data="admin_back")]
    ])
    await call.message.edit_text(text, parse_mode="HTML", reply_markup=markup)

@router.callback_query(F.data == "admin_toggle_maintenance")
async def admin_toggle_maintenance(call: CallbackQuery):
    if not is_admin(call.from_user.id): return
    current = await db.get_bot_setting("maintenance_mode", "0")
    new_val = "0" if current == "1" else "1"
    await db.set_bot_setting("maintenance_mode", new_val)
    status = "🔴 ON (Bot is now in maintenance)" if new_val == "1" else "🟢 OFF (Bot is now live)"
    await call.answer(f"Maintenance Mode: {status}", show_alert=True)
    await admin_global_settings(call)

@router.callback_query(F.data == "admin_set_max_accounts")
async def admin_set_max_accounts_prompt(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id): return
    await call.answer()
    await state.set_state(AdminStates.waiting_global_setting)
    await state.update_data(setting_key="max_accounts_per_user")
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Cancel", callback_data="admin_settings")]
    ])
    await call.message.edit_text(
        "👤 <b>Set Max Accounts Per User</b>\n\n"
        "Har user kitne accounts add kar sakta hai, wo number enter karein:\n"
        "<i>(Example: 3 ya 10)</i>",
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
            await message.answer("❌ Valid number enter karein!")
            return

    await db.set_bot_setting(key, value)
    await state.clear()
    await message.answer(f"✅ <b>Setting updated!</b>\n<code>{key}</code> = <code>{value}</code>", parse_mode="HTML")
