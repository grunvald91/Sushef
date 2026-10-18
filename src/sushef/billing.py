"""Платный доступ к ИИ в Telegram Stars (XTR): тексты и проверка счёта."""
from __future__ import annotations

from datetime import datetime, timezone

STARS_CURRENCY = "XTR"
PAYLOAD_PREFIX = "sushef_sub"


def invoice_payload(user_id: int, days: int) -> str:
    return f"{PAYLOAD_PREFIX}:{days}:{user_id}"


def parse_payload(payload: str) -> tuple[int, int] | None:
    """(days, user_id) из payload счёта или None для чужого/повреждённого счёта."""
    parts = (payload or "").split(":")
    if len(parts) != 3 or parts[0] != PAYLOAD_PREFIX:
        return None
    if not (parts[1].isdecimal() and parts[2].isdecimal()):
        return None
    return int(parts[1]), int(parts[2])


def checkout_error(payload: str, currency: str, total: int, *, user_id: int,
                   price: int, days: int) -> str | None:
    """Причина отказа в pre_checkout или None, если счёт актуален."""
    parsed = parse_payload(payload)
    if parsed is None or parsed[1] != user_id:
        return "Счёт выставлен для другого аккаунта. Откройте /subscribe ещё раз."
    if currency != STARS_CURRENCY or total != price or parsed[0] != days:
        return "Цена или срок изменились. Откройте /subscribe и оплатите новый счёт."
    return None


def format_until(ts: int) -> str:
    return datetime.fromtimestamp(ts, timezone.utc).strftime("%d.%m.%Y %H:%M UTC")


def subscription_text(sub: dict[str, int], *, price: int, days: int, trial_limit: int,
                      exempt: bool, payments_enabled: bool, now_ts: int) -> str:
    head = "⭐ **Подписка Сушефа**\n\n"
    if not payments_enabled:
        return head + "Сейчас все возможности открыты бесплатно. Приятного творчества! 🍲"
    if exempt:
        return head + "Для Вас доступ открыт без оплаты. Готовим с удовольствием! 💛"
    if sub["paid_until_ts"] > now_ts:
        status = "✅ Подписка активна до " + format_until(sub["paid_until_ts"]) + "."
    else:
        left = max(0, trial_limit - sub["trial_used"])
        status = (f"🎁 Осталось бесплатных запросов к шефу: {left} из {trial_limit}."
                  if left else "Бесплатные запросы закончились.")
    return (head + status + "\n\n"
            f"Подписка на {days} дней — **{price} ⭐** (Telegram Stars). "
            "Она открывает рецепты, ответы шефа, спасение блюд и меню на неделю. "
            "Оплата повторной подписки продлевает срок, а не сгорает.\n\n"
            "Продукты, рецепты, таймеры, инструкция и служба поддержки всегда бесплатны. "
            "Вопрос об оплате или возврате — /paysupport.")


def paywall_text(*, price: int, days: int, trial_limit: int) -> str:
    return ("⭐ Бесплатные запросы к шефу закончились"
            + (f" (было {trial_limit})" if trial_limit else "") + ".\n\n"
            f"Оформите подписку на {days} дней за **{price} ⭐** — и продолжим готовить "
            "вместе: рецепты, ответы, спасение блюд и меню на неделю.\n"
            "Сохранённые рецепты, продукты и таймеры доступны и без подписки.")
