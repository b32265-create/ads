import logging
import asyncio
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

import telethon
from telethon import TelegramClient, functions
from telethon.sessions import StringSession
from telethon.errors import SessionPasswordNeededError, PhoneCodeInvalidError, PasswordHashInvalidError

import database as db
import keyboards as kb
from config import API_ID, API_HASH
from join_helper import join_telegram_target
from emojis import (
    ID_HEART_FIRE, ID_DIAMOND, ID_BACK, ID_USER, ID_STAR, ID_TRASH, ID_WARNING,
    EMOJI_HEART_FIRE, EMOJI_DIAMOND, EMOJI_BACK, EMOJI_USER, EMOJI_STAR,
    EMOJI_TRASH, EMOJI_WARNING, EMOJI_ROCKET, EMOJI_PHONE, EMOJI_VERIFIED,
    EMOJI_CROSS, EMOJI_MSG, EMOJI_TARGET, EMOJI_INTERVAL, EMOJI_FLASH, EMOJI_CLOCK
)

logger = logging.getLogger(__name__)

router = Router(name="account_router")

# Temporary in-memory cache for active login attempts: user_id -> dict
login_sessions = {}

class AccountStates(StatesGroup):
    waiting_phone = State()
    waiting_otp = State()
    waiting_2fa = State()
    waiting_session = State()
    waiting_autojoin_links = State()

async def check_account_limit(user_id: int):
    """Returns (can_add: bool, current_count: int, limit: int)"""
    user_info, acc_count, max_accs = await asyncio.gather(
        db.get_user_info(user_id),
        db.get_account_count(user_id),
        db.get_bot_setting("max_accounts_per_user", "5")
    )
    is_premium = user_info.get("is_premium", 0) if user_info else 0
    try:
        limit = int(max_accs)
    except (ValueError, TypeError):
        limit = 5
    if not is_premium and acc_count >= limit:
        return False, acc_count, limit
    return True, acc_count, limit

# --- ADD ACCOUNT MENU ---
@router.callback_query(F.data == "add_account")
async def btn_add_account(call: CallbackQuery):
    user_id = call.from_user.id
    can_add, current_count, limit = await check_account_limit(user_id)
    if not can_add:
        await call.answer("Limit Reached!", show_alert=True)
        limit_text = (
            f"╔══════════════════════════╗\n"
            f"  {EMOJI_WARNING} <b>ACCOUNT LIMIT REACHED</b>\n"
            f"╚══════════════════════════╝\n"
            f"Free tier me maximum <b>{limit}</b> accounts host kiye ja sakte hain.\n"
            f"Aapke account me already <b>{current_count}</b> accounts active hain.\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"🚀 <b>Upgrade to VIP Premium:</b>\n"
            f"Unlimited accounts host karne ke liye aur faster 2s message delay ke liye Premium join karein!"
        )
        prem_kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Upgrade to Premium", callback_data="premium", icon_custom_emoji_id=ID_DIAMOND)],
            [InlineKeyboardButton(text="Back to Dashboard", callback_data="back_to_dashboard", icon_custom_emoji_id=ID_BACK)]
        ])
        await call.message.edit_text(limit_text, parse_mode="HTML", reply_markup=prem_kb)
        return

    await call.answer()
    text = (
        f"╔══════════════════════════╗\n"
        f"  {EMOJI_HEART_FIRE} <b>HOST TELEGRAM ACCOUNT</b>\n"
        f"╚══════════════════════════╝\n"
        f"Apna Telegram account connect karne ke liye secure method chunein:\n\n"
        f"1️⃣ {EMOJI_PHONE} <b>Phone Number (OTP Login)</b>\n"
        f"   └ <i>Bot direct aapke Telegram app par official login OTP bhejega.</i>\n\n"
        f"2️⃣ {EMOJI_STAR} <b>String Session (Instant)</b>\n"
        f"   └ <i>Agar pehle se Telethon session string ready hai toh paste karein.</i>\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"🔒 <i>All login sessions are encrypted and stored in your private Supabase DB.</i>"
    )
    await call.message.edit_text(text, parse_mode="HTML", reply_markup=kb.get_add_account_keyboard())

