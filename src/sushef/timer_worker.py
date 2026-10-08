"""Persistent reminders dispatch inside a running Sushef bot (no GitHub Actions).

The worker polls one database and sends Telegram notifications. Restarting the
process resumes outstanding countdowns. At-least-once delivery: on rare crashes
between Telegram send and DB acknowledgement a duplicate may be delivered.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from aiogram import Bot

from .storage import Storage
from .timers import timer_alert

logger = logging.getLogger(__name__)


async def deliver_due_timers(bot: Bot, storage: Storage,
                             *, now_ts: int | None = None) -> dict[str, int]:
    """One polling iteration; explicit clock supported for deterministic tests."""
    records = await storage.claim_due_timers(now_ts=now_ts, limit=20)
    sent = failed = 0
    for record in records:
        try:
            await bot.send_message(
                chat_id=record["chat_id"], text=timer_alert(record),
            )
        except Exception as exc:
            failed += 1
            logger.warning(
                "Telegram timer %s failed (%s), retry with backoff",
                record["id"], type(exc).__name__
            )
            await storage.complete_timer_delivery(record["id"], success=False,
                                                   now_ts=now_ts)
        else:
            sent += 1
            await storage.complete_timer_delivery(record["id"], success=True,
                                                   now_ts=now_ts)
    return {"claimed": len(records), "sent": sent, "retry": failed}


async def run_timer_worker(bot: Bot, storage: Storage, interval_seconds: float = 5.0) -> None:
    if interval_seconds <= 0:
        raise ValueError("Invalid timer check interval")
    logger.info("Persistent Sushef Telegram timers enabled, interval %.1fs", interval_seconds)
    while True:
        try:
            await deliver_due_timers(bot, storage)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.exception("Unexpected cooking timer worker error: %s", type(exc).__name__)
        await asyncio.sleep(interval_seconds)
