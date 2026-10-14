from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from typing import List, Dict

def get_dashboard_keyboard(
    msg_delay: int = 5,
    target: str = "Groups",
    schedule_enabled: int = 0
) -> InlineKeyboardMarkup:
    """
    Build the exact 2-column interactive Dashboard keyboard with only custom premium emoji icons.
    """
    sched_text = "Schedule: ON" if schedule_enabled else "Schedule: OFF"

    keyboard = [
        [
            InlineKeyboardButton(text="Add Account", callback_data="add_account", icon_custom_emoji_id="5463094762951156490"),
            InlineKeyboardButton(text="My Accounts", callback_data="my_accounts", icon_custom_emoji_id="5271801931814165886"),
        ],
        [
            InlineKeyboardButton(text="Set Ad Message", callback_data="set_ad_msg", icon_custom_emoji_id="5462950031143216831"),
            InlineKeyboardButton(text="Set Interval", callback_data="set_interval", icon_custom_emoji_id="5445083697336296498"),
        ],
        [
            InlineKeyboardButton(text=f"Msg Delay: {msg_delay}s", callback_data="set_delay", icon_custom_emoji_id="5330293807223158971"),
            InlineKeyboardButton(text=f"Target: {target}", callback_data="toggle_target", icon_custom_emoji_id="5462906239656666557"),
        ],
        [
            InlineKeyboardButton(text="Set Cycles", callback_data="set_cycles", icon_custom_emoji_id="5332648858050636426"),
            InlineKeyboardButton(text="Exclude Groups", callback_data="exclude_groups", icon_custom_emoji_id="5330312778093704176"),
        ],
        [
            InlineKeyboardButton(text="Start Ads", callback_data="start_ads", icon_custom_emoji_id="5460729485806544570"),
            InlineKeyboardButton(text="Stop Ads", callback_data="stop_ads", icon_custom_emoji_id="5463131536461144809"),
        ],
        [
            InlineKeyboardButton(text="Preview Ad", callback_data="preview_ad", icon_custom_emoji_id="5445093653070489957"),
            InlineKeyboardButton(text="Analytics", callback_data="analytics", icon_custom_emoji_id="5332290778037235887"),
        ],
        [
            InlineKeyboardButton(text="Premium", callback_data="premium", icon_custom_emoji_id="5330293807223158971"),
            InlineKeyboardButton(text="Auto Join Groups", callback_data="auto_join_groups", icon_custom_emoji_id="5472423139860293398"),
        ],
        [
            InlineKeyboardButton(text=sched_text, callback_data="schedule_ads", icon_custom_emoji_id="5332648858050636426"),
            InlineKeyboardButton(text="Delete Accounts", callback_data="delete_accounts", icon_custom_emoji_id="5231339530249845638"),
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
    
    # Verification button
    keyboard.append([InlineKeyboardButton(text="✅ Joined / Try Again", callback_data="verify_force_join")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_back_keyboard() -> InlineKeyboardMarkup:
    """Simple Back button to return to Dashboard."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Back to Dashboard", callback_data="back_to_dashboard")]
    ])


def get_interval_keyboard() -> InlineKeyboardMarkup:
    """Pre-set intervals for cycle delay."""
    keyboard = [
        [
            InlineKeyboardButton(text="⚡ 1 Min", callback_data="interval_60"),
            InlineKeyboardButton(text="⏱️ 5 Mins", callback_data="interval_300"),
        ],
        [
            InlineKeyboardButton(text="🍧 10 Mins", callback_data="interval_600"),
            InlineKeyboardButton(text="🕒 30 Mins", callback_data="interval_1800"),
        ],
        [
            InlineKeyboardButton(text="⌛ 1 Hour", callback_data="interval_3600"),
            InlineKeyboardButton(text="✏️ Custom Seconds", callback_data="interval_custom"),
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
            InlineKeyboardButton(text="⚡ 2s", callback_data="delay_2"),
            InlineKeyboardButton(text="🥂 5s (Recommended)", callback_data="delay_5"),
        ],
        [
            InlineKeyboardButton(text="⏱️ 10s", callback_data="delay_10"),
            InlineKeyboardButton(text="🛡️ 15s (Safest)", callback_data="delay_15"),
        ],
        [
            InlineKeyboardButton(text="✏️ Custom Seconds", callback_data="delay_custom"),
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
            InlineKeyboardButton(text="🌙 Unlimited (∞)", callback_data="cycles_0"),
            InlineKeyboardButton(text="🔁 5 Cycles", callback_data="cycles_5"),
        ],
        [
            InlineKeyboardButton(text="🔁 10 Cycles", callback_data="cycles_10"),
            InlineKeyboardButton(text="🔁 50 Cycles", callback_data="cycles_50"),
        ],
        [
            InlineKeyboardButton(text="✏️ Custom Number", callback_data="cycles_custom"),
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
            InlineKeyboardButton(text="📱 Login with Phone Number (OTP)", callback_data="login_phone"),
        ],
        [
            InlineKeyboardButton(text="🔑 Submit String Session", callback_data="login_session"),
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
            InlineKeyboardButton(text="⚙️ Global Settings", callback_data="admin_settings"),
            InlineKeyboardButton(text="🔙 Close Admin Panel", callback_data="admin_close")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_schedule_keyboard(schedule_enabled: int = 0) -> InlineKeyboardMarkup:
    """Schedule ads management keyboard."""
    toggle_text = "🔴 Disable Schedule" if schedule_enabled else "🟢 Enable Schedule"
    keyboard = [
        [
            InlineKeyboardButton(text=toggle_text, callback_data="schedule_toggle"),
        ],
        [
            InlineKeyboardButton(text="🕐 Set Start Time", callback_data="schedule_set_start"),
            InlineKeyboardButton(text="🕙 Set End Time", callback_data="schedule_set_end"),
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
            InlineKeyboardButton(text=f"❌ Remove: {ch.get('title', ch.get('channel_id'))}", callback_data=f"admin_del_fsub_{ch.get('channel_id')}")
        ])
    keyboard.append([InlineKeyboardButton(text="🔙 Back to Admin Panel", callback_data="admin_back")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)