# --- PHONE LOGIN FLOW ---
@router.callback_query(F.data == "login_phone")
async def start_phone_login(call: CallbackQuery, state: FSMContext):
    user_id = call.from_user.id
    can_add, current_count, limit = await check_account_limit(user_id)
    if not can_add:
        await call.answer(f"Limit reached! Free plan: max {limit} accounts.", show_alert=True)
        return

    await call.answer()
    await state.set_state(AccountStates.waiting_phone)
    text = (
        f"╔══════════════════════════╗\n"
        f"  {EMOJI_PHONE} <b>ENTER PHONE NUMBER</b>\n"
        f"╚══════════════════════════╝\n"
        f"Apna Telegram registered mobile number country code ke sath send karein:\n\n"
        f"📌 <i>Example:</i> <code>+919876543210</code> ya <code>+12025550143</code>"
    )
    await call.message.edit_text(text, parse_mode="HTML", reply_markup=kb.get_back_keyboard())

@router.message(AccountStates.waiting_phone)
async def process_phone_input(message: Message, bot: Bot, state: FSMContext):
    user_id = message.from_user.id
    can_add, current_count, limit = await check_account_limit(user_id)
    if not can_add:
        await state.clear()
        await message.answer(
            f"{EMOJI_WARNING} <b>Account limit reached!</b> Free users max {limit} accounts add kar sakte hain.",
            parse_mode="HTML",
            reply_markup=kb.get_back_keyboard()
        )
        return

    phone = message.text.strip().replace(" ", "").replace("-", "")
    if not phone.startswith("+"):
        phone = "+" + phone
        
    status_msg = await message.answer(f"{EMOJI_CLOCK} <i>Connecting to Telegram MTProto & requesting OTP...</i>", parse_mode="HTML")
    
    try:
        client = TelegramClient(StringSession(), API_ID, API_HASH)
        await client.connect()
        send_code = await client.send_code_request(phone)
        
        login_sessions[user_id] = {
            "client": client,
            "phone": phone,
            "phone_code_hash": send_code.phone_code_hash
        }
        
        await state.set_state(AccountStates.waiting_otp)
        await status_msg.edit_text(
            f"╔══════════════════════════╗\n"
            f"  {EMOJI_MSG} <b>TELEGRAM OTP SENT</b>\n"
            f"╚══════════════════════════╝\n"
            f"📱 <b>Target Phone:</b> <code>{phone}</code>\n\n"
            f"Apne Telegram app me aaya hua login code enter karein:\n"
            f"<i>(Tip: Digits ke beech space de kar bhi bhej sakte hain, e.g. <code>1 2 3 4 5</code>)</i>",
            parse_mode="HTML",
            reply_markup=kb.get_back_keyboard()
        )
    except Exception as e:
        logger.error(f"Error requesting code for {phone}: {e}")
        await status_msg.edit_text(
            f"{EMOJI_CROSS} <b>Failed to request OTP:</b>\n<code>{e}</code>\n\nPlease verify phone format and try again.",
            parse_mode="HTML",
            reply_markup=kb.get_back_keyboard()
        )
        await state.clear()

