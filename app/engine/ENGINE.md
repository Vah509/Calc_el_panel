# Универсальный CRUD-движок

Генерирует страницу списка + модалку/полноэкранную форму
редактирования (Alpine.js) и JSON API по одному декларативному
описанию таблицы (`TableConfig`). Заменяет ручное написание
`*_api.py` + `*_alpine.html` на каждую новую сущность.

Текущее состояние: **v94**. Полностью переписано с версии v25 (тогда
покрывал только `/material-v2`/`/brand-v2`) — с тех пор движок
дорос до дерева комплектов (3 уровня + состав), полноценного
документооборота (request → calculation → specification → invoice,
каждый со своей нумерацией, вкладками, каскадами пересборки) и
нескольких специализированных построчных примитивов (`materials_tab`,
`readonly_items_tab`, `invoice_items_tab`). Обновляется только по
явной просьбе Вахтанга ("свести документацию") — актуализировать в
той же сессии, где меняется код, при следующем таком запросе.

## Файлы

| Файл | Отвечает за |
|---|---|
| `config.py` | Датаклассы конфигурации: `TableConfig`, `FieldConfig`, `ComputedPair`, `Relation`, `FormRow`, `ActionButton`, `Hierarchy` — самый подробный источник правды, каждое поле там прокомментировано с примером и датой введения |
| `formulas.py` | Формулы `ComputedPair` (без `eval`), продублированы в Python и в JS (`ENGINE_FORMULAS` внутри `page.py`) — должны совпадать |
| `api.py` | Фабрика JSON-роутера: `GET/POST/PUT/DELETE /api/{key}` + `.../copy`, `.../items`, `.../bulk-mark-delete`, `.../actions/{action}` |
| `page.py` | Рендер HTML (список + модалка/форма) через Jinja + Alpine.js; `CLIENT_ACTIONS` — client-side обработчики кнопок |
| `page_router.py` | Подключение `/{key}-v2` страниц к FastAPI |
| `tables.py` | Реальные `TableConfig` всех таблиц (`ALL_TABLES`) + все серверные `action_handlers`/хуки |
| `register.py` | Регистрация api+page роутеров для каждой записи `ALL_TABLES` |
| `document_numbering.py` | `next_document_number()` — общий счётчик номеров документов по префиксу (`DocumentCounter`) |
| `document_chain.py` | `ChainLink`-реестр для страницы "Цепочка документов" — НЕ то же самое, что `Hierarchy` (см. ниже) |
| `name_template.py` | `render_name_template()` — подстановка плейсхолдеров в шаблон названия (используется `Calculation.full_name`) |

## Как добавить новую простую таблицу-справочник

1. Модель SQLModel уже должна существовать в `app/models/`.
2. В `tables.py` создать `TableConfig(...)` — `material_table` или
   `firm_table` как примеры среднего размера (relation, computed
   pair/action buttons, form_rows).
3. Добавить в список `ALL_TABLES` в конце `tables.py`.
4. Страница и API появляются автоматически на `/{key}-v2` и
   `/api/{key}` — руками ничего больше не пишется.

Для составного документа (со своей нумерацией, вкладками, дочерними
строками, каскадами) — см. разделы "Документы и нумерация" и
"Построчные примитивы" ниже, это не просто `TableConfig` с полями.

Наименование полей/функций/таблиц согласуется с Вахтангом до того,
как попадает в код — особенно если есть неоднозначность в русском/
английском переводе.

## `FieldConfig` — ключевые опции

Полный список с подробными комментариями — в самом `config.py`,
здесь только ориентир, что вообще возможно:

```python
FieldConfig(
    name="short_name", label="Короткое имя", widget="text",
    required=True, placeholder="ABB S203 C16",
    in_list=True, list_width="22%",
    searchable=True, search_toggle=True, search_default=True,
    is_numeric=False, in_form=True, form_width="140px",
    default=20.0, default_from_constant="calculation_name_template",
    default_first_option=False, readonly=False, virtual=False,
    hint="Доступные плейсхолдеры: {product_name}, {brand}",
    inline_action="recalc_full_name",       # кнопка сразу за полем
    on_change_action="brand_slot_labels",   # client-side реакция на смену поля
    row_actions=["Спецификация", "Пересчитать"],
    row_action_names=["build_specification_1", None],
    tab="Основное",                          # при form_tabs у таблицы
)
```

Отдельные механизмы стоит помнить явно:
- **`readonly`** — поле показывается как текст, не как input; сервер
  игнорирует его в payload при `PUT`. Используется для снэпшот-полей
  (`unit_price`, `unit_name` у `invoice_item` и т.п.).
