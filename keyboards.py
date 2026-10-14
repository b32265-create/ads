from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from typing import List, Dict
from emojis import (
    ID_FIRE, ID_HEART_FIRE, ID_PLANE, ID_MSG, ID_WARNING,
    ID_INTERVAL, ID_DELAY, ID_TARGET, ID_MOON, ID_RUNNING,
    ID_PAUSED, ID_SPARKLE, ID_VERIFIED, ID_GIFT, ID_TRASH,
    ID_DIAMOND, ID_STAR, ID_FLASH, ID_MONEY, ID_ROCKET,
    ID_USER, ID_BACK
)

def get_dashboard_keyboard(
    msg_delay: int = 5,
    target: str = "Groups",
    schedule_enabled: int = 0
) -> InlineKeyboardMarkup:
    """
    Build the exact 2-column interactive Dashboard keyboard with only custom premium emoji icons.
    """
    sched_text = "Schedule: ON" if schedule_enabled else "Schedule: OFF"
    sched_icon = ID_RUNNING if schedule_enabled else ID_MOON

    keyboard = [
        [
            InlineKeyboardButton(text="Add Account", callback_data="add_account", icon_custom_emoji_id=ID_HEART_FIRE),
            InlineKeyboardButton(text="My Accounts", callback_data="my_accounts", icon_custom_emoji_id=ID_USER),
        ],
        [
            InlineKeyboardButton(text="Set Ad Message", callback_data="set_ad_msg", icon_custom_emoji_id=ID_MSG),
            InlineKeyboardButton(text="Set Interval", callback_data="set_interval", icon_custom_emoji_id=ID_INTERVAL),
        ],
        [
            InlineKeyboardButton(text=f"Msg Delay: {msg_delay}s", callback_data="set_delay", icon_custom_emoji_id=ID_DELAY),
            InlineKeyboardButton(text=f"Target: {target}", callback_data="toggle_target", icon_custom_emoji_id=ID_TARGET),
        ],
        [
            InlineKeyboardButton(text="Set Cycles", callback_data="set_cycles", icon_custom_emoji_id=ID_MOON),
            InlineKeyboardButton(text="Exclude Groups", callback_data="exclude_groups", icon_custom_emoji_id=ID_GIFT),
        ],
        [
            InlineKeyboardButton(text="Start Ads", callback_data="start_ads", icon_custom_emoji_id=ID_FIRE),
            InlineKeyboardButton(text="Stop Ads", callback_data="stop_ads", icon_custom_emoji_id=ID_PAUSED),
        ],
        [
            InlineKeyboardButton(text="Preview Ad", callback_data="preview_ad", icon_custom_emoji_id=ID_SPARKLE),
            InlineKeyboardButton(text="Analytics", callback_data="analytics", icon_custom_emoji_id=ID_DIAMOND),
        ],
        [
            InlineKeyboardButton(text="Premium", callback_data="premium", icon_custom_emoji_id=ID_DIAMOND),
            InlineKeyboardButton(text="Auto Join Groups", callback_data="auto_join_groups", icon_custom_emoji_id=ID_TARGET),
        ],
        [
            InlineKeyboardButton(text=sched_text, callback_data="schedule_ads", icon_custom_emoji_id=sched_icon),
            InlineKeyboardButton(text="Delete Accounts", callback_data="delete_accounts", icon_custom_emoji_id=ID_TRASH),
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_force_join_keyboard(channels: List[Dict]) -> InlineKeyboardMarkup:
    """Keyboard prompting user to join required channels before accessing the bot."""
    keyboard = []
    for idx, ch in enumerate(channels, 1):
        btn_text = f"Join {ch.get('title', f'Channel {idx}')}"
        link = ch.get('invite_link', '')
        if not link.startswith('http'):
            link = f"https://t.me/{link.replace('@', '')}"
        keyboard.append([InlineKeyboardButton(text=btn_text, url=link, icon_custom_emoji_id=ID_MSG)])
    
    keyboard.append([InlineKeyboardButton(text="Joined / Try Again", callback_data="verify_force_join", icon_custom_emoji_id=ID_VERIFIED)])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_back_keyboard() -> InlineKeyboardMarkup:
    """Simple Back button to return to Dashboard."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Back to Dashboard", callback_data="back_to_dashboard", icon_custom_emoji_id=ID_BACK)]
    ])


def get_interval_keyboard() -> InlineKeyboardMarkup:
    """Pre-set intervals for cycle delay with custom premium emoji icons."""
    keyboard = [
        [
            InlineKeyboardButton(text="1 Min", callback_data="interval_60", icon_custom_emoji_id=ID_FLASH),
            InlineKeyboardButton(text="5 Mins", callback_data="interval_300", icon_custom_emoji_id=ID_INTERVAL),
        ],
        [
            InlineKeyboardButton(text="10 Mins", callback_data="interval_600", icon_custom_emoji_id=ID_INTERVAL),
            InlineKeyboardButton(text="30 Mins", callback_data="interval_1800", icon_custom_emoji_id=ID_INTERVAL),
        ],
        [
            InlineKeyboardButton(text="1 Hour", callback_data="interval_3600", icon_custom_emoji_id=ID_INTERVAL),
            InlineKeyboardButton(text="Custom Seconds", callback_data="interval_custom", icon_custom_emoji_id=ID_SPARKLE),
        ],
        [
            InlineKeyboardButton(text="Back to Dashboard", callback_data="back_to_dashboard", icon_custom_emoji_id=ID_BACK)
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_delay_keyboard() -> InlineKeyboardMarkup:
    """Pre-set delays between individual messages to prevent flood limits."""
    keyboard = [
        [
            InlineKeyboardButton(text="2s", callback_data="delay_2", icon_custom_emoji_id=ID_FLASH),
            InlineKeyboardButton(text="5s (Recommended)", callback_data="delay_5", icon_custom_emoji_id=ID_DELAY),
        ],
        [
            InlineKeyboardButton(text="10s", callback_data="delay_10", icon_custom_emoji_id=ID_DELAY),
            InlineKeyboardButton(text="15s (Safest)", callback_data="delay_15", icon_custom_emoji_id=ID_RUNNING),
        ],
        [
            InlineKeyboardButton(text="Custom Seconds", callback_data="delay_custom", icon_custom_emoji_id=ID_SPARKLE),
        ],
        [
            InlineKeyboardButton(text="Back to Dashboard", callback_data="back_to_dashboard", icon_custom_emoji_id=ID_BACK)
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_cycles_keyboard() -> InlineKeyboardMarkup:
    """Pre-set cycles options."""
    keyboard = [
        [
            InlineKeyboardButton(text="Unlimited (∞)", callback_data="cycles_0", icon_custom_emoji_id=ID_MOON),
            InlineKeyboardButton(text="5 Cycles", callback_data="cycles_5", icon_custom_emoji_id=ID_TARGET),
        ],
        [
            InlineKeyboardButton(text="10 Cycles", callback_data="cycles_10", icon_custom_emoji_id=ID_TARGET),
            InlineKeyboardButton(text="50 Cycles", callback_data="cycles_50", icon_custom_emoji_id=ID_FIRE),
        ],
        [
            InlineKeyboardButton(text="Custom Number", callback_data="cycles_custom", icon_custom_emoji_id=ID_SPARKLE),
        ],
        [
            InlineKeyboardButton(text="Back to Dashboard", callback_data="back_to_dashboard", icon_custom_emoji_id=ID_BACK)
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_add_account_keyboard() -> InlineKeyboardMarkup:
    """Choose login method for hosting a Telegram account."""
    keyboard = [
        [
            InlineKeyboardButton(text="Phone Number (OTP)", callback_data="login_phone", icon_custom_emoji_id=ID_USER),
        ],
        [
            InlineKeyboardButton(text="String Session", callback_data="login_session", icon_custom_emoji_id=ID_STAR),
        ],
        [
            InlineKeyboardButton(text="Back to Dashboard", callback_data="back_to_dashboard", icon_custom_emoji_id=ID_BACK)
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_admin_keyboard() -> InlineKeyboardMarkup:
    """Main keyboard for the Admin Control Panel."""
    keyboard = [
        [
            InlineKeyboardButton(text="Bot Statistics", callback_data="admin_stats", icon_custom_emoji_id=ID_DIAMOND),
            InlineKeyboardButton(text="Broadcast Message", callback_data="admin_broadcast", icon_custom_emoji_id=ID_MSG),
        ],
        [
            InlineKeyboardButton(text="User Management", callback_data="admin_users", icon_custom_emoji_id=ID_USER),
            InlineKeyboardButton(text="Manage Force Join", callback_data="admin_fsub", icon_custom_emoji_id=ID_TARGET),
        ],
        [
            InlineKeyboardButton(text="Global Settings", callback_data="admin_settings", icon_custom_emoji_id=ID_HEART_FIRE),
            InlineKeyboardButton(text="Close Admin Panel", callback_data="admin_close", icon_custom_emoji_id=ID_BACK)
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_schedule_keyboard(schedule_enabled: int = 0) -> InlineKeyboardMarkup:
    """Schedule ads management keyboard."""
    toggle_text = "Disable Schedule" if schedule_enabled else "Enable Schedule"
    toggle_icon = ID_PAUSED if schedule_enabled else ID_RUNNING
    keyboard = [
        [
            InlineKeyboardButton(text=toggle_text, callback_data="schedule_toggle", icon_custom_emoji_id=toggle_icon),
        ],
        [
            InlineKeyboardButton(text="Set Start Time", callback_data="schedule_set_start", icon_custom_emoji_id=ID_INTERVAL),
            InlineKeyboardButton(text="Set End Time", callback_data="schedule_set_end", icon_custom_emoji_id=ID_MOON),
        ],
        [
            InlineKeyboardButton(text="Back to Dashboard", callback_data="back_to_dashboard", icon_custom_emoji_id=ID_BACK)
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_admin_fsub_keyboard(channels: List[Dict]) -> InlineKeyboardMarkup:
    """Force join channels management keyboard for admins."""
    keyboard = [
        [InlineKeyboardButton(text="Add New Channel", callback_data="admin_add_fsub", icon_custom_emoji_id=ID_HEART_FIRE)]
    ]
    for ch in channels:
        keyboard.append([
            InlineKeyboardButton(text=f"Remove: {ch.get('title', ch.get('channel_id'))}", callback_data=f"admin_del_fsub_{ch.get('channel_id')}", icon_custom_emoji_id=ID_TRASH)
        ])
    keyboard.append([InlineKeyboardButton(text="Back to Admin Panel", callback_data="admin_back", icon_custom_emoji_id=ID_BACK)])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)
