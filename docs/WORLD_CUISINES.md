# Проверенная библиотека кухонь Сушефа (первая партия)

**Версия каталога:** 2026-10-09. **Объём исходников:** 23 карточки, 12 национальных кухонь. Это **начальное наполнение**, не полная энциклопедия кухни мира.

## Что добавлено

- Публичный каталог в SQL-таблице `cuisine_recipes` с `id`, `cuisine`, `region`, `title`, `ingredients`, `method`, `servings`, `kind`, `publisher`, `source_url`, `source_type`, `reviewed_on`.
- Первая миграция с наполняющими записями: `migrations/versions/0003_cuisine_catalog.py`. При повторном обновлении **существующие записи и личные данные не перезаписываются**. Для существующего PostgreSQL обязательно создать pg_dump до запуска Alembic.
- Категории для пользователя **пересекаются**, чтобы Средиземноморье одновременно встречалось и в Европейском, и в Восточном разделе там, где это культурно оправдано.
- Telegram: **Главное меню → 🌍 Кухни мира → регион → национальная кухня → блюдо → источник**. Кнопка «Приготовить по мотивам» собирает индивидуальную домашнюю адаптацию и сохраняет ссылку на источник в готовом рецепте.
- При обычном запросе «что приготовить из кабачка и яиц» дешёвый локальный поиск по словам в названиях/ингредиентах подскажет модели до **двух** релевантных карточек без второго LLM-вызова. Это подсказка, а не гарантированное совпадение.
- История блюд и персональная память по Telegram ID отделены от общего каталога.

## Уровень доказательности

`quantified` — в первоисточнике **есть раскладка ингредиентов с количествами**. Это НЕ означает, что адаптация Сушефа, изменение количества соли, времени, культуры ферментации или способа хранения проверены исходным издателем.

`reference` — первоисточник подтверждает название, состав и/или характерный способ приготовления, но **не даёт полную количественную раскладку**. Сушефу разрешено сделать собственную домашнюю рецептуру, но запрещено выдавать её за точный оригинал.

Числа и техники описаны собственными словами. Текст сайта, фотографии, страницы книг и другие объекты авторского права не копируются в базу целиком. Внешние URL **не скачиваются** автоматически ботом.

## Реальные первоисточники

| Направление | Первичный ресурс |
| --- | --- |
| Испанская | [Официальный Spain.info: гаспачо](https://www.spain.info/en/recipe/gazpacho/), [паэлья](https://www.spain.info/en/recipe/paella/), [сальморехо](https://www.spain.info/en/recipe/salmorejo/), [тортилья](https://www.spain.info/es/receta/tortilla-patata/), [пайсана](https://www.spain.info/es/receta/tortilla-paisana/) |
| Японская | [MAFF Japan: оякодон](https://www.maff.go.jp/e/policies/market/k_ryouri/search_menu/3539/index.html), [тондзиру](https://www.maff.go.jp/e/policies/market/k_ryouri/search_menu/4022/index.html), [мисо-суп](https://www.maff.go.jp/e/policies/market/k_ryouri/search_menu/5188/index.html) |
| Итальянская | [Italia.it: Pesto Genovese](https://www.italia.it/en/liguria/things-to-do/pesto-genovese) |
| Греческая | [Visit Greece: Greek salad](https://www.visitgreece.gr/en/experiences/gastronomy/traditional-products/greek-salad) |
| Турецкая | [GoTürkiye: Menemen, Çılbır](https://goturkiye.com/blog/5-turkish-breakfast-dishes-to-try) |
| Корейская | [Korea Tourism Organization: Jeonju Bibimbap](https://english.visitkorea.or.kr/svc/contents/contentsView.do?vcontsId=221301) |
| Индийская | [Ministry of Tourism of India: Chila](https://www.incredibleindia.gov.in/en/chhattisgarh/raipur/exploring-the-culinary-delights-of-raipur) |
| Французская | [France.fr: Ratatouille](https://www.france.fr/en/article/taste-provence-this-weekend-and-make-a-ratatouille/), [Tartiflette](https://www.france.fr/en/article/ultimate-comfort-food-tartiflette/) |
| Марокканская | [Moroccan National Tourist Office: Harira, Tajine](https://www.visitmorocco.com/en/travel-info/food-drinks) |
| Грузинская | [Georgia Travel: рецепт имеретинского хачапури от Gunda и описание лобио](https://georgia.travel/rediscovering-khachapuri-georgias-must-try-classic) |
| Китайская | [China.org.cn: обзор Mapo Tofu](https://www.china.org.cn/top10/2010-11/22/content_21395426_6.htm) — **описательная статья, не проверенная количественная рецептура** |
| Американская | [NIH: Lentil Soup](https://www.nhlbi.nih.gov/health/heart-healthy-living/healthy-foods/healthy-eating-recipes/lentil-soup); историческая книга [Fannie Merritt Farmer, *The Boston Cooking-School Cook Book*](https://www.gutenberg.org/ebooks/65061), доступная через Project Gutenberg |

Книга Фанни Фармер находится в публичном достоянии **в США** по сведениям Project Gutenberg. Применимость прав на любые публикации в другой юрисдикции требует отдельной проверки; из книги мы используем библиографические данные, ингредиенты и краткое собственное описание идеи.

## Что потребуется на следующем этапе

1. **Редакторский конвейер** для добавления сотен и тысяч блюд: первоисточник → лицензия/права → сверка количеств → пищевая безопасность по категории → reviewer → публикация конкретной версии.
2. **Поиск по нормализованным продуктам**, синонимам и единицам, с качественной морфологией русского языка. Текущее сравнение первых четырёх букв слова — лишь стартовый дешёвый механизм, не надёжный способ пищевых ограничений.
3. **Явные группы аллергенов и перекрёстный контакт**; нельзя по одному совпадению слова считать блюдо безопасным.
4. **Профессиональные технологические поля**: выход, потери, критические этапы, варианты замен, методы, оборудование, температурные ограничения, уровень сложности, дегустационные критерии, автор адаптации.
5. **Качество рекомендаций**: тесты модельных диалогов с новичком и опытным шефом, тесты отказа от неподтверждённой технологической информации, реальные проверки ClaudeHub.
6. Автопроверка доступности ссылок и редакторская ревизия при обновлении карточки. Бот не должен зависеть от стороннего сайта для работы в момент приготовления.

## Проверка и деплой

Через Codespaces **только после прохождения локального `compileall`, `pytest -q`**, проверки `alembic upgrade head` на копии production БД, подтверждения `0003_cuisines`, бэкапа и настоящего Telegram/ClaudeHub smoke test. Скрипт `scripts/deploy_via_codespaces.sh` привязан к ветке `feat/cuisine-knowledge-audit-20261009`. GitHub Actions не использовать. Пока нет результатов тестов и live-проверки — статус production **не подтверждён**.