- **`virtual`** — поле НЕ хранится в модели/БД вообще (например общая
  ставка НДС у материала — только в `constants`, но должна быть видна
  в форме). Требует `source_constant_key`.
- **`default_from_constant`** — дефолт новой записи берётся из
  `constant.value` динамически, а не хардкодом (требует
  `TableConfig.needs_constants=True`).
- **`inline_action` vs `row_actions` vs `on_change_action`** — три
  разных способа привязать поведение к полю: `inline_action` — кнопка
  с реальным обработчиком в том же ряду; `row_actions`/`row_action_names`
  — до нескольких кнопок в ряду, каждая может быть либо активной
  (указано имя), либо disabled-заглушкой (`None`); `on_change_action`
  — client-side функция, срабатывающая при каждом изменении поля
  (`CLIENT_ACTIONS` в `page.py`), не при сохранении.

## `ComputedPair` — пересчитываемые пары полей

```python
ComputedPair(
    field_a="price_excl_vat", field_b="price_incl_vat",
    rate_field="vat_rate", rate_constant_key="vat_rate",
    formula="vat",
    label_a="Цена без НДС", label_b="Цена с НДС", label_rate="Ставка НДС",
)
```

- Изменение `field_a` пересчитывает `field_b` (и наоборот).
- `rate_constant_key` (не `rate_field`) — ставка общая для всех
  записей, живёт только в `constant`, не хранится в самой строке
  (текущий способ для НДС после отказа от `Material.vat_rate`).
- Формула реализуется в ОБОИХ местах — `formulas.py` (Python,
  бэкенд-валидация, `422` при отсутствующей ставке) и
  `ENGINE_FORMULAS` в `page.py` (JS, мгновенный пересчёт на фронте).
  `eval` нигде не используется.

## `FormRow` / `form_tabs` — раскладка формы

Без `form_rows` каждое поле — отдельная строка, в порядке объявления
в `config.fields`. `form_rows` группирует несколько полей в один
визуальный ряд:

```python
form_rows=[
    FormRow(field_names=["brand_id", "sku_article"]),
    FormRow(field_names=["price_excl_vat", "price_incl_vat"]),
]
```

`form_tabs=["Основное", "Настройки", "Материалы", ...]` включает
переключение вкладок без закрытия формы — тогда КАЖДОЕ поле должно
иметь `FieldConfig.tab` (поле без `tab` уходит на первую вкладку по
умолчанию). Используется у `calculation` (5 вкладок).

## Построчные примитивы (дочерние таблицы документа)

Движок предлагает НЕСКОЛЬКО разных примитивов для показа дочерних
строк документа на его форме — они не взаимозаменяемы, каждый под
свою степень интерактивности:

| Примитив | Интерактивность | Пример использования |
|---|---|---|
| `materials_tab` / `kits_tab` | Полная: добавление, удаление, инлайн-редактирование количества, picker | `calculation` → `calculation_item` |
| `readonly_items_tab` | Никакой — чистый read-only снимок | `specification` → `specification_item` |
| `invoice_items_tab` | Частичная — одно редактируемое поле (скидка) на строку, остальное read-only | `invoice` → `invoice_item` |

Общее для всех трёх: дочерняя таблица должна иметь
`Hierarchy(parent_field=...)`, указывающий на FK к родителю — движок
делает `GET /api/{child_key}?parent_id={editing.id}` при открытии
формы. Выбор примитива — по степени редактируемости, не по
"похожести" данных: `specification_item` и `invoice_item` оба
снэпшоты, но у первого человек вообще не трогает строки, а у
второго правит скидку — отсюда разные примитивы, а не один
параметризованный.

Полный список параметров каждого примитива (`*_columns`,
`*_table_key`, `*_sum_field` и т.д.) — см. комментарии в `config.py`
рядом с соответствующими полями `TableConfig`, они длинные и точные,
здесь не дублируются.

## `Hierarchy` vs `document_chain.py` — не путать

- **`Hierarchy`** (`config.py`) — для drill-down ОДНОЙ ветки
  справочника на одном экране: `kit_group → kit_section → kit`, три
  `TableConfig`, у каждого свой уровень. Также переиспользуется как
  "просто `parent_id`-фильтр без дерева" у дочерних строк документа
  (`calculation_item.hierarchy.parent_field = "calculation_id"`) —
  без `child_key`, чисто ради фильтрации списка.
- **`document_chain.py::CHAIN_LINKS`** — для САМОСТОЯТЕЛЬНЫХ
  документов (`request → calculation/specification/invoice`), каждый
  со своей отдельной страницей движка, просто связанных FK на
  родителя. Используется ТОЛЬКО страницей "Цепочка документов"
  (`/documents-chain?request_id=`), обходит граф рекурсивно.