@router.message(AccountStates.waiting_otp)
async def process_otp_input(message: Message, bot: Bot, state: FSMContext):
    user_id = message.from_user.id
    code = message.text.strip().replace(" ", "").replace("-", "")
    
    session_data = login_sessions.get(user_id)
    if not session_data:
        await message.answer(f"{EMOJI_WARNING} Login session expired. Please start again.", reply_markup=kb.get_back_keyboard())
        await state.clear()
        return
        
    client: TelegramClient = session_data["client"]
    phone = session_data["phone"]
    phone_code_hash = session_data["phone_code_hash"]
    
    status_msg = await message.answer(f"{EMOJI_CLOCK} <i>Verifying OTP authorization...</i>", parse_mode="HTML")
    
    try:
        await client.sign_in(phone=phone, code=code, phone_code_hash=phone_code_hash)
        session_str = client.session.save()
        me = await client.get_me()
        acc_name = me.first_name or phone
        
        acc_id = await db.add_account(user_id, phone, session_str, acc_name)
        await client.disconnect()
        login_sessions.pop(user_id, None)
        await state.clear()
        
        try:
            from dm_relay import start_account_dm_listener
            asyncio.create_task(start_account_dm_listener({
                "id": acc_id,
                "user_id": user_id,
                "phone_number": phone,
                "session_string": session_str,
                "account_name": acc_name
            }, bot))
        except Exception:
            pass
        
        await status_msg.edit_text(
            f"╔══════════════════════════╗\n"
            f"  {EMOJI_VERIFIED} <b>ACCOUNT CONNECTED!</b> 🎉\n"
            f"╚══════════════════════════╝\n"
            f"• {EMOJI_USER} <b>Account Name:</b> {acc_name}\n"
            f"• {EMOJI_PHONE} <b>Phone / ID:</b> <code>{phone}</code>\n"
            f"• 🟢 <b>Status:</b> Hosted & Ready for Ads\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"✨ <i>Session securely stored in Supabase database.</i>",
            parse_mode="HTML",
            reply_markup=kb.get_back_keyboard()
        )
    except SessionPasswordNeededError:
        await state.set_state(AccountStates.waiting_2fa)
        await status_msg.edit_text(
            f"╔══════════════════════════╗\n"
            f"  {EMOJI_STAR} <b>2-STEP VERIFICATION (2FA)</b>\n"
            f"╚══════════════════════════╝\n"
            f"Is Telegram account par Two-Step Password set hai.\n\n"
            f"👉 Apna <b>Cloud Password</b> yahan enter karein:",
            parse_mode="HTML",
            reply_markup=kb.get_back_keyboard()
        )
    except PhoneCodeInvalidError:
        await status_msg.edit_text(
            f"{EMOJI_CROSS} <b>Invalid OTP Code!</b>\nCode galat hai, dubara check karke enter karein:",
            parse_mode="HTML",
            reply_markup=kb.get_back_keyboard()
        )
    except Exception as e:
        logger.error(f"Login error for {phone}: {e}")
        await status_msg.edit_text(
            f"{EMOJI_CROSS} <b>Login Error:</b> <code>{e}</code>",
            parse_mode="HTML",
            reply_markup=kb.get_back_keyboard()
        )
        await client.disconnect()
        login_sessions.pop(user_id, None)
        await state.clear()

@router.message(AccountStates.waiting_2fa)
async def process_2fa_input(message: Message, bot: Bot, state: FSMContext):
    user_id = message.from_user.id
    password = message.text.strip()
    
    session_data = login_sessions.get(user_id)
    if not session_data:
        await message.answer(f"{EMOJI_WARNING} Login session expired. Please restart login.", reply_markup=kb.get_back_keyboard())
        await state.clear()
        return
        
    client: TelegramClient = session_data["client"]
    phone = session_data["phone"]
    
    status_msg = await message.answer(f"{EMOJI_CLOCK} <i>Verifying 2FA cloud password...</i>", parse_mode="HTML")
    
    try:
        await client.sign_in(password=password)
        session_str = client.session.save()
        me = await client.get_me()
        acc_name = me.first_name or phone
        
        acc_id = await db.add_account(user_id, phone, session_str, acc_name)
        await client.disconnect()
        login_sessions.pop(user_id, None)
        await state.clear()
        
        try:
            from dm_relay import start_account_dm_listener
            asyncio.create_task(start_account_dm_listener({
                "id": acc_id,
                "user_id": user_id,
                "phone_number": phone,
                "session_string": session_str,
                "account_name": acc_name
            }, bot))
        except Exception:
            pass
        
        await status_msg.edit_text(
            f"╔══════════════════════════╗\n"
            f"  {EMOJI_VERIFIED} <b>2FA VERIFIED & HOSTED!</b> 🎉\n"
            f"╚══════════════════════════╝\n"
            f"• {EMOJI_USER} <b>Account:</b> {acc_name}\n"
            f"• {EMOJI_PHONE} <b>Phone:</b> <code>{phone}</code>\n"
            f"• 🟢 <b>Status:</b> Ready for advertising",
            parse_mode="HTML",
            reply_markup=kb.get_back_keyboard()
        )
    except PasswordHashInvalidError:
        await status_msg.edit_text(f"{EMOJI_CROSS} <b>Incorrect 2FA password!</b> Dobara password enter karein:", parse_mode="HTML")
    except Exception as e:
        logger.error(f"2FA Error: {e}")
        await status_msg.edit_text(f"{EMOJI_CROSS} <b>Login Failed:</b> <code>{e}</code>", parse_mode="HTML", reply_markup=kb.get_back_keyboard())
        await client.disconnect()
        login_sessions.pop(user_id, None)
        await state.clear()

