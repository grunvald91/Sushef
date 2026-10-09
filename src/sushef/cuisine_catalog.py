"""Краткие, самостоятельно изложенные карточки кулинарных первоисточников.

Это не копия книг или сайтов. 'quantified' означает: источник приводит
количества продуктов, но не даёт права считать любое изменение проверенным.
'reference' — источник подтверждает состав и приём, но не точные пропорции.
Дата ручной сверки: 2026-10-09. Не загружает внешние URL во время работы.
"""
from __future__ import annotations

from urllib.parse import urlparse

CUISINES = {
    "spanish": ("🇪🇸 Испанская", "mediterranean", "овощи, оливковое масло, рис, холодные супы"),
    "italian": ("🇮🇹 Итальянская", "mediterranean", "травы, сыры, паста, оливковое масло"),
    "greek": ("🇬🇷 Греческая", "mediterranean", "овощи, фета, оливки, орегано"),
    "turkish": ("🇹🇷 Турецкая", "eastern_mediterranean", "яйца, овощи, йогурт, пряности"),
    "japanese": ("🇯🇵 Японская", "east_asian", "рис, даси, мисо, сезонные овощи"),
    "korean": ("🇰🇷 Корейская", "east_asian", "рис, намуль, ферментированные приправы"),
    "indian": ("🇮🇳 Индийская", "south_asian", "бобовые, рис, специи, лепёшки"),
    "american": ("🇺🇸 Американская", "north_american", "супы, традиционная домашняя кухня"),
}

