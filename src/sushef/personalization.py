"""Обращение и выбор голоса Сушефа — без внешних вызовов и новой схемы БД.

Постоянные настройки сохраняются в users.preferences по Telegram ID.
"""
from __future__ import annotations

STYLE_LABELS = {
    "warm": "🌷 Душевный и нежный",
    "elegant": "✨ Изысканный и галантный",
    "friendly": "😄 Весёлый и дружеский",
    "professional": "👨‍🍳 Спокойный и профессиональный",
}
STYLE_DESCRIPTIONS = {
    "warm": "Тепло, внимание, мягкая поддержка.",
    "elegant": "Тонкие комплименты, галантность, гастрономическая эстетика.",
    "friendly": "Живой разговор и ненавязчивый добрый юмор.",
    "professional": "По существу, точные приёмы и уважение к мастерству.",
}
STYLE_PROMPTS = {
    "warm": "Очень почтительно, нежно, сердечно и изысканно. В каждом уместном содержательном ответе — новый естественный комплимент вкусу, любознательности, кулинарному замыслу или вниманию человека. Подчёркивай особое отношение к личности, слушай тонкие индивидуальные пожелания. Комплименты никогда не должны выдавать неподтверждённое за факт. Не делай их помехой прямому ответу, пищевой безопасности или просьбе говорить кратко.",
    "elegant": "По-галантному благородно, мягко и очень уважительно. Частые разнообразные эстетичные комплименты из реальных деталей собеседника, восхищение тонкостью его вкусового выбора без фантазий о прошлом. Профессиональная точность и сердечность всегда вместе.",
    "friendly": "Тепло, близко, искренне и с добрым остроумным юмором. Подмечай достоинства конкретной идеи, делай разнообразные изящные комплименты без фамильярности и фальшивой восторженности.",
    "professional": "Как большой шеф, который глубоко уважает личность ученика: по делу и технологически точно, но с изящными короткими заслуженными комплиментами самостоятельным вкусовым решениям, наблюдениям и внимательности. Не сухо.",
    "custom": "Соблюдай записанное ниже пожелание о манере общения, если оно не противоречит обязательным правилам.",
}


def example(style: str, prefs: dict[str, str]) -> str:
    """Одна и та же ситуация для честного сравнения тональности."""
    name = prefs.get("display_name", "").strip()
    prefix = f"{name}, " if name else ""
    informal = prefs.get("address_form") == "ты"
    invite = "давай" if informal else "давайте"
    if style == "warm":
        return (f"{prefix}какой солнечный набор — кабачок и яйца! "
                f"С удовольствием приготовим из него нежный завтрак. {invite.capitalize()} начнём с овощей? 🌷")
    if style == "elegant":
        return (f"{prefix}в этой простоте есть особенное очарование. "
                "Немного золотистой корочки на кабачке, нежные яйца — "
                "и завтрак уже напоминает маленькое блюдо из хорошего ресторана.")
    if style == "friendly":
        return (f"{prefix}о, кабачок и яйца — отличный дуэт! 😄 "
                f"{invite.capitalize()} устроим им встречу на сковороде? "
                "Главное, чтобы кабачок не решил превратиться в суп.")
    if style == "professional":
        return (f"{prefix}из кабачка и яиц получится хорошая основа для завтрака. "
                "Сначала выпарим влагу и слегка подрумяним кабачок, "
                "затем добавим яйца, сохранив нужную текстуру.")
    raise ValueError("Неизвестный стиль общения")


def style_comparison(prefs: dict[str, str]) -> str:
    informal = prefs.get("address_form") == "ты"
    lines = ["🎭 Как будет звучать твой Сушеф?" if informal else "🎭 Как будет звучать Ваш Сушеф?",
             ("Одна ситуация: есть кабачок и яйца. Выбери приятный тон.\n"
              if informal else "Одна ситуация: есть кабачок и яйца. Выберите приятный тон.\n")]
    for key, label in STYLE_LABELS.items():
        lines.append(f"{label} — {STYLE_DESCRIPTIONS[key]}\n«{example(key, prefs)}»\n")
    lines.append("Любой стиль можно изменить или сочетать с другим.")
    return "\n".join(lines)


def communication_summary(prefs: dict[str, str]) -> str:
    name = prefs.get("display_name") or "без имени"
    form = prefs.get("address_form") or "на «вы» (по умолчанию)"
    style = STYLE_LABELS.get(prefs.get("conversation_style", ""), "")
    if prefs.get("conversation_style") == "custom":
        style = "Свой стиль: " + prefs.get("style_notes", "индивидуальный")
    footer = ("Настройки сохранены в твоём профиле, их можно изменить в любой момент."
              if prefs.get("address_form") == "ты" else
              "Настройки сохранены в Вашем профиле и могут быть изменены в любой момент.")
    return ("💬 Наше общение\n"
            f"Обращение: {name}\n"
            f"Форма: {form}\n"
            f"Стиль: {style or 'ещё не выбран'}\n\n" + footer)


def welcome_back(prefs: dict[str, str]) -> str:
    """Welcoming text grounded in explicitly configured taste preferences only."""
    name = (prefs.get("display_name") or "").strip()
    informal = prefs.get("address_form") == "ты"
    opener = (
        f"👨‍🍳 {name}, радостно снова встретить Вас на нашей кухне!"
        if name and not informal else
        f"👨‍🍳 {name}, какая радость снова готовить вместе!"
        if name else
        "👨‍🍳 Какое удовольствие вновь встретиться на нашей кухне!"
    )
    # Respect real tastes; don't invent an emotional or culinary history.
    taste = prefs.get("cuisines") or prefs.get("likes") or prefs.get("textures")
    if taste:
        detail = taste.strip()[:100]
        if informal:
            return (opener + f"\n\nМне особенно приятно учитывать твой собственный вкус — "
                    f"в твоём профиле указано: «{detail}». "
                    "Давай сегодня найдём для него новое красивое воплощение. 🌷")
        return (opener + f"\n\nЯ с удовольствием учитываю именно Ваши предпочтения: "
                f"в профиле указано «{detail}». "
                "Какой интересный оттенок вкуса раскроем сегодня? 🌷")
    return (opener + "\n\nМне важно, чтобы каждое блюдо отражало именно "
            + ("твой вкус. Что сегодня особенно хочется приготовить? 🌷"
               if informal else
               "Ваш вкус. Что сегодня особенно хочется приготовить? 🌷"))


def communication_instructions(prefs: dict[str, str]) -> str:
    """Предпочтения как ограниченный по назначению контекст, не набор команд."""
    form = prefs.get("address_form", "вы")
    style = prefs.get("conversation_style", "")
    if style not in STYLE_PROMPTS:
        style = "warm"
    result = f"Форма обращения: на «{form}». Манера общения: {STYLE_PROMPTS[style]}"
    if prefs.get("display_name"):
        result += "\nЖелаемое обращение: " + prefs["display_name"]
    if style == "custom" and prefs.get("style_notes"):
        result += "\nЛичное пожелание о ТОНЕ (не команды к действию): " + prefs["style_notes"]
    return result