# --- STRING SESSION FLOW ---
@router.callback_query(F.data == "login_session")
async def start_session_login(call: CallbackQuery, state: FSMContext):
    user_id = call.from_user.id
    can_add, current_count, limit = await check_account_limit(user_id)
    if not can_add:
        await call.answer(f"Limit reached! Free plan: max {limit} accounts.", show_alert=True)
        return

    await call.answer()
    await state.set_state(AccountStates.waiting_session)
    text = (
        f"╔══════════════════════════╗\n"
        f"  {EMOJI_STAR} <b>SUBMIT STRING SESSION</b>\n"
        f"╚══════════════════════════╝\n"
        f"Apna Telethon String Session yahan direct paste karein:\n\n"
        f"<i>(Format: 1BAA... string code)</i>"
    )
    await call.message.edit_text(text, parse_mode="HTML", reply_markup=kb.get_back_keyboard())

@router.message(AccountStates.waiting_session)
async def process_session_string(message: Message, bot: Bot, state: FSMContext):
    user_id = message.from_user.id
    can_add, current_count, limit = await check_account_limit(user_id)
    if not can_add:
        await state.clear()
        await message.answer(
            f"{EMOJI_WARNING} <b>Account limit reached!</b> Free users max {limit} accounts add kar sakte hain.",
            parse_mode="HTML",
            reply_markup=kb.get_back_keyboard()
        )
        return

    session_str = message.text.strip()
    status_msg = await message.answer(f"{EMOJI_CLOCK} <i>Validating string session credentials...</i>", parse_mode="HTML")
    
    try:
        client = TelegramClient(StringSession(session_str), API_ID, API_HASH)
        await client.connect()
        if not await client.is_user_authorized():
            await status_msg.edit_text(f"{EMOJI_CROSS} <b>Invalid or expired String Session!</b>", parse_mode="HTML", reply_markup=kb.get_back_keyboard())
            await client.disconnect()
            return
            
        me = await client.get_me()
        phone = me.phone or f"ID_{me.id}"
        acc_name = me.first_name or phone
        
        acc_id = await db.add_account(user_id, phone, session_str, acc_name)
        await client.disconnect()
        await state.clear()
        
        try:
            from dm_relay import start_account_dm_listener
            asyncio.create_task(start_account_dm_listener({
                "id": acc_id,
                "user_id": user_id,
                "phone_number": phone,
                "session_string": session_str,
                "account_name": acc_name
            }, bot))
        except Exception:
            pass
        
        await status_msg.edit_text(
            f"╔══════════════════════════╗\n"
            f"  {EMOJI_VERIFIED} <b>SESSION HOSTED SUCCESSFULLY!</b> 🎉\n"
            f"╚══════════════════════════╝\n"
            f"• {EMOJI_USER} <b>Account:</b> {acc_name}\n"
            f"• {EMOJI_PHONE} <b>Identifier:</b> <code>{phone}</code>\n"
            f"• 🟢 <b>Status:</b> Ready for Campaigns",
            parse_mode="HTML",
            reply_markup=kb.get_back_keyboard()
        )
    except Exception as e:
        logger.error(f"Session error: {e}")
        await status_msg.edit_text(f"{EMOJI_CROSS} <b>Error:</b> <code>{e}</code>", parse_mode="HTML", reply_markup=kb.get_back_keyboard())