## `ActionButton` и хуки — логика за пределами обычного CRUD

- **`ActionButton(action, label, tab, client_side)`** + `action_handlers`
  — кнопка с реальной серверной логикой (`fn(instance, session) -> dict`,
  сам решает про `commit`) ИЛИ, при `client_side=True`, чистая
  JS-функция в `CLIENT_ACTIONS` (`page.py`) — не требует `editing.id`,
  работает и для ещё не сохранённой записи. Вызов:
  `POST /api/{key}/{id}/actions/{action}`.
- **`before_create_hook(data, session) -> dict`** — мутирует payload
  ДО создания модели (например подстановка `unit_id` по умолчанию у
  новой калькуляции).
- **`before_update_hook(instance, session) -> None`** — мутирует уже
  применённый к payload `instance` ДО `commit` (например пересчёт
  `unit_price_after_discount`/`line_total` у `invoice_item` при смене
  `discount_percent`).
- **`open_edit_action`** — вызывается автоматически при каждом
  открытии формы существующей записи (не по клику) — например
  обновление сумм вкладки "Стоимость" калькуляции без обязательного
  нажатия "Пересчитать".

## Нумерация документов

`document_number_field` + `document_prefix` на `TableConfig` включают
автогенерацию (`next_document_number()`, `document_numbering.py`) по
общему счётчику `DocumentCounter` (одна строка на префикс: R/S/I).
Номер редактируется вручную свободно; ручная правка на бо́льшее число
подтягивает счётчик вверх, дубликаты не проверяются.

## Галочки поиска (`enable_search_toggles`)

Когда включено на уровне таблицы — над строкой поиска показываются
чекбоксы "искать по <label>" для полей с `searchable=True` **и**
`search_toggle=True`. Поле с `searchable=True, search_toggle=False`
ищется всегда, без своего чекбокса. `Relation.searchable_fields`
расширяет то же самое на JOIN по связанной таблице (например поиск
заявки по имени клиента через `request.client_id`).

Механизм: `GET /api/{key}?q=...&search_fields=short_name&search_fields=full_name`
— без `search_fields` ищет по всем `searchable`, с ним — по
пересечению с реальным списком searchable-полей таблицы (защита от
поиска по произвольному полю модели через query-параметр).

## Фильтр по связи (chips в filterbar)

Работает автоматически для любого поля из `config.relations` с
`show_filter_chips=True` (по умолчанию) — рендерит чипы "Все" + по
одному на каждую запись связанной таблицы. `show_filter_chips=False`
(у документов с несколькими relation сразу — `request` с 5 полями)
отключает чипы именно для этого поля в пользу текстового поиска.

## Постгрес-миграции для новых полей на уже задеплоенных таблицах

Не часть движка формально, но критично при добавлении ЛЮБОГО нового
`FieldConfig`, чья модель уже существует на Railway: строку
`(table, column, ddl_type)` нужно добавить в
`_ensure_is_deleted_columns()` (`app/database.py`) В ТОЙ ЖЕ версии —
иначе SQLite-тесты (`create_all()` с нуля) зелёные, а первый же
`INSERT` на Postgres падает 500. См. подробный комментарий в самой
функции и историю в `docs/HANDOFF.md` (это происходило несколько раз
за историю проекта — самый частый источник production-багов).

## Тестирование изменений движка

Все правки прогоняются локально через `TestClient` до сборки архива
— `bash_tool` + `starlette.testclient.TestClient(app)` как контекст-
менеджер (`with TestClient(app) as client:`), чтобы гарантированно
сработали `startup`-события (`init_db()` и т.п.). Требует `httpx2`
(не `httpx`). Фоновый `uvicorn &` между вызовами `bash_tool`
ненадёжен — не использовать.

## Известные ограничения / на будущее

- Chips-фильтр по связи подгружает связанную таблицу целиком без
  пагинации при `init()` — годится для небольших справочников
  (бренды, клиенты), не масштабируется на сотни записей без отдельной
  логики (поиск/автокомплит вместо плоского списка чипов).
- `purge_*`-обработчики (см. `app/processors/registry.py`) не
  проверяют зависимости перед физическим удалением — актуально
  пересмотреть при первом реальном инциденте с оборванной ссылкой.
- Рефакторинг `enginePage()` (JS-компонент Alpine, ~60 методов) —
  сознательно отложен, будет пересмотрен, когда совпадёт с реальной
  новой работой, а не как отдельная задача.
- MkDocs с Material theme — возможный будущий вариант оформления
  папки `docs/`/этого файла в сайт, не решено, текущая структура
  `.md` уже с ним совместима при необходимости.
