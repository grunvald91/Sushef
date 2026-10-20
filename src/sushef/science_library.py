"""Evidence-linked food microbiology reference cards.

Only the separate VerifiedProtocol catalog supports journal binding.
Research review and manufacturer enzyme pages are NOT generalized recipes.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


EvidenceType = Literal["research_review", "manufacturer_guidance", "scientific_consensus"]


@dataclass(frozen=True)
class KnowledgeCard:
    id: str
    revision: str
    title: str
    category: str
    evidence: EvidenceType
    publisher: str
    source_url: str
    reviewed_on: str
    specific_application: str
    biology_or_chemistry: str
    source_conditions: tuple[str, ...]
    required_controls: tuple[str, ...]
    warnings: tuple[str, ...]
    excluded_uses: tuple[str, ...]
    home_protocol_authorized: bool = False


CARDS: tuple[KnowledgeCard, ...] = (
    KnowledgeCard(
        id="koji-rice-risk-review",
        revision="2026.10.08-1",
        title="Рисовый кодзи: обзор опасностей и контроля",
        category="koji",
        evidence="research_review",
        publisher="Allwood et al., Journal of Food Safety (2023)",
        source_url="https://onlinelibrary.wiley.com/doi/full/10.1111/jfs.13048",
        reviewed_on="2026-10-08",
        specific_application=(
            "Научное описание производства рисового кодзи с пищевой Aspergillus oryzae; "
            "не аттестованная домашняя инструкция."
        ),
        biology_or_chemistry=(
            "Aspergillus oryzae образует амилазы и протеазы на зерновом субстрате. "
            "Возможны конкурирующая контаминация и риск Bacillus cereus и Staphylococcus aureus."
        ),
        source_conditions=(
            "В обзоре рассматривается производственная инкубация рисового кодзи "
            "около 30–40 °C в течение примерно 48 часов: это ОПИСАНИЕ "
            "контролируемой технологии, а не режим для домашней кухни.",
            "Авторы подчёркивают важность подтверждённого пищевого стартера, "
            "чистого оборудования и мониторинга температуры и влажности.",
            "Исследования поведения B. cereus при производственном контроле "
            "не доказывают безопасность небольших домашних партий.",
        ),
        required_controls=(
            "Подтверждение пищевого штамма A. oryzae и его происхождения у поставщика.",
            "Проверенный производственный SOP по сырью, санитарии, температуре, "
            "влажности, активности воды, длительности и хранению.",
            "Отдельная оценка микробиологических рисков для домашних условий.",
        ),
        warnings=(
            "Тёплый приготовленный рис без валидированного процесса — высокорисковое сырьё.",
            "Для домашних условий эта справка не разрешает запуск партии кодзи.",
            "Числа в обзоре НЕЛЬЗЯ использовать как универсальный рецепт "
            "самодельного кодзи или заменять отсутствующие дозы спор догадкой.",
            "Запах, цвет мицелия и одна температура не подтверждают безопасность.",
        ),
        excluded_uses=(
            "Культивирование случайной плесени или непищевого штамма.",
            "Перенос описанных производственных температур на сырой животный белок.",
            "Запуск домашней партии только по этой справочной карточке.",
        ),
    ),
    KnowledgeCard(
        id="scottzyme-pec5l",
        revision="2026.10.08-1",
        title="Scottzyme PEC5L: пектиназа для осветления винодельческого сырья",
        category="enzymes",
        evidence="manufacturer_guidance",
        publisher="Scott Laboratories",
        source_url="https://scottlab.com/scottzyme-pec5l-enzyme-sctzmp5",
        reviewed_on="2026-10-08",
        specific_application=(
            "Конкретный коммерческий жидкий ферментный препарат для виноделия: "
            "прессование винограда, обработка сусла/сока и вина. "
            "Не универсальная инструкция для любой еды."
        ),
        biology_or_chemistry=(
            "Пектолитический комплекс для расщепления пектинов. "
            "Внешнее внесение фермента — это ферментативная обработка, "
            "не размножение живых микроорганизмов."
        ),
        source_conditions=(
            "Производитель: виноград перед прессованием — 10–20 мл/тонну.",
            "Производитель: сок в рамках винодельческой технологии — 1,0–1,3 мл/гл.",
            "Производитель: вино — 1,3–1,6 мл/гл. "
            "Это величины только для этого препарата, этой формы и указанного сырья.",
            "Для распределения производитель предлагает примерно 10%-й "
            "раствор в прохладной воде; для вина рекомендует пробные тесты.",
            "Хранение препарата: 4 °C, плотно закрытым; следовать сроку годности упаковки.",
        ),
        required_controls=(
            "Убедиться, что препарат — подлинный Scottzyme PEC5L той же рецептуры; "
            "прочесть технический лист, инструкцию, аллергенное заявление, "
            "срок годности и пищевую допущенность.",
            "Проверить объём и природу сырья, стадию виноделия и дозирование "
            "в единицах производителя, не ложками «на глаз».",
        ),
        warnings=(
            "Числа приведены для винодельческого сырья и НЕ подходят автоматически "
            "для варенья, мяса, детского питания или любого фруктового пюре.",
            "Нельзя по названию «пектиназа» переносить дозу на иной бренд/активность.",
        ),
        excluded_uses=(
            "Прямое домашнее применение без проверки конкретной упаковки и её инструкции.",
            "Использование в чужом субстрате или при другом назначении.",
        ),
    ),
    KnowledgeCard(
        id="rapidase-clear-extreme-granular",
        revision="2026.10.08-1",
        title="Rapidase Clear Extreme (гранулы): пектиназа для винодельческого сока",
        category="enzymes",
        evidence="manufacturer_guidance",
        publisher="Scott Laboratories",
        source_url="https://scottlab.com/rapidase-clear-extreme-100-g-16257",
        reviewed_on="2026-10-08",
        specific_application=(
            "Определённая ГРАНУЛИРОВАННАЯ форма Rapidase Clear Extreme "
            "для осветления винодельческого сока после прессования; "
            "не путать с жидкой формой того же торгового наименования."
        ),
        biology_or_chemistry=(
            "Пектиназа с дополнительными активностями снижает пектиновую мутность "
            "винодельческого сока. Это внешние пищевые ферменты, не закваска."
        ),
        source_conditions=(
            "Производитель для гранул: сок теплее 12 °C — 1 г/гл.",
            "Сок при 10–12 °C — 2 г/гл; при 6–10 °C — 3 г/гл.",
            "Указанное время контакта для этой винодельческой технологии — 2–12 часов.",
            "Гранулы предварительно растворяют в десятикратном по массе "
            "количестве воды, перемешивают и вносят после прессования.",
            "Хранение гранул 4–8 °C; после разведения использовать в течение нескольких часов.",
        ),
        required_controls=(
            "Сверить, что закуплена именно гранулированная форма и действующая "
            "техническая документация производителя.",
            "Отдельно подтвердить сырьё, температурные условия, массовую дозировку, "
            "отсутствие противопоказанных компонентов и аллергенов.",
        ),
        warnings=(
             "Нельзя заменять гранулы жидкой формой Rapidase Clear Extreme: "
            "жидкая форма имеет другие дозировки в мл/гл; "
            "объединять её с граммовыми дозами гранул нельзя.",
            "Винодельческие нормы не превращаются автоматически в домашнюю "
            "норму «на литр любого сока».",
        ),
        excluded_uses=(
            "Дозирование жидкого препарата по нормам гранул.",
            "Применение к непищевым продуктам или неподтверждённому сырью.",
        ),
    ),
    KnowledgeCard(
        id="fermented-foods-vs-probiotics",
        revision="2026.10.08-1",
        title="Заквасочные культуры ≠ доказанные пробиотики",
        category="cultures",
        evidence="scientific_consensus",
        publisher="International Scientific Association for Probiotics and Prebiotics (ISAPP)",
        source_url="https://isappscience.org/topic/fermented-foods/",
        reviewed_on="2026-10-08",
        specific_application=(
            "Научное различие между технологическими пищевыми культурами, "
            "ферментированной едой, ферментативной обработкой и пробиотиками."
        ),
        biology_or_chemistry=(
            "Ферментация подразумевает желаемый рост микроорганизмов "
            "и их ферментативные преобразования. Пробиотик — конкретный "
            "охарактеризованный микроорганизм с доказанной пользой "
            "в достаточном количестве, а не любое живое брожение."
        ),
        source_conditions=(
            "Свойства закваски зависят от конкретного штамма, сырья и режима.",
            "Ферментированный продукт не обязан сохранять живые культуры после "
            "нагрева, фильтрации и хранения.",
        ),
        required_controls=(
            "Указывать штамм/состав пищевого стартера и технологическую роль.",
            "Для утверждения о пробиотическом действии нужны данные по штамму "
            "и количеству жизнеспособных клеток, а также надёжные исследования.",
        ),
        warnings=(
            "Не приписывать лечебные свойства любой «полезной бактерии».",
            "Наличие закваски не доказывает безопасность или пробиотический эффект.",
        ),
        excluded_uses=("Лечение заболеваний, необоснованные медицинские обещания.",),
    ),
    KnowledgeCard(
        id="novonesis-amylase-ag-300-l",
        revision="2026.10.08-1",
        title="Novonesis Amylase AG 300 L: амилаза для фруктового сока",
        category="enzymes",
        evidence="manufacturer_guidance",
        publisher="Novonesis",
        source_url="https://www.novonesis.com/en/biosolutions/food-and-beverages/beverages/juice-fruit-vegetables/clarification/amylase-ag-300-l",
        reviewed_on="2026-10-08",
        specific_application=(
            "Коммерческая ЖИДКАЯ амилаза именно AG 300 L для удаления крахмальной "
            "мутности при производстве соков и концентратов. Не универсальный "
            "препарат для любой ферментации или пищевого сырья."
        ),
        biology_or_chemistry=(
            "Амилаза разрушает крахмальные цепи. Это ферментативный гидролиз "
            "при внесении внешнего препарата, не микробная ферментация."
        ),
        source_conditions=(
            "По Novonesis: заявленная активность — 300 AGU/мл "
            "(единицы производителя, не переинтерпретировать).",
            "Типичная дозировка для сока 12 °Brix — 20–60 мл на 1000 л сока.",
            "В производственном контексте температура 50–55 °C, "
            "обработка в осветлительном резервуаре около 1–2 часов.",
        ),
        required_controls=(
            "Убедиться, что используется именно AG 300 L, жидкая форма, "
            "производитель, партия и соответствующий технологический лист.",
            "Проверить Brix сырья, условия процесса, содержание крахмала, "
            "аллергенный паспорт, пищевой статус препарата и инструкции по безопасности.",
        ),
        warnings=(
            "Параметры Novonesis относятся к конкретному препарату и "
            "промышленным сокам при определённой концентрации сухих веществ.",
            "Производитель предупреждает о риске сенсибилизации "
            "при вдыхании аэрозолей ферментного препарата.",
            "Не переносить мл на граммы и AGU/мл на активность другого продукта.",
        ),
        excluded_uses=(
            "Любые другие амилазы без технического паспорта.",
            "Самодельное дозирование «на стакан» или использование для "
            "ферментации риса, мяса и смешанных продуктов.",
        ),
    ),
)

_INDEX = {card.id: card for card in CARDS}


def get_knowledge(card_id: str) -> KnowledgeCard | None:
    return _INDEX.get(card_id)


def list_knowledge(category: str | None = None) -> tuple[KnowledgeCard, ...]:
    return tuple(c for c in CARDS if category is None or c.category == category)


def knowledge_text(card: KnowledgeCard) -> str:
    lines = [
        "🔬 " + card.title,
        f"Карточка: {card.id} / {card.revision}",
        f"Тип источника: {card.evidence}",
        f"Источник: {card.publisher}",
        f"Ссылка: {card.source_url}",
        "Статус: справочная карточка. Она НЕ является проверенным "
        "самостоятельным домашним протоколом.",
        "",
        "Применимость: " + card.specific_application,
        "Биология / ферменты: " + card.biology_or_chemistry,
        "",
        "Что описано в источнике:",
        *(f"• {s}" for s in card.source_conditions),
        "",
        "Что обязательно уточнить:",
        *(f"• {s}" for s in card.required_controls),
        "",
        "Ограничения и риски:",
        *(f"⚠️ {s}" for s in card.warnings),
        "",
        "Нельзя переносить:",
        *(f"• {s}" for s in card.excluded_uses),
        "",
        "⚠️ Не применяйте числа из справки как универсальные дозы/рецепт. "
        "Для продукта нужна документация на конкретную пищевую культуру "
        "или партию ферментного препарата.",
    ]
    return "\n".join(lines)


def knowledge_context(card_id: str) -> str:
    card = get_knowledge(card_id)
    if card is None:
        raise ValueError("Неизвестная справочная карточка")
    return (
        "Ты отвечаешь в РЕЖИМЕ справки по конкретному источнику. "
        "Это НЕ разрешённый к исполнению домашний протокол. "
        "Строго сохраняй область применения: "
        + knowledge_text(card)
        + "\nНе придумывай отсутствующие дозы, температуру, "
          "способы культивации, стерилизации, безопасность и полезность. "
          "В частности не превращай показатели из обзора по рисовому кодзи "
          "в домашнюю инструкцию; и не смешивай дозы жидкого и гранулированного фермента."
    )


def validate_knowledge() -> None:
    if len(_INDEX) != len(CARDS):
        raise ValueError("Повтор идентификатора научной карточки")
    for card in CARDS:
        if (not card.id or not card.revision or not card.publisher or
                not card.source_url.startswith("https://") or not card.reviewed_on or
                not card.specific_application or not card.biology_or_chemistry or
                not card.source_conditions or not card.required_controls or
                not card.warnings or not card.excluded_uses):
            raise ValueError("Неполная научная карточка: " + card.id)
        if card.home_protocol_authorized:
            raise ValueError("Справка не может объявлять домашний протокол разрешённым")


validate_knowledge()
