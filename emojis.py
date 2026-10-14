# Custom Premium Emojis from pack: statuspack_uz (https://t.me/addemoji/statuspack_uz)

def custom_emoji(emoji_id: str, fallback: str) -> str:
    """Format custom emoji for Telegram HTML parse mode."""
    return f'<tg-emoji emoji-id="{emoji_id}">{fallback}</tg-emoji>'

# Premium Emoji definitions from statuspack_uz
EMOJI_FIRE = custom_emoji("5460729485806544570", "🔥")
EMOJI_HEART_FIRE = custom_emoji("5463094762951156490", "❤️‍🔥")
EMOJI_PLANE = custom_emoji("5445319572645225530", "✈️")
EMOJI_MSG = custom_emoji("5462950031143216831", "💬")
EMOJI_WARNING = custom_emoji("5463312955879727255", "⚠️")
EMOJI_INTERVAL = custom_emoji("5445083697336296498", "🍧")
EMOJI_DELAY = custom_emoji("5330293807223158971", "🥂")
EMOJI_TARGET = custom_emoji("5472423139860293398", "🌐")
EMOJI_MOON = custom_emoji("5332648858050636426", "🌙")
EMOJI_RUNNING = custom_emoji("5462906239656666557", "🟢")
EMOJI_PAUSED = custom_emoji("5463131536461144809", "🛑")
EMOJI_AI = custom_emoji("5445093653070489957", "✨")
EMOJI_VERIFIED = custom_emoji("5462919317832082236", "✅")
EMOJI_GIFT = custom_emoji("5330312778093704176", "🎁")
EMOJI_TRASH = custom_emoji("5231339530249845638", "🪓")
EMOJI_DIAMOND = custom_emoji("5332290778037235887", "💎")
EMOJI_STAR = custom_emoji("5229227046290343318", "⭐️")
EMOJI_FLASH = custom_emoji("5330293807223158971", "⚡")
EMOJI_MONEY = custom_emoji("5460978422111021593", "💸")
EMOJI_ROCKET = custom_emoji("5447483858205287105", "🚀")
EMOJI_COOL = custom_emoji("5271801931814165886", "😎")
