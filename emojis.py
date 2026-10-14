# Custom Premium Emojis from pack: statuspack_uz (https://t.me/addemoji/statuspack_uz)

def custom_emoji(emoji_id: str, fallback: str) -> str:
    """Format custom emoji for Telegram HTML parse mode."""
    return f'<tg-emoji emoji-id="{emoji_id}">{fallback}</tg-emoji>'

# Raw Custom Emoji IDs for inline keyboard button icon_custom_emoji_id
ID_FIRE = "5460729485806544570"        # 🔥
ID_HEART_FIRE = "5463094762951156490"  # ❤️‍🔥
ID_PLANE = "5445319572645225530"       # ✈️
ID_MSG = "5462950031143216831"         # 💬
ID_WARNING = "5463312955879727255"     # ⚠️
ID_INTERVAL = "5445083697336296498"    # 🍧
ID_DELAY = "5330293807223158971"       # 🥂
ID_TARGET = "5472423139860293398"      # 🌐
ID_MOON = "5332648858050636426"        # 🌙
ID_RUNNING = "5462906239656666557"     # 🟢
ID_PAUSED = "5463131536461144809"      # 🛑
ID_SPARKLE = "5445093653070489957"     # ✨
ID_VERIFIED = "5462919317832082236"    # ✅
ID_GIFT = "5330312778093704176"        # 🎁
ID_TRASH = "5231339530249845638"       # 🪓
ID_DIAMOND = "5332290778037235887"     # 💎
ID_STAR = "5229227046290343318"        # ⭐️
ID_FLASH = "5330293807223158971"       # ⚡
ID_MONEY = "5460978422111021593"       # 💸
ID_ROCKET = "5447483858205287105"      # 🚀
ID_USER = "5271801931814165886"        # 😎 / 👤
ID_BACK = "5463131536461144809"        # 🔙 / 🛑

# Formatted Premium Emojis (for HTML messages)
EMOJI_FIRE = custom_emoji(ID_FIRE, "🔥")
EMOJI_HEART_FIRE = custom_emoji(ID_HEART_FIRE, "❤️‍🔥")
EMOJI_PLANE = custom_emoji(ID_PLANE, "✈️")
EMOJI_MSG = custom_emoji(ID_MSG, "💬")
EMOJI_WARNING = custom_emoji(ID_WARNING, "⚠️")
EMOJI_INTERVAL = custom_emoji(ID_INTERVAL, "🍧")
EMOJI_DELAY = custom_emoji(ID_DELAY, "🥂")
EMOJI_TARGET = custom_emoji(ID_TARGET, "🌐")
EMOJI_MOON = custom_emoji(ID_MOON, "🌙")
EMOJI_RUNNING = custom_emoji(ID_RUNNING, "🟢")
EMOJI_PAUSED = custom_emoji(ID_PAUSED, "🛑")
EMOJI_SPARKLE = custom_emoji(ID_SPARKLE, "✨")
EMOJI_AI = custom_emoji(ID_SPARKLE, "✨")
EMOJI_VERIFIED = custom_emoji(ID_VERIFIED, "✅")
EMOJI_GIFT = custom_emoji(ID_GIFT, "🎁")
EMOJI_TRASH = custom_emoji(ID_TRASH, "🪓")
EMOJI_DIAMOND = custom_emoji(ID_DIAMOND, "💎")
EMOJI_STAR = custom_emoji(ID_STAR, "⭐️")
EMOJI_FLASH = custom_emoji(ID_FLASH, "⚡")
EMOJI_MONEY = custom_emoji(ID_MONEY, "💸")
EMOJI_ROCKET = custom_emoji(ID_ROCKET, "🚀")
EMOJI_COOL = custom_emoji(ID_USER, "😎")
EMOJI_USER = custom_emoji(ID_USER, "👤")
EMOJI_PHONE = custom_emoji(ID_USER, "📱")
EMOJI_BACK = custom_emoji(ID_BACK, "🔙")
EMOJI_CROSS = custom_emoji(ID_WARNING, "❌")
EMOJI_CLOCK = custom_emoji(ID_INTERVAL, "🕒")
EMOJI_STATS = custom_emoji(ID_DIAMOND, "📊")
EMOJI_PIN = custom_emoji(ID_SPARKLE, "📌")
EMOJI_GEAR = custom_emoji(ID_TARGET, "⚙️")
EMOJI_BROADCAST = custom_emoji(ID_MSG, "✉️")
EMOJI_KEY = custom_emoji(ID_STAR, "🔑")
EMOJI_LOCK = custom_emoji(ID_PAUSED, "🔒")
