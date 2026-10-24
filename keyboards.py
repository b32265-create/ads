from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from typing import List, Dict

def get_dashboard_keyboard(
    msg_delay: int = 5,
    target: str = "Groups",
    schedule_enabled: int = 0,
    manager_enabled: int = 1
) -> InlineKeyboardMarkup:
    """
    Build the 2-column interactive Dashboard keyboard with universal standard unicode emojis.
    """
    sched_text = "⏰ Schedule: ON" if schedule_enabled else "⏰ Schedule: OFF"
    mgr_text = "👔 Manager: ON" if manager_enabled else "👔 Manager: OFF"

    keyboard = [
        [
            InlineKeyboardButton(text="➕ Add Account", callback_data="add_account"),
            InlineKeyboardButton(text="📱 My Accounts", callback_data="my_accounts"),
        ],
        [
            InlineKeyboardButton(text="📝 Set Ad Message", callback_data="set_ad_msg"),
            InlineKeyboardButton(text="⏱️ Set Interval", callback_data="set_interval"),
        ],
        [
            InlineKeyboardButton(text=f"⏳ Msg Delay: {msg_delay}s", callback_data="set_delay"),
            InlineKeyboardButton(text=f"🎯 Target: {target}", callback_data="toggle_target"),
        ],
        [
            InlineKeyboardButton(text="🔄 Set Cycles", callback_data="set_cycles"),
            InlineKeyboardButton(text="🚫 Exclude Groups", callback_data="exclude_groups"),
        ],
        [
            InlineKeyboardButton(text="🚀 Start Ads", callback_data="start_ads"),
            InlineKeyboardButton(text="🛑 Stop Ads", callback_data="stop_ads"),
        ],
        [
            InlineKeyboardButton(text="👁️ Preview Ad", callback_data="preview_ad"),
            InlineKeyboardButton(text="📊 Analytics", callback_data="analytics"),
        ],
        [
            InlineKeyboardButton(text="💎 Premium (₹100)", callback_data="premium"),
            InlineKeyboardButton(text="🎁 Refer & Earn (Free VIP)", callback_data="refer_earn"),
        ],
        [
            InlineKeyboardButton(text="⚡ Auto Join Groups", callback_data="auto_join_groups"),
            InlineKeyboardButton(text="🗑️ Delete Accounts", callback_data="delete_accounts"),
        ],
        [
            InlineKeyboardButton(text=sched_text, callback_data="schedule_ads"),
            InlineKeyboardButton(text=mgr_text, callback_data="toggle_manager_account"),
        ],
        [
            InlineKeyboardButton(text="🤖 AI ASSISTANT ATO REPLY", callback_data="ai_assistant_autoreply"),
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_force_join_keyboard(channels: List[Dict]) -> InlineKeyboardMarkup:
    """Keyboard prompting user to join required channels before accessing the bot."""
    keyboard = []
    for idx, ch in enumerate(channels, 1):
        btn_text = f"📢 Join {ch.get('title', f'Channel {idx}')}"
        link = ch.get('invite_link', '')
        if not link.startswith('http'):
            link = f"https://t.me/{link.replace('@', '')}"
        keyboard.append([InlineKeyboardButton(text=btn_text, url=link)])
    
    keyboard.append([InlineKeyboardButton(text="✅ Joined / Try Again", callback_data="verify_force_join")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_back_keyboard() -> InlineKeyboardMarkup:
    """Simple Back button to return to Dashboard."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Back to Dashboard", callback_data="back_to_dashboard")]
    ])


def get_interval_keyboard() -> InlineKeyboardMarkup:
    """Pre-set intervals for cycle delay with standard emojis."""
    keyboard = [
        [
            InlineKeyboardButton(text="👑 1 Min (VIP)", callback_data="interval_60"),
            InlineKeyboardButton(text="👑 5 Mins (VIP)", callback_data="interval_300"),
        ],
        [
            InlineKeyboardButton(text="⏱️ 10 Mins", callback_data="interval_600"),
            InlineKeyboardButton(text="⏱️ 30 Mins", callback_data="interval_1800"),
        ],
        [
            InlineKeyboardButton(text="⚙️ Custom Seconds", callback_data="interval_custom"),
        ],
        [
            InlineKeyboardButton(text="🔙 Back to Dashboard", callback_data="back_to_dashboard")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_delay_keyboard() -> InlineKeyboardMarkup:
    """Pre-set delays between individual messages to prevent flood limits."""
    keyboard = [
        [
            InlineKeyboardButton(text="👑 1s (Turbo VIP)", callback_data="delay_1"),
            InlineKeyboardButton(text="⏳ 5s", callback_data="delay_5"),
        ],
        [
            InlineKeyboardButton(text="⏱️ 10s", callback_data="delay_10"),
            InlineKeyboardButton(text="🛡️ 30s", callback_data="delay_30"),
        ],
        [
            InlineKeyboardButton(text="⚙️ Custom Seconds", callback_data="delay_custom"),
        ],
        [
            InlineKeyboardButton(text="🔙 Back to Dashboard", callback_data="back_to_dashboard")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_cycles_keyboard() -> InlineKeyboardMarkup:
    """Pre-set cycles options."""
    keyboard = [
        [
            InlineKeyboardButton(text="🎯 5 Cycles", callback_data="cycles_5"),
            InlineKeyboardButton(text="🎯 10 Cycles", callback_data="cycles_10"),
        ],
        [
            InlineKeyboardButton(text="🎯 15 Cycles", callback_data="cycles_15"),
            InlineKeyboardButton(text="🎯 20 Cycles", callback_data="cycles_20"),
        ],
        [
            InlineKeyboardButton(text="⚙️ Custom Number", callback_data="cycles_custom"),
        ],
        [
            InlineKeyboardButton(text="👑 ♾️ Unlimited (∞) (VIP)", callback_data="cycles_0"),
        ],
        [
            InlineKeyboardButton(text="🔙 Back to Dashboard", callback_data="back_to_dashboard")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_add_account_keyboard() -> InlineKeyboardMarkup:
    """Choose login method for hosting a Telegram account."""
    keyboard = [
        [
            InlineKeyboardButton(text="📱 Phone Number (OTP)", callback_data="login_phone"),
        ],
        [
            InlineKeyboardButton(text="🔑 String Session", callback_data="login_session"),
        ],
        [
            InlineKeyboardButton(text="🔙 Back to Dashboard", callback_data="back_to_dashboard")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_admin_keyboard() -> InlineKeyboardMarkup:
    """Main keyboard for the Admin Control Panel."""
    keyboard = [
        [
            InlineKeyboardButton(text="📊 Bot Statistics", callback_data="admin_stats"),
            InlineKeyboardButton(text="✉️ Broadcast Message", callback_data="admin_broadcast"),
        ],
        [
            InlineKeyboardButton(text="👥 User Management", callback_data="admin_users"),
            InlineKeyboardButton(text="📢 Manage Force Join", callback_data="admin_fsub"),
        ],
        [
            InlineKeyboardButton(text="📡 Log Account Config", callback_data="admin_log_account"),
            InlineKeyboardButton(text="👔 Manager Account Config", callback_data="admin_manager_account"),
        ],
        [
            InlineKeyboardButton(text="🚀 Mass Join (All Accs)", callback_data="admin_mass_join"),
            InlineKeyboardButton(text="⚙️ Global Settings", callback_data="admin_settings"),
        ],
        [
            InlineKeyboardButton(text="❌ Close Admin Panel", callback_data="admin_close")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_schedule_keyboard(schedule_enabled: int = 0) -> InlineKeyboardMarkup:
    """Schedule ads management keyboard."""
    toggle_text = "🛑 Disable Schedule" if schedule_enabled else "🟢 Enable Schedule"
    keyboard = [
        [
            InlineKeyboardButton(text=toggle_text, callback_data="schedule_toggle"),
        ],
        [
            InlineKeyboardButton(text="🌅 Set Start Time", callback_data="schedule_set_start"),
            InlineKeyboardButton(text="🌃 Set End Time", callback_data="schedule_set_end"),
        ],
        [
            InlineKeyboardButton(text="🔙 Back to Dashboard", callback_data="back_to_dashboard")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_admin_fsub_keyboard(channels: List[Dict]) -> InlineKeyboardMarkup:
    """Force join channels management keyboard for admins."""
    keyboard = [
        [InlineKeyboardButton(text="➕ Add New Channel", callback_data="admin_add_fsub")]
    ]
    for ch in channels:
        keyboard.append([
            InlineKeyboardButton(text=f"🗑️ Remove: {ch.get('title', ch.get('channel_id'))}", callback_data=f"admin_del_fsub_{ch.get('channel_id')}")
        ])
    keyboard.append([InlineKeyboardButton(text="🔙 Back to Admin Panel", callback_data="admin_back")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_autodm_keyboard(
    enabled: bool = False,
    rate: int = 10,
    target_mode: str = "groups",
    pending_leads: int = 0
) -> InlineKeyboardMarkup:
    """Auto DM control keyboard with standard unicode emoji icons."""
    toggle_btn_text = "🛑 Stop Auto DM (5m Scan)" if enabled else "🚀 Start Auto DM (5m Scan)"
    mode_text = "👥 Target: Group 500 Msgs" if target_mode == "groups" else "📋 Target: Custom List"
    leads_text = f"📂 Saved Leads: {pending_leads} Ready" if pending_leads > 0 else "📂 Saved Leads (0)"
    
    keyboard = [
        [
            InlineKeyboardButton(text=toggle_btn_text, callback_data="toggle_autodm_active"),
        ],
        [
            InlineKeyboardButton(text="📝 Set DM Message", callback_data="set_autodm_message"),
            InlineKeyboardButton(text=f"⚡ Rate: {rate}/hr", callback_data="set_autodm_rate"),
        ],
        [
            InlineKeyboardButton(text=mode_text, callback_data="toggle_autodm_mode"),
            InlineKeyboardButton(text=leads_text, callback_data="autodm_view_leads"),
        ],
        [
            InlineKeyboardButton(text="🎯 Custom Target List", callback_data="set_autodm_targets"),
            InlineKeyboardButton(text="🔍 Keywords (Filter)", callback_data="set_autodm_keywords"),
        ],
        [
            InlineKeyboardButton(text="🤖 Set Auto-Reply", callback_data="set_autodm_autoreply"),
            InlineKeyboardButton(text="⚡ Scan & Send Now", callback_data="autodm_send_now"),
        ],
        [
            InlineKeyboardButton(text="🗑️ Reset Leads DB", callback_data="autodm_reset_leads"),
            InlineKeyboardButton(text="🔙 Back to Dashboard", callback_data="back_to_dashboard")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_autodm_rate_keyboard() -> InlineKeyboardMarkup:
    """Pre-set limits for Auto DM (Scans 500 msgs every 5 minutes)."""
    keyboard = [
        [
            InlineKeyboardButton(text="🛡️ 1 DM / 5m (~12/hr Safest)", callback_data="autodm_rate_12"),
            InlineKeyboardButton(text="⚡ 2 DMs / 5m (~24/hr Fast)", callback_data="autodm_rate_24"),
        ],
        [
            InlineKeyboardButton(text="🚀 3 DMs / 5m (~36/hr Turbo)", callback_data="autodm_rate_36"),
            InlineKeyboardButton(text="⚙️ Custom Rate / Hour", callback_data="autodm_rate_custom"),
        ],
        [
            InlineKeyboardButton(text="🔙 Back to Auto DM", callback_data="auto_dm_menu")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_autodm_back_keyboard() -> InlineKeyboardMarkup:
    """Back button returning to Auto DM menu."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Back to Auto DM", callback_data="auto_dm_menu")]
    ])