# Данные из публичных источников; количество у quantified сверено с
# первоисточником, а method — наше короткое описание техники, НЕ цитата.
# Названия ингредиентов намеренно доступны поиску на русском.
RECIPES = [
    dict(id="gazpacho", cuisine="spanish", title="Гаспачо", region="Андалусия",
         kind="quantified", servings=4, ingredients=["помидоры 1 кг", "зелёный перец 2 шт.",
         "чеснок 2 зубчика", "хлеб 100 г", "оливковое масло 4 ст. л.",
         "хересный уксус 1 ст. л.", "вода", "соль"],
         method="Размочить хлеб и измельчить с овощами, маслом и уксусом; регулировать густоту водой.",
         publisher="TURESPAÑA · Spain.info", source_url="https://www.spain.info/en/recipe/gazpacho/"),
    dict(id="salmorejo", cuisine="spanish", title="Сальморехо", region="Андалусия",
         kind="quantified", servings=4, ingredients=["помидоры 1 кг", "чеснок 1 зубчик",
         "хлеб 200 г", "оливковое масло 100 г", "соль 10 г", "яйцо и хамон для подачи — по желанию"],
         method="Измельчить помидоры и удалить шкурки/семена; взбить с хлебом, маслом и чесноком до кремовой текстуры.",
         publisher="TURESPAÑA · Spain.info", source_url="https://www.spain.info/en/recipe/salmorejo/"),
    dict(id="paella", cuisine="spanish", title="Валенсийская паэлья", region="Валенсия",
         kind="quantified", servings=10,
         ingredients=["рис 1 кг", "курица 2 кг", "кролик 1 кг", "помидоры 300 г",
         "стручковая фасоль 500 г", "гаррофон 250 г", "оливковое масло 300 мл",
         "вода около 3,5 л", "шафран", "паприка 6 г", "соль"],
         method="Обжарить мясо; приготовить овощную основу, добавить воду и проварить; затем распределить рис, довести без интенсивного перемешивания. Жидкость корректируют по испарению.",
         publisher="TURESPAÑA · Spain.info", source_url="https://www.spain.info/en/recipe/paella/"),
    dict(id="tortilla", cuisine="spanish", title="Картофельная тортилья", region="Испания",
         kind="quantified", servings=4,
         ingredients=["картофель 4 средние шт.", "яйца 4–5 шт.", "лук 1 средний",
                      "оливковое масло 250 мл (для приготовления)", "соль"],
         method="Медленно приготовить картофель и лук в масле, слить излишки; соединить с яйцами и довести в сковороде с двух сторон.",
         publisher="TURESPAÑA · Spain.info", source_url="https://www.spain.info/es/receta/tortilla-patata/"),
    dict(id="paisana", cuisine="spanish", title="Овощная тортилья пайсана", region="Кастилия и Леон",
         kind="quantified", servings=4,
         ingredients=["яйца 8 шт.", "кабачок 1 небольшой", "красный перец 1/2",
         "зелёный перец 1 шт.", "зелёная фасоль 100 г", "горох 75 г", "картофель 150 г",
         "лук 1 крупный", "чоризо 50 г", "оливковое масло 1/2 чашки"],
         method="Овощи и чоризо готовят до мягкости; лишнее масло сливают, затем смешивают с яйцами и формируют тортилью.",
         publisher="TURESPAÑA · Spain.info", source_url="https://www.spain.info/es/receta/tortilla-paisana/"),
    dict(id="oyakodon", cuisine="japanese", title="Оякодон", region="Япония",
         kind="quantified", servings=2,
         ingredients=["куриное бедро 150 г", "лук 100 г", "яйца 2 шт.",
         "бульон даси 100 мл", "соевый соус 1 ст. л. + немного для маринада",
         "сахар 1/2 ст. л.", "мирин 1/2 ст. л.", "готовый рис 2 порции"],
         method="Курицу и лук готовят в бульоне с приправами; ближе к концу добавляют яйцо и подают поверх риса.",
         publisher="MAFF Japan · Our Regional Cuisines",
         source_url="https://www.maff.go.jp/e/policies/market/k_ryouri/search_menu/3539/index.html"),
    dict(id="tonjiru", cuisine="japanese", title="Тондзиру (суп с мисо и свининой)", region="Кагосима",
         kind="quantified", servings=4,
         ingredients=["свинина 80 г", "дайкон 100 г", "морковь 50 г", "таро 100 г",
         "конняку 50 г", "жареный тофу 50 г", "ячменное мисо 50 г",
         "сушёные сардины 20 г", "вода 3 чашки"],
         method="Приготовить рыбный бульон, слегка обжарить мясо и овощи, протомить; мисо вводить ближе к окончанию.",
         publisher="MAFF Japan · Our Regional Cuisines",
         source_url="https://www.maff.go.jp/e/policies/market/k_ryouri/search_menu/4022/index.html"),
    dict(id="miso-ehime", cuisine="japanese", title="Мисо-суп Эхиме", region="Эхиме",
         kind="quantified", servings=4,
         ingredients=["ячменное мисо 60 г", "вода 500 мл", "сушёные сардины 30 г",
         "тофу 40 г", "жареный тофу 12 г", "таро 80 г", "дайкон 60 г",
         "сушёные шиитаке 2 г", "зелёный лук 20 г"],
         method="Приготовить даси; сварить овощи, затем растворить мисо в горячем бульоне и добавить зелёный лук.",
         publisher="MAFF Japan · Our Regional Cuisines",
         source_url="https://www.maff.go.jp/e/policies/market/k_ryouri/search_menu/5188/index.html"),
    dict(id="pesto", cuisine="italian", title="Песто по-генуэзски", region="Лигурия",
         kind="reference", servings=None,
         ingredients=["базилик", "кедровые орехи", "чеснок", "пармезан",
                      "пекорино", "оливковое масло", "соль"],
         method="Традиционная техника — растирание ингредиентов в ступке; страница не задаёт универсальные граммовки.",
         publisher="Italia.it · Italian National Tourism Board",
         source_url="https://www.italia.it/en/liguria/things-to-do/pesto-genovese"),
    dict(id="greek-salad", cuisine="greek", title="Греческий салат", region="Греция",
         kind="reference", servings=None,
         ingredients=["помидоры", "огурец", "лук", "фета", "оливки",
                      "орегано", "каперсы", "оливковое масло", "уксус", "соль"],
         method="Нарезать овощи и дополнить сыром, оливками и орегано; заправить маслом и уксусом.",
         publisher="Greek National Tourism Organisation",
         source_url="https://www.visitgreece.gr/en/experiences/gastronomy/traditional-products/greek-salad"),
    dict(id="menemen", cuisine="turkish", title="Менемен", region="Турция",
         kind="reference", servings=None,
         ingredients=["яйца", "помидоры", "зелёный перец", "растительное масло",
                      "специи", "сыр — вариация"],
         method="Овощная основа из томатов и перца томится в масле, затем добавляются яйца; точных граммовок источник не приводит.",
         publisher="GoTürkiye · Türkiye Tourism Promotion",
         source_url="https://goturkiye.com/blog/5-turkish-breakfast-dishes-to-try"),
    dict(id="cilbir", cuisine="turkish", title="Чылбыр", region="Турция",
         kind="reference", servings=None,
         ingredients=["яйца", "йогурт", "чеснок", "сливочное масло", "красный перец"],
         method="Яйца пашот подаются на чесночном йогурте с ароматным перечным маслом; точной раскладки на странице нет.",
         publisher="GoTürkiye · Türkiye Tourism Promotion",
         source_url="https://goturkiye.com/blog/5-turkish-breakfast-dishes-to-try"),
    dict(id="bibimbap", cuisine="korean", title="Чонджу пибимпап", region="Чонджу",
         kind="reference", servings=None,
         ingredients=["рис", "ростки сои", "шпинат", "кабачок", "грибы",
                      "говядина", "яйцо", "кочуджан", "кунжутное масло"],
         method="Разные овощи готовят отдельно, чтобы сохранить текстуру, затем выкладывают на рис вместе с мясом, яйцом и заправкой.",
         publisher="Korea Tourism Organization · VISITKOREA",
         source_url="https://english.visitkorea.or.kr/svc/contents/contentsView.do?vcontsId=221301"),
    dict(id="chila", cuisine="indian", title="Чила (региональная лепёшка)", region="Чхаттисгарх",
         kind="reference", servings=None,
         ingredients=["рисовая основа", "урад дал", "зелёный чатни для подачи"],
         method="Национальный туристический источник описывает лепёшку из рисового теста и урад дала, но не даёт полных пропорций.",
         publisher="Ministry of Tourism, India · Incredible India",
         source_url="https://www.incredibleindia.gov.in/en/chhattisgarh/raipur/exploring-the-culinary-delights-of-raipur"),
    dict(id="lentil-soup", cuisine="american", title="Суп с чечевицей и томатами", region="США / рецепт NIH",
         kind="quantified", servings=11,
         ingredients=["сухая чечевица 2 чашки", "морковь 2 средние", "сельдерей 2 стебля",
         "лук 1 небольшой", "чеснок 2 зубчика", "томат консервированный 14,5 унции",
         "овощной бульон 2 чашки", "вода 6,5 чашек", "оливковое масло 2 ст. л.",
         "орегано 1 ч. л.", "базилик 1 ч. л."],
         method="Овощи размягчают в масле, затем добавляют приправы, чечевицу, томаты и жидкость; варят до мягкости бобовых.",
         publisher="NIH · National Heart, Lung, and Blood Institute",
         source_url="https://www.nhlbi.nih.gov/health/heart-healthy-living/healthy-foods/healthy-eating-recipes/lentil-soup"),
    dict(id="goldenrod", cuisine="american", title="Яйца Goldenrod на тостах", region="США / историческая кухня",
         kind="quantified", servings=None,
         ingredients=["яйца вкрутую 3 шт.", "сливочное масло 1 ст. л.", "мука 1 ст. л.",
                      "молоко 1 чашка", "тосты 5 ломтиков", "соль", "перец", "петрушка"],
         method="Историческая рецептура: белый соус на масле, муке и молоке соединяется с рублеными яйцами, подаётся на тосте.",
         publisher="Fannie Merritt Farmer · The Boston Cooking-School Cook Book (1910)",
         source_url="https://www.gutenberg.org/ebooks/65061", source_type="public_domain_book"),
]

CHECKED_ON = "2026-10-09"


def validate_seed() -> None:
    ids = set()
    for item in RECIPES:
        assert item["id"] not in ids and item["id"].isascii()
        ids.add(item["id"])
        assert item["cuisine"] in CUISINES
        assert item["kind"] in {"quantified", "reference"}
        assert item["ingredients"] and item["method"] and item["publisher"]
        link = urlparse(item["source_url"])
        assert link.scheme == "https" and link.netloc
        assert item["kind"] != "quantified" or all(isinstance(x, str) for x in item["ingredients"])


def as_row(item: dict) -> dict:
    cuisine_label, group, flavour = CUISINES[item["cuisine"]]
    return {
        "id": item["id"], "cuisine": item["cuisine"], "cuisine_label": cuisine_label,
        "region": item["region"], "title": item["title"], "kind": item["kind"],
        "servings": item["servings"], "ingredients": item["ingredients"],
        "method": item["method"], "publisher": item["publisher"],
        "source_url": item["source_url"],
        "source_type": item.get("source_type", "official_reference"),
        "reviewed_on": CHECKED_ON,
        "tags": {"group": group, "flavour": flavour},
    }