# --- MY ACCOUNTS LIST ---
@router.callback_query(F.data == "my_accounts")
async def btn_my_accounts(call: CallbackQuery):
    await call.answer()
    user_id = call.from_user.id
    accounts = await db.get_user_accounts(user_id)
    
    if not accounts:
        text = (
            f"╔══════════════════════════╗\n"
            f"  {EMOJI_USER} <b>HOSTED ACCOUNTS (0)</b>\n"
            f"╚══════════════════════════╝\n"
            f"{EMOJI_CROSS} <i>Aapne abhi tak koi Telegram account add nahi kiya hai.</i>\n\n"
            f"Niche <b>Add Account</b> par click karke apna pehla account connect karein."
        )
        markup = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Add Account", callback_data="add_account", icon_custom_emoji_id=ID_HEART_FIRE)],
            [InlineKeyboardButton(text="Back to Dashboard", callback_data="back_to_dashboard", icon_custom_emoji_id=ID_BACK)]
        ])
        await call.message.edit_text(text, parse_mode="HTML", reply_markup=markup)
        return
        
    text = (
        f"╔══════════════════════════╗\n"
        f"  {EMOJI_USER} <b>HOSTED ACCOUNTS ({len(accounts)})</b>\n"
        f"╚══════════════════════════╝\n"
    )
    keyboard = []
    for idx, acc in enumerate(accounts, 1):
        status_tag = f"[{EMOJI_CROSS} Banned]" if acc.get("is_banned") else f"[{EMOJI_VERIFIED} Active]"
        text += (
            f"<b>{idx}. {acc.get('account_name', 'Telegram')}</b> {status_tag}\n"
            f"   ├ 📱 <code>{acc.get('phone_number')}</code>\n"
            f"   └ 🚀 Dispatched: <code>{acc.get('total_sent', 0)}</code> ads\n\n"
        )
        keyboard.append([
            InlineKeyboardButton(text=f"Remove {acc.get('phone_number')}", callback_data=f"del_acc_{acc['id']}", icon_custom_emoji_id=ID_TRASH)
        ])
        
    text += f"━━━━━━━━━━━━━━━━━━━━━\n💡 <i>Kisi account ko unlink karne ke liye niche buttons use karein:</i>"
    keyboard.append([InlineKeyboardButton(text="Add Another Account", callback_data="add_account", icon_custom_emoji_id=ID_HEART_FIRE)])
    keyboard.append([InlineKeyboardButton(text="Back to Dashboard", callback_data="back_to_dashboard", icon_custom_emoji_id=ID_BACK)])
    
    await call.message.edit_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard))

# --- DELETE ACCOUNTS ---
@router.callback_query(F.data == "delete_accounts")
async def btn_delete_accounts_menu(call: CallbackQuery):
    await call.answer()
    user_id = call.from_user.id
    accounts = await db.get_user_accounts(user_id)
    
    if not accounts:
        await call.answer("Aapke paas koi account nahi hai!", show_alert=True)
        return
        
    keyboard = [
        [InlineKeyboardButton(text="Delete ALL My Accounts", callback_data="confirm_delete_all_accs", icon_custom_emoji_id=ID_WARNING)],
        [InlineKeyboardButton(text="Back to Dashboard", callback_data="back_to_dashboard", icon_custom_emoji_id=ID_BACK)]
    ]
    await call.message.edit_text(
        f"╔══════════════════════════╗\n"
        f"  {EMOJI_TRASH} <b>UNLINK ALL ACCOUNTS</b>\n"
        f"╚══════════════════════════╝\n"
        f"⚠️ <b>Warning:</b> Kya aap sach me apne sabhi <b>{len(accounts)}</b> hosted accounts ko remove karna chahte hain?\n\n"
        f"<i>Sessions Supabase database se permanently delete ho jayenge.</i>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard)
    )

@router.callback_query(F.data == "confirm_delete_all_accs")
async def confirm_delete_all(call: CallbackQuery):
    user_id = call.from_user.id
    await db.delete_all_user_accounts(user_id)
    await call.answer("All accounts removed!", show_alert=True)
    await call.message.edit_text(
        f"{EMOJI_VERIFIED} <b>Aapke sabhi accounts successfully delete kar diye gaye hain.</b>",
        parse_mode="HTML",
        reply_markup=kb.get_back_keyboard()
    )

