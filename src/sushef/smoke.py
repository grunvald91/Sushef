"""Minimal live service smoke check after safe Docker startup.

Uses one very short ClaudeHub reply (which may incur a small API charge).
Prints no tokens, auth headers, prompts or user data.
"""
from __future__ import annotations

import asyncio

from aiogram import Bot

from .chef import Chef
from .config import load_settings


async def main() -> None:
    settings = load_settings()
    bot = Bot(token=settings.telegram_bot_token)
    try:
        await bot.get_me()
        print("Telegram Bot API: OK")
    except Exception as exc:
        print("Telegram Bot API: FAILED (" + type(exc).__name__ + ")")
        raise SystemExit(1) from None
    finally:
        await bot.session.close()

    chef = Chef(settings)
    try:
        answer = await chef.answer(
            "ask", "Ответь одним словом: готово.", {}, []
        )
        if not answer.strip():
            raise ValueError("Empty response")
        print("ClaudeHub LLM API: OK")
    except Exception as exc:
        print("ClaudeHub LLM API: FAILED (" + type(exc).__name__ + ")")
        raise SystemExit(1) from None
    finally:
        await chef.close()


if __name__ == "__main__":
    asyncio.run(main())
