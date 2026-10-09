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
    "french": ("🇫🇷 Французская", "european", "тушёные овощи, сырные и сливочные блюда"),
    "moroccan": ("🇲🇦 Марокканская", "north_african", "тажины, кускус, пряные супы"),
    "georgian": ("🇬🇪 Грузинская", "caucasus", "тесто с сыром, орехи, зелень, бобовые"),
    "chinese": ("🇨🇳 Китайская", "east_asian", "тофу, соусы, региональные техники"),
    "american": ("🇺🇸 Американская", "north_american", "супы, традиционная домашняя кухня"),
}

# Пользовательская навигация: группы пересекаются, ведь Средиземноморье
# одновременно относится к нескольким культурно-географическим традициям.
CUISINE_GROUPS = {
    "mediterranean": ("🌿 Средиземноморская", ("spanish", "italian", "greek", "turkish", "moroccan")),
    "european": ("🥐 Европейская", ("french", "italian", "spanish", "greek")),
    "eastern": ("🥢 Восточная и азиатская", ("turkish", "georgian", "japanese", "korean", "chinese", "indian")),
    "other": ("🍲 Другие направления", ("american", "moroccan")),
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
    dict(id="ratatouille", cuisine="french", title="Рататуй", region="Прованс",
         kind="quantified", servings=4,
         ingredients=["кабачки 4 небольших", "баклажаны 2 шт.", "красный перец 2 шт.",
         "помидоры 4 крупных", "лук 2 шт.", "чеснок 2 зубчика",
         "оливковое масло 4 ст. л.", "сахар 1/2 ч. л.", "базилик", "соль", "перец"],
         method="Нарезать овощи, подготовить томаты, готовить овощную смесь до мягкости и гармонии вкусов.",
         publisher="Atout France · Explore France",
         source_url="https://www.france.fr/en/article/taste-provence-this-weekend-and-make-a-ratatouille/"),
    dict(id="tartiflette", cuisine="french", title="Тартифлет", region="Савойя",
         kind="quantified", servings=6,
         ingredients=["картофель 1,3 кг", "сливочное масло 2 ст. л.", "лук 1 шт.",
         "бекон 200 г", "белое сухое вино 150 мл", "сливки 200 мл",
         "реблошон 1 головка", "чеснок 1 зубчик"],
         method="Картофель предварительно подваривают; лук и бекон обжаривают, а компоненты доводят с сыром до горячей запечённой основы.",
         publisher="Atout France · Explore France",
         source_url="https://www.france.fr/en/article/ultimate-comfort-food-tartiflette/"),
    dict(id="harira", cuisine="moroccan", title="Харира", region="Марокко",
         kind="reference", servings=None,
         ingredients=["бобовые", "помидоры", "макаронные изделия", "мука", "специи"],
         method="Традиционный марокканский суп с томатами и бобовыми; официальный источник описывает состав без дозировок.",
         publisher="Moroccan National Tourist Office · Visit Morocco",
         source_url="https://www.visitmorocco.com/en/travel-info/food-drinks"),
    dict(id="tajine", cuisine="moroccan", title="Тажин", region="Марокко",
         kind="reference", servings=None,
         ingredients=["мясо или рыба или овощи", "пряности", "сухофрукты — возможная вариация"],
         method="Блюдо готовят методом томления; состав сильно зависит от региона и выбранного вида тажина.",
         publisher="Moroccan National Tourist Office · Visit Morocco",
         source_url="https://www.visitmorocco.com/en/travel-info/food-drinks"),
    dict(id="khachapuri", cuisine="georgian", title="Имеретинский хачапури на сковороде",
         region="Имерети / рецепт Gunda", kind="quantified", servings=4,
         ingredients=["сильная пшеничная мука 400 г", "цельнозерновая мука 50 г",
         "сметана 350 г", "молоко 50 г", "сахар 5 г", "имеретинский сыр 600 г",
         "сулугуни 200 г", "соль 10 г", "сливочное масло для подачи"],
         method="Замесить мягкое тесто, охладить порции, закрыть начинку из двух сыров и осторожно раскатать; подрумянить на сковороде с двух сторон.",
         publisher="Georgia Travel · Gunda's pan-fried Imeretian khachapuri",
         source_url="https://georgia.travel/rediscovering-khachapuri-georgias-must-try-classic"),
    dict(id="lobio", cuisine="georgian", title="Лобио", region="Грузия",
         kind="reference", servings=None,
         ingredients=["фасоль", "кориандр", "пажитник", "чеснок", "лук"],
         method="Пряное блюдо из фасоли; туристический источник описывает тушёную основу с кориандром и чесноком.",
         publisher="Georgia Travel",
         source_url="https://georgia.travel/rediscovering-khachapuri-georgias-must-try-classic"),
    dict(id="mapo-tofu", cuisine="chinese", title="Мапо тофу", region="Сычуань",
         kind="reference", servings=None,
         ingredients=["тофу", "говядина", "острая сычуаньская приправа"],
         method="Характерны сочетание мягкого тофу с мясом и пряная, вызывающая покалывание сычуаньская вкусовая основа; источник не даёт точной рецептуры.",
         publisher="China.org.cn · Sichuan cuisine overview",
         source_url="https://www.china.org.cn/top10/2010-11/22/content_21395426_6.htm"),
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