@router.callback_query(F.data.startswith("del_acc_"))
async def delete_single_account(call: CallbackQuery):
    acc_id = int(call.data.replace("del_acc_", ""))
    user_id = call.from_user.id
    await db.delete_account_by_id(acc_id, user_id)
    await call.answer("Account removed!")
    await btn_my_accounts(call)

# --- AUTO JOIN GROUPS (PUBLIC & PRIVATE) ---
@router.callback_query(F.data == "auto_join_groups")
async def btn_auto_join(call: CallbackQuery, state: FSMContext):
    await call.answer()
    user_id = call.from_user.id
    accounts = await db.get_user_accounts(user_id)
    if not accounts:
        await call.answer("Pehle Telegram account add karein!", show_alert=True)
        return
        
    text = (
        f"╔══════════════════════════╗\n"
        f"  {EMOJI_TARGET} <b>AUTO JOIN GROUPS & CHANNELS</b>\n"
        f"╚══════════════════════════╝\n"
        f"Apne sabhi <b>{len(accounts)}</b> accounts se naye Public ya Private groups join karne ke liye unke links enter karein:\n\n"
        f"• <b>Public:</b> <code>@groupname</code> ya <code>https://t.me/groupname</code>\n"
        f"• <b>Private Invite:</b> <code>https://t.me/+inviteHash</code> ya <code>https://t.me/joinchat/...</code>\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"<i>(Har link ko nayi line me paste karein)</i>:"
    )
    await state.set_state(AccountStates.waiting_autojoin_links)
    await call.message.edit_text(text, parse_mode="HTML", reply_markup=kb.get_back_keyboard())

@router.message(AccountStates.waiting_autojoin_links)
async def process_autojoin_links(message: Message, bot: Bot, state: FSMContext):
    user_id = message.from_user.id
    links = [line.strip() for line in message.text.split("\n") if line.strip()]
    if not links:
        await message.answer(f"{EMOJI_CROSS} Koi valid link nahi mili.", reply_markup=kb.get_back_keyboard())
        return
        
    accounts = await db.get_user_accounts(user_id)
    if not accounts:
        await message.answer(f"{EMOJI_CROSS} Koi active account nahi mila.", reply_markup=kb.get_back_keyboard())
        return

    status_msg = await message.answer(
        f"{EMOJI_CLOCK} <i>Joining {len(links)} links across {len(accounts)} accounts with anti-flood delay...</i>", 
        parse_mode="HTML"
    )
    
    success_count = 0
    already_count = 0
    fail_count = 0
    
    for acc in accounts:
        try:
            client = TelegramClient(StringSession(acc["session_string"]), API_ID, API_HASH)
            await client.connect()
            if not await client.is_user_authorized():
                await client.disconnect()
                continue

            for link in links:
                try:
                    ok, note = await join_telegram_target(client, link)
                    if ok:
                        if "Already" in note:
                            already_count += 1
                        else:
                            success_count += 1
                    else:
                        fail_count += 1
                    await asyncio.sleep(2)
                except Exception:
                    fail_count += 1
            await client.disconnect()
        except Exception:
            pass
            
    await state.clear()
    await status_msg.edit_text(
        f"╔══════════════════════════╗\n"
        f"  {EMOJI_VERIFIED} <b>AUTO JOIN BATCH COMPLETED!</b>\n"
        f"╚══════════════════════════╝\n"
        f"┌ {EMOJI_VERIFIED} <b>Successfully Joined:</b> <code>{success_count}</code>\n"
        f"├ {EMOJI_USER} <b>Already Member:</b> <code>{already_count}</code>\n"
        f"└ {EMOJI_CROSS} <b>Skipped / Failed:</b> <code>{fail_count}</code>\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"Naye groups aapke target chat pool me shamil ho chuke hain.",
        parse_mode="HTML",
        reply_markup=kb.get_back_keyboard()
    )
