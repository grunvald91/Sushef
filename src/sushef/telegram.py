"""Telegram client with an optional deployment-specific proxy."""
from aiogram import Bot
from aiogram.client.session.aiohttp import AiohttpSession

from .config import Settings


def create_bot(settings: Settings) -> Bot:
    session = AiohttpSession(proxy=settings.telegram_proxy_url or None)
    return Bot(token=settings.telegram_bot_token, session=session)
