import asyncio
import logging
import sys
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.memory import MemoryStorage

from config import BOT_TOKEN, ADMIN_IDS
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery
from typing import Callable, Dict, Any, Awaitable
import database as db
from emojis import EMOJI_WARNING
from handlers import user, account, ads_worker, admin

class MaintenanceMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        maintenance = await db.get_bot_setting("maintenance_mode", "0")
        if str(maintenance) == "1":
            user_obj = data.get("event_from_user")
            user_id = user_obj.id if user_obj else None
            if user_id and user_id not in ADMIN_IDS:
                if isinstance(event, Message):
                    await event.answer(
                        f"{EMOJI_WARNING} <b>Bot Under Maintenance</b>\n\n"
                        "Hum bot par zaroori upgrades aur optimization kar rahe hain.\n"
                        "Kripya thodi der baad dobara start karein.",
                        parse_mode="HTML"
                    )
                    return None
                elif isinstance(event, CallbackQuery):
                    await event.answer(
                        "🚧 Bot maintenance mode me hai. Please check back later.",
                        show_alert=True
                    )
                    return None
        return await handler(event, data)

# Configure UTF-8 encoding on Windows console
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
import os
from aiohttp import web

logger = logging.getLogger("ShadowAdsBot")

async def start_health_server():
    """Lightweight HTTP server for Render / Cloud health check and keepalive."""
    port_str = os.getenv("PORT")
    if not port_str:
        return None  # Running locally, no PORT set

    try:
        port = int(port_str)
        app = web.Application()

        async def health_handler(request):
            return web.Response(text="Shadow Ads Bot is alive and running!", status=200)

        app.router.add_get("/", health_handler)
        app.router.add_get("/health", health_handler)

        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "0.0.0.0", port)
        await site.start()
        logger.info(f"🌐 Cloud Health Server listening on 0.0.0.0:{port} (Render compatible)")
        return runner
    except Exception as e:
        logger.warning(f"Could not start health server on PORT {port_str}: {e}")
        return None

async def main():
    if not BOT_TOKEN:
        logger.error("❌ BOT_TOKEN is not set in .env! Please add your Telegram Bot Token in .env file.")
        print("\n" + "="*60)
        print("⚠️ ERROR: BOT_TOKEN is missing in .env file!")
        print("Please open .env and set your BOT_TOKEN from @BotFather:")
        print("BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrSTUvwxYZ")
        print("="*60 + "\n")
        return

    # 1. Initialize SQLite DB with WAL mode
    logger.info("Initializing database...")
    await db.init_db()

    # 2. Setup Bot & Dispatcher
    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    dp = Dispatcher(storage=MemoryStorage())
    dp.message.outer_middleware(MaintenanceMiddleware())
    dp.callback_query.outer_middleware(MaintenanceMiddleware())

    # 3. Include Routers
    dp.include_router(user.router)
    dp.include_router(account.router)
    dp.include_router(ads_worker.router)
    dp.include_router(admin.router)

    # 4. Fetch bot info
    bot_info = await bot.get_me()
    logger.info(f"Bot started successfully as @{bot_info.username} ({bot_info.first_name})")
    print(f"\n🚀 Bot @{bot_info.username} is running! Press Ctrl+C to stop.\n")

    # 5. Start optional Cloud Health Server (for Render / Koyeb)
    health_runner = await start_health_server()

    # 6. Initialize DM relay listeners for all hosted accounts in background
    try:
        from dm_relay import init_all_active_dm_listeners
        asyncio.create_task(init_all_active_dm_listeners(bot))
    except Exception as e:
        logger.warning(f"Could not initialize DM relay listeners: {e}")

    # 6b. Initialize official System Clients (Log Account & Manager Account)
    try:
        from system_clients import init_system_clients, stop_system_client
        asyncio.create_task(init_system_clients(bot))
    except Exception as e:
        logger.warning(f"Could not initialize system clients: {e}")

    # 7. Start Polling
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)
    finally:
        await bot.session.close()
        try:
            from system_clients import stop_system_client
            await stop_system_client("log")
            await stop_system_client("manager")
        except Exception:
            pass
        if health_runner:
            try:
                await health_runner.cleanup()
            except Exception:
                pass
        try:
            if hasattr(db, "close_pool"):
                await db.close_pool()
        except Exception:
            pass

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped by user.")
