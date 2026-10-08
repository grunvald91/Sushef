"""Source-attributed food processing procedures with strictly bounded applicability.

This catalog transcribes *selected* conditions from primary extension sources.
It does not certify food safety, substitute for the complete source, or grant
permission to interpolate recipe proportions.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

ProtocolStatus = Literal["source_documented", "reference_only"]
AssessmentStatus = Literal["STOP", "CHECK_SOURCE", "NEEDS_DATA"]


@dataclass(frozen=True)
class ProcessStage:
    code: str
    label: str
    description: str
    temperature_min_f: str | None = None
    temperature_max_f: str | None = None
    duration: str = ""


@dataclass(frozen=True)
class VerifiedProtocol:
    id: str
    revision: str
    title: str
    category: str
    status: ProtocolStatus
    publisher: str
    source_title: str
    source_url: str
    checked_on: str
    purpose: str
    ingredients: tuple[str, ...]
    stages: tuple[ProcessStage, ...]
    monitoring: tuple[str, ...]
    critical_limits: tuple[str, ...]
    stop_rules: tuple[str, ...]
    restrictions: tuple[str, ...]
    expected_changes: tuple[str, ...]
    footnote: str = ""


PROTOCOLS: tuple[VerifiedProtocol, ...] = (
    VerifiedProtocol(
        id="nchfp-sauerkraut",
        revision="2026.10.08-1",
        title="Квашеная капуста — рецептура NCHFP",
        category="vegetables",
        status="source_documented",
        publisher="National Center for Home Food Preservation (USDA/UGA)",
        source_title="Sauerkraut",
        source_url="https://nchfp.uga.edu/how/can/pickles-and-fermented-products/sauerkraut/",
        checked_on="2026-10-08",
        purpose="Молочнокислая ферментация белокочанной капусты в рассоле.",
        ingredients=(
            "На исходную партию: 25 фунтов свежей капусты и 3/4 чашки соли для консервирования/засолки.",
            "При работе порциями: на каждые 5 фунтов капусты добавлять ровно 3 столовые ложки такой соли.",
            "Только если собственный сок не покрывает капусту: кипячёный и охлаждённый рассол "
            "1,5 столовой ложки соли на 1 кварту воды (рецепт источника).",
        ),
        stages=(
            ProcessStage(
                code="prep", label="Подготовка", description=(
                    "Удалить верхние листья, промыть и подготовить капусту; "
                    "нашинковать, смешивать с солью партиями по 5 фунтов, "
                    "плотно укладывать до появления сока."
                )
            ),
            ProcessStage(
                code="ferment", label="Ферментация", description=(
                    "Поддерживать капусту под рассолом, использовать пригодную для пищи "
                    "ёмкость, груз и чистое накрытие согласно оригиналу."
                ),
                temperature_min_f="70", temperature_max_f="75",
                duration="около 3–4 недель в указанном диапазоне",
            ),
            ProcessStage(code="store", label="После ферментации", description=(
                "После завершения использовать холодильное хранение по источнику "
                "либо отдельный проверенный процесс консервирования из оригинала."
            )),
        ),
        monitoring=(
            "Проверять, остаётся ли капуста покрыта жидкостью (NCHFP: 1–2 дюйма под рассолом).",
            "Измерять температуру окружающего воздуха и документировать изменение времени.",
            "При использовании банок как груза источник рекомендует проверять 2–3 раза в неделю.",
        ),
        critical_limits=(
            "Соль и капусту измерять исходными мерками рецепта: самовольная замена/снижение соли недопустимы.",
            "Условия 70–75 °F (приблизительно 21,1–23,9 °C) соответствуют 3–4 неделям.",
        ),
        stop_rules=(
            "Если соли меньше указанного, условия/ёмкость неподходящие или нарушена санитария — "
            "не объявлять процесс контролируемым; обратиться к оригиналу.",
            "При признаках порчи, подозрительном запахе или неизвестных условиях не пробовать продукт.",
        ),
        restrictions=(
            "Не заменять соль на соль с пониженным содержанием натрия.",
            "Не переносить условия на другую овощную смесь или сырые животные продукты.",
            "Это рецепт с полными мерами NCHFP, а не автоматически рассчитанный процент соли.",
        ),
        expected_changes=(
            "Постепенное закисление и изменение структуры и аромата при работе молочнокислых бактерий.",
        ),
        footnote="Для иных температур исходная страница указывает другие сроки; "
                 "не переносите их на этот режим без обращения к первоисточнику.",
    ),
    VerifiedProtocol(
        id="nchfp-dill-pickles",
        revision="2026.10.08-1",
        title="Ферментированные огурцы с укропом — NCHFP",
        category="vegetables",
        status="source_documented",
        publisher="National Center for Home Food Preservation (USDA/UGA)",
        source_title="Dill Pickles",
        source_url="https://nchfp.uga.edu/how/ferment/recipes/dill-pickles/",
        checked_on="2026-10-08",
        purpose="Молочнокислая ферментация засолочных огурцов по рецепту NCHFP.",
        ingredients=(
            "На каждый 1 галлон вместимости ёмкости: 4 фунта небольших (4-дюймовых) огурцов для засолки.",
            "2 столовые ложки семян укропа ИЛИ 4–5 головок свежего/сухого укропа.",
            "1/2 чашки соли для консервирования/засолки; 1/4 чашки 5%-го уксуса; 8 чашек воды.",
            "Необязательно: 2 зубчика чеснока, 2 сухих красных перца, "
            "2 чайные ложки цельной смеси специй для засолки.",
        ),
        stages=(
            ProcessStage(code="prep", label="Подготовка", description=(
                "Вымыть огурцы; срезать и выбросить 1/16 дюйма со стороны цветка, "
                "оставить около 1/4 дюйма плодоножки. Уложить укроп/специи и огурцы "
                "в чистую пищевую ёмкость."
            )),
            ProcessStage(code="brine", label="Рассол", description=(
                "Растворить указанную соль в смеси воды и 5%-го уксуса; залить огурцы, "
                "установить пригодный груз и крышку по исходному документу."
            )),
            ProcessStage(code="ferment", label="Ферментация", description=(
                "Держать огурцы покрытыми рассолом, несколько раз в неделю проверять поверхность."
            ), temperature_min_f="70", temperature_max_f="75",
                duration="около 3–4 недель при 70–75 °F"),
            ProcessStage(code="store", label="После процесса", description=(
                "Следовать оригиналу для холодильного хранения или консервирования; "
                "не считать температуру ферментации инструкцией по последующему хранению."
            )),
        ),
        monitoring=(
            "Температура воздуха 70–75 °F по исходному NCHFP.",
            "Огурцы должны оставаться под рассолом (см. общий документ NCHFP об ёмкостях).",
            "Проверять состояние огурцов и поверхность несколько раз в неделю.",
        ),
        critical_limits=(
            "Уксус должен быть ровно 5%-м; вода, соль и уксус — в исходных пропорциях.",
            "Избегать температуры выше 80 °F: NCHFP предупреждает об излишнем размягчении.",
        ),
        stop_rules=(
            "Мягкие, скользкие или с неприятным запахом огурцы NCHFP рекомендует выбросить.",
            "Если концентрация рассола или кислотность уксуса неизвестны — протокол не подтверждён.",
        ),
        restrictions=(
            "Нельзя произвольно менять доли уксуса/соли/воды.",
            "Нельзя заменять ферментированный рассол просто водой.",
            "Не распространять эти параметры на иные овощи или высокорисковое сырьё.",
        ),
        expected_changes=(
            "Постепенное повышение кислотности и формирование характерного вкуса.",
        ),
    ),
    VerifiedProtocol(
        id="usu-yogurt",
        revision="2026.10.08-1",
        title="Йогурт из пастеризованного молока — USU Extension",
        category="dairy",
        status="source_documented",
        publisher="Utah State University Extension",
        source_title="Homemade Fermented Yogurt",
        source_url="https://extension.usu.edu/preserve-the-harvest/fermented-yogurt",
        checked_on="2026-10-08",
        purpose="Йогуртовая ферментация с пищевой коммерческой закваской.",
        ingredients=(
            "Для re-culturing по источнику: 1 галлон цельного молока.",
            "1 чашка предварительно активированного йогурта ИЛИ "
            "готового несладкого коммерческого йогурта с живыми культурами.",
            "По желанию для структуры: 1 и 1/3 чашки сухого обезжиренного молока.",
            "Использовать пастеризованное молоко и пищевую закваску, не сырое молоко.",
        ),
        stages=(
            ProcessStage(code="heat", label="Тепловая обработка смеси", description=(
                "В исходном рецепте смесь молока с сухим молоком нагревают до 185–200 °F, "
                "удерживают 10–20 минут при постоянном помешивании. "
                "Это шаг исходной технологии, не разрешение игнорировать качество молока."
            ), temperature_min_f="185", temperature_max_f="200",
                duration="10–20 минут"),
            ProcessStage(code="cool", label="Охлаждение и внесение закваски", description=(
                "Охладить смесь до 112–115 °F; отделить чашку для размешивания "
                "активированной закваски, объединить с основной смесью и разлить "
                "по банкам. Использовать йогуртницу согласно оригиналу."
            ), temperature_min_f="112", temperature_max_f="115"),
            ProcessStage(code="ferment", label="Инкубация", description=(
                "Выдерживать в йогуртнице по технологии USU, контролируя кислотность. "
                "Источник НЕ приводит универсальную отдельную температуру инкубации: "
                "не выдумывать её из диапазона охлаждения."
            ), duration="4–8 часов с контролем pH ≤ 4,6"),
            ProcessStage(code="chill", label="Охлаждение", description=(
                "Сразу поместить готовую партию в холодильник, как указано USU."
            )),
        ),
        monitoring=(
            "Температура смеси на этапах нагрева и охлаждения.",
            "Показание калиброванного pH-метра для достижения pH ≤ 4,6; "
            "одного измерения недостаточно для гарантии безопасности.",
            "Происхождение закваски и чистота ёмкостей; последующее охлаждение.",
        ),
        critical_limits=(
            "185–200 °F на этапе нагрева 10–20 мин по USU; охлаждение до 112–115 °F.",
            "USU указывает инкубацию 4–8 ч до достижения pH 4,6 или ниже и немедленное охлаждение.",
        ),
        stop_rules=(
            "Если неизвестна пищевая культура, молоко сырое или нарушены "
            "условия процесса — не рекомендовать употребление экспериментальной партии.",
            "Если заданная кислотность не достигнута в рамках проверенной "
            "технологии — не объявлять продукт готовым; не советовать бесконечно выдерживать.",
        ),
        restrictions=(
            "Молочные аллергены сохраняются. Не переносить режим на растительное молоко.",
            "Не приписывать штаммам культуры пробиотические лечебные свойства без доказательств.",
            "Нагрев и охлаждение — разные технологические этапы, не температура одной ферментации.",
        ),
        expected_changes=(
            "Образование молочной кислоты, загущение смеси и характерный кисломолочный вкус.",
        ),
        footnote="USU отдельно описывает активацию сухой йогуртовой культуры; "
                 "она не заменяется произвольным количеством неизвестной закваски.",
    ),
)

# Protocol topics that must not be exposed as ready-to-follow recipes without
# a product-specific, verified source. No arbitrary dose or incubation schedule.
PENDING_TOPICS: dict[str, str] = {
    "koji": "Кодзи: нужна документация на пищевую культуру, источник для сырья "
            "и контроль риска Bacillus cereus.",
    "natto": "Натто: нужна проверенная инструкция для пищевого Bacillus subtilis var. natto.",
    "enzymes": "Внешние пищевые ферменты: нужен паспорт препарата с активностью, дозой, "
               "pH, временем, температурой, сырьём и аллергенами.",
    "sourdough": "Закваска: нужен проверенный источник для конкретного изделия, "
                 "сырья и режимов выпечки/хранения.",
    "cold": "Холодная ферментация: нужна технология для конкретной культуры и субстрата.",
    "warm": "Тёплая ферментация: требуется проверенная технология для данного сырья и культуры.",
}

_INDEX = {p.id: p for p in PROTOCOLS}


def get_protocol(protocol_id: str) -> VerifiedProtocol | None:
    return _INDEX.get(protocol_id)


def list_protocols(category: str | None = None) -> tuple[VerifiedProtocol, ...]:
    return tuple(p for p in PROTOCOLS if category is None or p.category == category)


def protocol_summary(p: VerifiedProtocol) -> str:
    return (
        f"📗 {p.title}\n"
        f"Код: {p.id} · версия: {p.revision}\n"
        f"Источник: {p.publisher}\n"
        f"URL: {p.source_url}\n"
        "Статус: исходная рецептура опубликована профильной организацией; "
        "конкретная партия НЕ сертифицирована.\n"
        f"Применимость: {p.purpose}\n\n"
        "Пропорции и сырьё (без автоматического пересчёта):\n"
        + "\n".join("• " + s for s in p.ingredients)
        + "\n\nЭтапы:\n"
        + "\n".join(
            f"{i}. {s.label}: {s.description}"
            + (f" Температура {s.temperature_min_f}–{s.temperature_max_f} °F."
               if s.temperature_min_f is not None else "")
            + (f" Срок: {s.duration}." if s.duration else "")
            for i, s in enumerate(p.stages, 1)
        )
        + "\n\nКонтроль:\n" + "\n".join("• " + s for s in p.monitoring)
        + "\n\nКритические условия:\n" + "\n".join("• " + s for s in p.critical_limits)
        + "\n\nОснования остановить/пересмотреть партию:\n"
        + "\n".join("• " + s for s in p.stop_rules)
        + "\n\nЗапреты на перенос/изменения:\n"
        + "\n".join("• " + s for s in p.restrictions)
        + "\n\nОжидаемые изменения продукта (не тест на безопасность):\n"
        + "\n".join("• " + s for s in p.expected_changes)
        + ("\n\nПримечание: " + p.footnote if p.footnote else "")
        + "\n\n⚠️ Перед использованием откройте оригинальный источник полностью. "
          "Описание здесь не заменяет инструкции по упаковке, хранению и "
          "дополнительным проверкам. pH/температура сами по себе не удостоверяют съедобность."
    )


def protocol_context(protocol_id: str) -> str:
    """Source-traceable context for LLM, not a permission to extrapolate."""
    p = get_protocol(protocol_id)
    if p is None:
        raise ValueError("Неизвестный протокол")
    return (
        "Ты консультируешь ТОЛЬКО по версии фиксированного протокола:\n"
        + protocol_summary(p)
        + "\nЗАПРЕЩЕНО: изменять пропорции, придумывать температуры/время, "
          "объявлять продукт безопасным по одному показателю, заменять пищевые культуры "
          "неизвестными микробами или изобретать этап консервирования. "
          "Если пользователь хочет другой субстрат, уменьшение соли, иной фермент или "
          "условия вне протокола — скажи, что это уже ДРУГАЯ технология, "
          "попроси проверенный источник и не выдавай её за этот протокол."
    )


@dataclass(frozen=True)
class ProtocolAssessment:
    status: AssessmentStatus
    notes: tuple[str, ...]


def assess_process(
    protocol_id: str,
    stage_code: str,
    temperature_f: Decimal | None,
    *,
    recipe_unchanged: bool | None,
    signs_of_spoilage: bool | None = None,
    known_starter: bool | None = None,
    pasteurized_milk: bool | None = None,
    brine_submerged: bool | None = None,
    five_percent_vinegar: bool | None = None,
    ph: Decimal | None = None,
) -> ProtocolAssessment:
    """A red-flag assessment, NEVER a SAFE/EDIBLE clearance."""
    p = get_protocol(protocol_id)
    if not p:
        raise ValueError("Неизвестный протокол")
    stage = next((s for s in p.stages if s.code == stage_code), None)
    if stage is None:
        raise ValueError("Неизвестный этап")
    if temperature_f is not None and (not temperature_f.is_finite() or
                                       temperature_f < Decimal("-40") or
                                       temperature_f > Decimal("250")):
        raise ValueError("Некорректная температура")
    if ph is not None and (not ph.is_finite() or ph < 0 or ph > 14):
        raise ValueError("Некорректный pH")

    notes: list[str] = []
    stop = False
    if recipe_unchanged is False:
        stop = True
        notes.append("Пропорции/условия изменены: исходная проверенная рецептура больше неприменима.")
    elif recipe_unchanged is None:
        notes.append("Нет подтверждения, что состав и меры сохранены.")
    if signs_of_spoilage is True:
        stop = True
        notes.append("Есть возможные признаки порчи: продукт не пробовать; при подозрении выбросить.")
    elif signs_of_spoilage is None:
        notes.append("Неизвестно, есть ли признаки порчи.")
    if p.category == "vegetables":
        if brine_submerged is False:
            stop = True
            notes.append("Продукты вышли из рассола: режим требуется остановить/пересмотреть.")
        elif brine_submerged is None:
            notes.append("Неизвестно, остаются ли овощи под рассолом.")
    if p.id == "nchfp-dill-pickles":
        if five_percent_vinegar is False:
            stop = True
            notes.append("Уксус не 5%-й: исходная рецептура больше неприменима.")
        elif five_percent_vinegar is None:
            notes.append("Не подтверждена кислотность уксуса 5%.")
    if p.category == "dairy":
        if pasteurized_milk is False:
            stop = True
            notes.append("Использование сырого молока не соответствует этому протоколу.")
        elif pasteurized_milk is None:
            notes.append("Не подтверждено, что молоко пастеризовано.")
        if known_starter is False:
            stop = True
            notes.append("Нет подтверждённой пищевой молочной закваски.")
        if known_starter is None:
            notes.append("Не установлено происхождение молочной закваски.")
    if temperature_f is None:
        notes.append("Нет измерения температуры для указанного этапа.")
    elif stage.temperature_min_f is not None and not (
        Decimal(stage.temperature_min_f) <= temperature_f <= Decimal(stage.temperature_max_f)
    ):
        stop = True
        notes.append("Температура вне диапазона ЭТОГО этапа и протокола.")
    if ph is not None and p.id == "usu-yogurt" and stage_code == "ferment" and ph > Decimal("4.6"):
        notes.append("Целевая кислотность USU ещё не достигнута; это не подтверждение готовности.")
    status: AssessmentStatus = "STOP" if stop else "NEEDS_DATA" if notes else "CHECK_SOURCE"
    if not notes:
        notes.append("Проверка исходного рецепта и истории процесса всё ещё обязательна. "
                     "Программа никогда не подтверждает пригодность продукта.")
    return ProtocolAssessment(status, tuple(notes))


def validate_catalog() -> None:
    if len(_INDEX) != len(PROTOCOLS):
        raise ValueError("Повторный код протокола")
    for p in PROTOCOLS:
        if not (p.id and p.revision and p.source_url.startswith("https://")
                and p.publisher and p.checked_on and p.stages
                and p.ingredients and p.critical_limits and p.stop_rules
                and p.restrictions and p.expected_changes):
            raise ValueError(f"Неполная метаинформация протокола {p.id}")
        if p.status != "source_documented":
            raise ValueError(f"Нельзя выставить непроверенный рецепт как готовый: {p.id}")
        stage_codes = [s.code for s in p.stages]
        if len(stage_codes) != len(set(stage_codes)):
            raise ValueError(f"Повторный этап у {p.id}")
        for s in p.stages:
            if (s.temperature_min_f is None) != (s.temperature_max_f is None):
                raise ValueError(f"Неполный температурный диапазон: {p.id}/{s.code}")
            if s.temperature_min_f is not None and Decimal(s.temperature_min_f) > Decimal(s.temperature_max_f):
                raise ValueError(f"Перепутаны границы этапа: {p.id}/{s.code}")


validate_catalog()
