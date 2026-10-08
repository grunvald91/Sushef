"""Журнал наблюдений: значения записываются, но не объявляются безопасными."""
from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

FIELD = re.compile(r"^(t|temp|температура|ph|pH|note|заметка)\s*=\s*(.*?)\s*$", re.I)


@dataclass(frozen=True)
class Observation:
    temperature_c: Decimal | None
    ph: Decimal | None
    note: str


def _decimal(text: str, name: str) -> Decimal:
    try:
        value = Decimal(text.strip().replace(",", "."))
    except InvalidOperation as exc:
        raise ValueError(f"Некорректное число для {name}") from exc
    if not value.is_finite():
        raise ValueError(f"Некорректное число для {name}")
    return value


def parse_observation(text: str) -> Observation:
    """Формат: t=22.5; ph=4.1; note=появились пузырьки.

    Без лишних допущений. Пробелы и запятые в числе поддерживаются,
    но единицы температур всегда °C. pH не служит гарантией безопасности.
    """
    seen: set[str] = set()
    values: dict[str, str] = {}
    parts = [p.strip() for p in text.split(";") if p.strip()]
    if not parts or len(parts) > 3:
        raise ValueError("Используйте формат t=22; ph=4.1; note=текст")
    for part in parts:
        match = FIELD.fullmatch(part)
        if not match:
            raise ValueError(f"Не понял значение: {part[:50]}")
        key, value = match.group(1).lower(), match.group(2).strip()
        key = {"temp": "t", "температура": "t", "заметка": "note"}.get(key, key)
        if key in seen:
            raise ValueError(f"Поле {key} указано дважды")
        seen.add(key)
        values[key] = value
    temperature = _decimal(values["t"], "температуры") if "t" in values else None
    ph = _decimal(values["ph"], "pH") if "ph" in values else None
    if temperature is not None and not Decimal("-30") <= temperature <= Decimal("120"):
        raise ValueError("Температура вне диапазона измерений (-30…120 °C)")
    if ph is not None and not Decimal("0") <= ph <= Decimal("14"):
        raise ValueError("pH должен быть от 0 до 14")
    note = values.get("note", "").strip()
    if not (temperature is not None or ph is not None or note):
        raise ValueError("Запишите хотя бы одну температуру, pH или наблюдение")
    if len(note) > 500:
        raise ValueError("Заметка слишком длинная")
    return Observation(temperature, ph, note)


def observation_text(row: dict) -> str:
    parts = []
    if row["temperature_c"] is not None:
        parts.append(f"{row['temperature_c']} °C")
    if row["ph"] is not None:
        parts.append(f"pH {row['ph']}")
    if row.get("note"):
        parts.append(str(row["note"]))
    return " · ".join(parts) or "Без данных"


SAFETY_REMINDER = (
    "⚠️ Записи журнала — это наблюдения, а НЕ подтверждение безопасности. "
    "Одно измерение pH или температуры не удостоверяет, что продукт можно есть. "
    "Используйте проверенные рецепты и пищевые культуры."
)
