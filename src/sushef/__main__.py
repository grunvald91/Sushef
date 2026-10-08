import asyncio
import logging

from aiogram import Bot, Dispatcher

from .bot import router
from .chef import Chef
from .config import load_settings
from .storage import Storage


async def main() -> None:
    settings = load_settings()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    storage = Storage(settings.database_url)
    await storage.create_tables()
    chef = Chef(settings)
    bot = Bot(token=settings.telegram_bot_token)
    dp = Dispatcher()
    dp.include_router(router)
    try:
        # Один экземпляр polling. Для нескольких экземпляров нужен webhook + распределённая изоляция.
        await bot.delete_webhook(drop_pending_updates=False)
        await dp.start_polling(bot, storage=storage, chef=chef, settings=settings, tasks_concurrency_limit=20)
    finally:
        await chef.close()
        await storage.close()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
