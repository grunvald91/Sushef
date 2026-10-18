import asyncio
import logging

from aiogram import Dispatcher

from .bot import router
from .inline_mode import router as inline_router
from .chef import Chef
from .config import load_settings
from .telegram import create_bot
from .telegram_modern import configure_bot_commands
from .storage import Storage
from .timer_worker import run_timer_worker


async def main() -> None:
    settings = load_settings()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    storage = Storage(settings.database_url)
    # Schema changes are managed by Alembic, not create_all on live data.
    await storage.verify_schema_revision()
    chef = Chef(settings)
    bot = create_bot(settings)
    dp = Dispatcher()
    dp.include_router(inline_router)
    dp.include_router(router)
    timer_task = None
    try:
        # Один экземпляр polling. Для нескольких экземпляров нужен webhook + распределённая изоляция.
        await bot.delete_webhook(drop_pending_updates=False)
        await configure_bot_commands(bot)
        timer_task = asyncio.create_task(run_timer_worker(bot, storage), name="sushef-cooking-timers")
        await dp.start_polling(bot, storage=storage, chef=chef, settings=settings, tasks_concurrency_limit=20)
    finally:
        if timer_task is not None:
            timer_task.cancel()
            try:
                await timer_task
            except asyncio.CancelledError:
                pass
        await chef.close()
        await storage.close()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
