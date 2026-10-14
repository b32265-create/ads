"""
Shadow Ads Bot - Dynamic Personalized Welcome Banner Generator
==============================================================
Composites user's Telegram profile avatar inside the glowing cyber ring
and personalizes the pill badge with the user's Telegram handle.
"""
import os
import io
import logging
from PIL import Image, ImageDraw, ImageFont, ImageOps

logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BANNER_TEMPLATE_PATH = os.path.join(BASE_DIR, "assets", "banner_template.png")
FONT_PATH = os.path.join(BASE_DIR, "assets", "font.ttf")
CACHE_DIR = os.path.join(BASE_DIR, "assets", "user_banners")

os.makedirs(CACHE_DIR, exist_ok=True)


def generate_user_welcome_banner(
    user_id: int,
    username: str = "",
    first_name: str = "",
    avatar_bytes: bytes = None
) -> str:
    """
    Generates a personalized high-resolution welcome banner for the user.
    Returns the file path of the generated image.
    """
    out_path = os.path.join(CACHE_DIR, f"banner_{user_id}.png")

    try:
        if not os.path.exists(BANNER_TEMPLATE_PATH):
            logger.warning(f"Banner template not found at {BANNER_TEMPLATE_PATH}")
            return ""

        base = Image.open(BANNER_TEMPLATE_PATH).convert("RGBA")
        target_size = (216, 216)

        # 1. Avatar or Monogram
        if avatar_bytes:
            try:
                avatar = Image.open(io.BytesIO(avatar_bytes)).convert("RGBA")
                avatar = ImageOps.fit(avatar, target_size, method=Image.Resampling.LANCZOS)
            except Exception as e:
                logger.warning(f"Avatar processing error: {e}")
                avatar = None
        else:
            avatar = None

        if not avatar:
            # Generate sleek dark initials badge
            avatar = Image.new("RGBA", target_size, (16, 18, 24, 255))
            draw_av = ImageDraw.Draw(avatar)
            draw_av.ellipse((4, 4, 212, 212), outline=(60, 65, 80), width=4)
            try:
                av_font = ImageFont.truetype(FONT_PATH, 76)
            except Exception:
                av_font = ImageFont.load_default()
            initial = (first_name[:2] if first_name else "TG").upper()
            bbox = draw_av.textbbox((0, 0), initial, font=av_font)
            tx = (216 - (bbox[2] - bbox[0])) // 2
            ty = (216 - (bbox[3] - bbox[1])) // 2 - 5
            draw_av.text((tx, ty), initial, fill=(255, 255, 255), font=av_font)

        # 2. Smooth circular alpha mask
        mask = Image.new("L", target_size, 0)
        mask_draw = ImageDraw.Draw(mask)
        mask_draw.ellipse((0, 0, target_size[0], target_size[1]), fill=255)

        # 3. Paste into glowing ring (Center cx=222, cy=202)
        cx, cy = 222, 202
        paste_x = cx - target_size[0] // 2
        paste_y = cy - target_size[1] // 2
        base.paste(avatar, (paste_x, paste_y), mask)

        # 4. Draw user's username inside pill badge
        draw = ImageDraw.Draw(base)
        draw.rounded_rectangle((474, 283, 630, 329), radius=10, fill=(0, 0, 0, 255))

        display_user = f"@{username}" if username else f"{first_name[:12]}"
        font_size = 22
        if len(display_user) > 13:
            font_size = 19
        if len(display_user) > 16:
            font_size = 16

        try:
            user_font = ImageFont.truetype(FONT_PATH, font_size)
            credit_font = ImageFont.truetype(FONT_PATH, 13)
        except Exception:
            user_font = ImageFont.load_default()
            credit_font = ImageFont.load_default()

        draw.text((485, 292), display_user, fill=(255, 255, 255), font=user_font)

        # 5. Powered by watermark
        draw.text((680, 375), "POWERED BY @SHADOW_SELLER07", fill=(150, 150, 150), font=credit_font)

        # Save optimized PNG
        base.save(out_path, "PNG", optimize=True)
        return out_path

    except Exception as e:
        logger.error(f"Error generating welcome banner: {e}")
        return BANNER_TEMPLATE_PATH
