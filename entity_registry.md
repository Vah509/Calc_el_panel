# Реестр сущностей — ЭлектроЩит

Единый источник правды по факту реального кода (не по плану/спеке).
Актуализирован под **v98** (2026-09-04) — сессия 3 плана
"Перепроведение" (план-файл docs/HANDOFF_reprovodenie.md в
репозитории физически отсутствует, см. docs/HANDOFF.md): кнопка
«Обновить цены» на каждой вкладке бренда заявки, пересчитывающая цены
всех активных калькуляций слота разом. Обновляется тем же шагом, где
меняется код (то, что это правило выпадало из процесса раньше и
привело к сильному устареванию v48→v94 — сама причина ревизии v95).

Формат: сначала общая инфраструктура (движок, документооборот,
процессоры, печатные формы), затем каждая таблица — поля / движок /
примечания в одном месте, в порядке `ALL_TABLES`.

---

## 1. Инфраструктура

### Файлы

```
app/
├── __init__.py
├── database.py            ← подключение к БД, get_session(), init_db(),
│                             seed_constants(), _ensure_is_deleted_columns()
│                             (ALTER TABLE для полей, добавленных в модель
│                             ПОСЛЕ первого деплоя таблицы на Postgres —
│                             см. критический принцип проекта в разделе 5)
├── main.py                 ← точка входа, регистрирует роутеры движка +
│                             processors + documents_chain + invoice_print, /health
├── version.py               ← APP_VERSION, NAV_MENU (верхнее меню)
├── models/                   ← 1 класс-таблица = 1 файл, все модели SQLModel
│                             (полный список — раздел 2 ниже)
├── engine/                    ← универсальный CRUD/drill-down движок
│   ├── config.py                 ← TableConfig, FieldConfig, ComputedPair,
│   │                                Relation, FormRow, ActionButton, Hierarchy
│   ├── tables.py                  ← экземпляры TableConfig для всех таблиц
│   │                                (ALL_TABLES) + все action-обработчики
│   ├── api.py                    ← build_api_router() — REST по TableConfig
│   ├── page.py                    ← build_page_router() — HTML (Alpine.js)
│   ├── page_router.py              ← обвязка page.py в APIRouter
│   ├── register.py                 ← регистрация api+page роутеров
│   ├── document_numbering.py        ← next_document_number() — общий
│   │                                счётчик номеров документов по префиксу
│   ├── document_chain.py            ← ChainLink-реестр родитель/потомок
│   │                                для страницы "Цепочка документов"
│   ├── name_template.py             ← render_name_template() — подстановка
│   │                                плейсхолдеров в шаблон названия
│   │                                (Calculation.full_name)
│   ├── formulas.py                  ← формулы ComputedPair (без eval),
│   │                                продублированы в JS (page.py)
│   └── ENGINE.md                    ← техническая документация движка
├── documents_chain/            ← страница "Цепочка документов" (кнопка
│   │                            на списке request), обходит CHAIN_LINKS
│   ├── api.py, page.py, router.py
├── invoice_print/               ← печатные формы счёта-фактуры
│   ├── data.py                     ← build_invoice_print_data() — ЕДИНАЯ
│   │                                точка сборки данных для PDF И Excel
│   ├── pdf_builder.py               ← reportlab, DejaVuSans TTF (кириллица)
│   ├── xlsx_builder.py               ← openpyxl, тот же макет, что PDF
│   ├── amount_in_words.py            ← сумма прописью (укр., гривні/копійки)
│   ├── router.py                     ← GET /invoice-print/{id}/pdf|xlsx
│   └── fonts/                         ← DejaVuSans.ttf, DejaVuSans-Bold.ttf
├── processors/                  ← страница /processors — разовые обработчики
│   ├── registry.py                  ← PROCESSORS: recalc_material_vat +
│   │                                автосгенерированные purge_*
│   ├── page.py, router.py
├── static/style.css
└── templates/base.html            ← общий каркас, верхнее меню из NAV_MENU
```

Паттерн: 1 класс-таблица = 1 файл в `models/`. Вся CRUD/UI-логика — в
универсальном движке (`app/engine/`), не в отдельных роутерах на
таблицу. Составные документы (request/calculation/specification/
invoice) добавляют СВОЮ бизнес-логику (обработчики кнопок, каскады)
поверх того же движка через `action_handlers`/хуки — не отдельными
роутерами в обход движка.

### Универсальные REST-эндпоинты движка (на каждую таблицу из ALL_TABLES)

| Метод | Путь | Назначение |
|---|---|---|
| GET | `/api/{key}` | Список: `parent_id` (drill-down/иерархия строк), `q`/`search_fields`, `page`/`page_size`, сортировка. Формат: `{items, total, page, page_size, total_pages}` |
| POST | `/api/{key}` | Создать |
| PUT | `/api/{key}/{item_id}` | Обновить (readonly-поля в payload игнорируются) |
| DELETE | `/api/{key}/{item_id}` | Удалить — поведение зависит от `delete_mode` |
| POST | `/api/{key}/{item_id}/copy` | Server-side копирование записи |
| PUT | `/api/{key}/{item_id}/items` | Полная замена дочерних записей (только `edit_mode="items_modal"`) |
| POST | `/api/{key}/bulk-mark-delete` | Безусловная установка `is_deleted` для набора id — 422 при `delete_mode != "soft"` |
| POST | `/api/{key}/{item_id}/actions/{action}` | Вызов именованного `ActionButton`/`action_handlers` обработчика, опционально с телом запроса (единственный сценарий с payload — `invoice_items_bulk_discount_action`) |

HTML-страница: `GET {url_path}` (например `/material-v2`,
`/invoice-v2/{id}` для документов с `own_page_url`) — одна страница на
все уровни drill-down/вкладки сразу, без перезагрузки между ними.

### `delete_mode` — три режима (`TableConfig.delete_mode`)

| Режим | Поведение DELETE | Таблицы (v94) |
|---|---|---|
| `"soft"` | Пометка `is_deleted=True`; физическое удаление — только через purge-processor | material, brand, kit, client, request, calculation, specification, firm, invoice |
| `"simple"` | Физическое удаление, но только если нет дочерних записей | kit_group, kit_section |
| `"hard"` (дефолт) | Безусловное немедленное физическое удаление | kit_item, calculation_item, specification_item, invoice_item, unit, product_type_rate, constant (allow_delete=False на деле блокирует) |

### Документооборот: request → calculation → invoice

**2026-09-05 (первый проход зачистки Specification, см.
`docs/HANDOFF_specification_cleanup.md` — второй проход планируется
отдельной сессией):** активная цепочка сокращена до `request →
calculation → invoice`. Invoice создаётся напрямую из отмеченных
калькуляций заявки (`_build_invoice_from_slot_handler`), минуя
Specification. Кнопка "Спецификация" на заявке и кнопка "Обновить" на
счёте (для счетов, привязанных к спецификации) — убраны из UI и
движка. Таблицы `specification`/`specification_item`, поле
`Invoice.specification_id`/`InvoiceItem.specification_item_id` в БД
**остаются нетронутыми** — нужны для 3-4 старых счетов, у которых
`specification_id` заполнен (архив, не мигрируется). Страницы
`/specification-v2/*` по-прежнему доступны напрямую по URL, но пункта
меню и связей из UI заявки/счёта на них больше нет.

Каждый документ имеет собственную нумерацию по префиксу через
`document_numbering.py` + `DocumentCounter` (одна строка на префикс:
R/calculation-без-префикса.../S/I — префикс "S" для Specification
больше не используется новыми документами, но зарезервирован).

Построчные дочерние таблицы (`calculation_item`, `specification_item`,
`invoice_item`) — каждая своя философия снэпшота/live-ссылки, см.
таблицу ниже:

| Дочерняя таблица | Родитель | Модель данных |
|---|---|---|
| `calculation_item` | calculation | LIVE — хранит `material_id`/`kit_id`, цена подтягивается на пересчёте |
| `specification_item` | specification | СНЭПШОТ — архивная таблица, новые записи не создаются с 2026-09-05 |
| `invoice_item` | invoice | СНЭПШОТ — для новых счетов копируется из отмеченных `Calculation` напрямую (`_build_invoice_from_slot_handler`); `discount_percent` — единственное поле, редактируемое человеком напрямую |

**Каскад пересборки через Specification** (`_sync_invoice_items_from_
specification` + `_refresh_invoice_items_handler`) — УДАЛЁН
2026-09-05. Актуален был только для старых счетов, привязанных к
specification_id; для них кнопка "Обновить" на карточке счёта больше
не работает (ожидаемо, см. HANDOFF_specification_cleanup.md).

### `document_chain.py` — реестр цепочки документов

`CHAIN_LINKS` (плоский список `ChainLink(child_key, parent_key, fk_field)`):
```
calculation → request  (request_id)
invoice     → request  (request_id)
```
`specification` убрана из реестра 2026-09-05 — `/documents-chain`
больше не показывает уровень "Спецификации" у заявки. Используется
ТОЛЬКО страницей "Цепочка документов" (кнопка на списке request →
`/documents-chain?request_id=`), обходит граф рекурсивно от корня
(`request`). Добавление нового типа документа — одна новая строка в
`CHAIN_LINKS`, без изменения кода страницы.

### Печатные формы счёта (`app/invoice_print/`)

`data.py::build_invoice_print_data(invoice_id, session)` — ЕДИНАЯ точка
сборки `InvoicePrintData` (dataclass) из БД: реквизиты firm/client,
построчные `InvoicePrintLine`, итоги. И `pdf_builder.py` (reportlab), и
`xlsx_builder.py` (openpyxl) принимают уже готовый `InvoicePrintData` и
только рисуют — расчёт сумм/прописи не дублируется между форматами.
Единица измерения строки берётся из `InvoiceItem.unit_name` — для
новых счетов копируется напрямую из `Calculation.unit_id → Unit.name`
при создании. Для СТАРЫХ счетов (собранных через Specification, до
2026-09-05) в `data.py` остаётся fallback-путь через
`InvoiceItem.specification_item_id → SpecificationItem →
Calculation.unit_id → Unit.name` — намеренно НЕ удалён в первом
проходе зачистки Specification, см. `docs/HANDOFF_specification_cleanup.md`.

Роуты: `GET /invoice-print/{id}/pdf`, `GET /invoice-print/{id}/xlsx` —
прямые ссылки для браузера (кнопки «Скачать PDF»/«Скачать Excel» на
карточке invoice, `client_side=True` ActionButton — просто открывает
URL в новой вкладке).

### Processors (`/processors`)

- `recalc_material_vat` — пересчитывает `Material.price_incl_vat` по
  текущей ставке из `constant.vat_rate`.
- `purge_{table_key}` — автогенерируется для КАЖДОЙ таблицы с
  `delete_mode == "soft"` (material, brand, kit, client, request,
  calculation, specification, firm, invoice). Физически удаляет все
  строки с `is_deleted=True`, **без проверки зависимостей** — известное
  упрощение, актуально пересмотреть при первом реальном инциденте.

---

## 2. Таблицы (в порядке `ALL_TABLES`)

### `brand`
| Поле | Тип | Назначение |
|---|---|---|
| id | int, PK | |
| name | str, unique, indexed | Название бренда |
| rate_vb | float, default 0.0 | Курс валюты поставщика (EUR/USD→грн), правится вручную |
| is_deleted | bool, default False, indexed | Soft-delete |

Движок: `delete_mode="soft"`.

### `unit` (справочник единиц измерения)
| Поле | Тип | Назначение |
|---|---|---|
| id | int, PK | |
| name | str, unique | "шт", "м", "кг", "послуга" и т.п. |
| sort_order | int, default 0 | Ручная сортировка в выпадающих списках |

Плоский справочник, используется как FK из `material.unit_id` и
`calculation.unit_id`. "Услуга" — обычная запись справочника ("услуга"
как unit), отдельной сущности для услуг нет.

### `product_type_rate` (справочник "Стоимость сборки")
| Поле | Тип | Назначение |
|---|---|---|
| id | int, PK | |
| name | str, indexed | Название типа изделия |
| hourly_rate | float, default 0.0 | Часовая ставка сборки |
| is_deleted | bool, default False, indexed | |

Используется калькуляцией (`Calculation.product_type_rate_id`) на
вкладке "Стоимость" для расчёта `hours_total` (сборка по часам, одна
из двух альтернативных ветвей `cost_method`).

### `client` (справочник клиентов)
| Поле | Тип | Назначение |
|---|---|---|
| id | int, PK | |
| short_name | str, indexed | Короткое название (поиск, списки) |
| full_name | str | Полное название (для документов/счетов) |
| egrpou_code | str, default "" | Код ЄДРПОУ |
| phone | str, default "" | Общий телефон клиента |
| contact_person_name / contact_person_phone | str, default "" | Контактное лицо, отдельный телефон |
| is_deleted | bool, default False, indexed | Soft-delete |

### `request` (заявка) — корень цепочки документов
| Поле | Тип | Назначение |
|---|---|---|
| id | int, PK | |
| document_number | str, default "" | Номер по счётчику префикса "R" |
| document_date | date | |
| client_id | int, FK→client.id | Заказчик (обязателен по бизнес-логике) |
| client_invoice_id | int, FK→client.id, nullable | Плательщик, если отличается от заказчика — "по умолчанию = заказчик" реализовано на уровне API, не constraint модели |
| brand_slot_1/2/3_id | int, FK→brand.id, nullable×3 | Три брендовых варианта, всегда все видны в форме |
| note | str, default "" | |
| is_deleted | bool, default False, indexed | |

Движок: `delete_mode="soft"`, `document_number_field="document_number"`,
`document_prefix="R"`, `own_page_url="/request-v2"`. Панель списка:
«Создать документ на основании» → `/calculation-v2?from_request={id}`,
«Показать цепочку» → `/documents-chain?request_id={id}`.

Форма (v97-v98, сессии 2-3 плана "Перепроведение" — план-файл
`docs/HANDOFF_reprovodenie.md` в репозитории отсутствует, см.
предупреждение в `docs/HANDOFF.md`) — `form_tabs=["Основное",
"Вариант 1", "Вариант 2", "Вариант 3"]`: "Основное" несёт номер/дату/
обоих клиентов/заметку, каждая из трёх остальных — один брендовый
слот. Каждый слот по-прежнему имеет пару кнопок «Спецификация»/
«Пересчитать» в своём ряду формы (`row_actions`) — только
«Спецификация N» реально работает (строит/пересобирает specification
для этого `brand_slot`), «Пересчитать» пока заглушка; путь через
спецификацию ещё не убран (запланировано на сессию 6). Под полем
бренда на каждой вкладке — примитив движка `brand_slot_calc_tabs`:
read-only список АКТИВНЫХ калькуляций этого слота (номер/название/
сумма/дата, сортировка по дате+времени, новые сверху) с чекбоксом в
каждой строке и кнопкой «Обновить список». Данные подтягивает один
action `refresh_brand_calculations`
(`_refresh_brand_calculations_handler`, tables.py) — он же подключён
как `open_edit_action`, поэтому срабатывает автоматически при каждом
открытии формы, не только по клику кнопки. Чекбоксы — **чисто
клиентское** состояние (`brandCalcSelected` в page.py), ничего не
пишут в БД; их отмеченный набор начнёт на что-то влиять (создание/
обновление счёта) в сессии 4 того же плана.

**v98 (сессия 3):** на каждой из трёх вкладок бренда, рядом с
«Обновить список», добавлена кнопка «Обновить цены»
(`TableConfig.action_buttons`, три `ActionButton` с одним и тем же
`action="recalc_brand_calculations"`, по одному на `tab=`). По клику
пересчитывает цены строк + производные суммы вкладки «Стоимость» ВСЕХ
активных калькуляций ВСЕХ трёх слотов сразу (не только текущего слота,
не только отмеченных чекбоксом) — тем же построчным алгоритмом, что и
кнопка «Пересчитать» внутри самой калькуляции
(`_recalc_calculation_prices`, общая функция, выделенная из
`_recalc_material_prices_handler`). Обработчик
`_recalc_brand_calculations_handler` коммитит один раз на весь набор
калькуляций, затем возвращает результат
`_refresh_brand_calculations_handler` — те же ключи
`brand_slot_1/2/3_calcs`, уже со свежими суммами, фронт подмешивает их
в `editing` без дополнительного клика «Обновить список».

### `calculation` (калькуляция) — одно изделие, один брендовый вариант
| Поле | Тип | Назначение |
|---|---|---|
| id | int, PK | |
| document_number, document_date, document_time | | Номер БЕЗ отдельного префикса документооборота — своя нумерация калькуляций |
| request_id | int, FK→request.id, nullable | |
| client_name | str, default "" | |
| full_name | str, default "" | Название изделия — генерируется по `name_template` (см. `name_template.py`), можно переопределить вручную |
| name_template | str, default `DEFAULT_NAME_TEMPLATE` | Шаблон подстановки плейсхолдеров |
| brand_slot | int, nullable | 1/2/3 — совпадает по смыслу с `brand_slot_N` в request |
| unit_id | int, FK→unit.id, nullable | Единица измерения ИЗДЕЛИЯ. Добавлено 2026-08-31 ПОСЛЕ первого деплоя таблицы — старые калькуляции имеют `unit_id=NULL` (см. `_ensure_is_deleted_columns`). Дефолт для новых калькуляций — "послуга" (`before_create_hook`, не первая опция списка) |
| quantity | float, default 1.0 | Количество изделий |
| status | str, default "active" | "active" / "delete_pending" — ручной выбор, без принудительного порядка переходов |
| cost_method | str, default "markup" | "markup" (наценка) или "hours" (сборка по часам) — определяет, какая из двух ветвей формулы стоимости используется в `final_total` |
| markup_percent | float, default 1.4 | |
| insurance_markup | float, default 1.1 | |
| assembly_hours | float, default 0.0 | Только для `cost_method="hours"` |
| product_type_rate_id | int, FK→producttyperate.id, nullable | |
| materials_total, kits_total, base_total, insured_total, markup_total, hours_total, final_total | float, default 0.0 | Расчётная цепочка (вкладка "Стоимость"): `base_total → insured_total → markup_total ИЛИ hours_total → final_total` |
| is_deleted | bool, default False, indexed | |

Движок: `delete_mode="soft"`, `own_page_url="/calculation-v2"`,
`form_tabs=["Основное","Настройки","Материалы","Комплекты","Стоимость"]`,
`materials_tab`/`kits_tab` (оба на общей физической таблице
`calculation_item`, различаются фильтром `material_id`/`kit_id` IS NOT NULL),
`needs_constants=True` (дефолт `name_template` из constant).
`open_edit_action` пересчитывает суммы вкладки "Стоимость" при каждом
открытии формы без обязательного клика "Пересчитать".

### `calculation_item` (строки калькуляции — материалы ИЛИ комплекты)
| Поле | Тип | Назначение |
|---|---|---|
| id | int, PK | |
| calculation_id | int, FK→calculation.id, nullable | |
| material_id | int, FK→material.id, nullable | Тип строки определяется тем, какое из двух полей заполнено |
| kit_id | int, FK→kit.id, nullable | Добавлено ПОСЛЕ первого деплоя (v67) |
| quantity | float, default 1.0 | |
| price_excl_vat | float, default 0.0 | СНЭПШОТ цены на момент добавления/пересчёта, не живая ссылка |

Движок: `hierarchy(parent_field="calculation_id")`, обе вкладки
"Материалы"/"Комплекты" калькуляции — чисто UI-разделение одной
физической таблицы через фильтр по заполненному FK.

### `material`
| Поле | Тип | Назначение |
|---|---|---|
| id | int, PK | |
| short_name | str, indexed | |
| brand_id | int, FK→brand.id, nullable | |
| sku_article | str, indexed, nullable | Артикул производителя |
| unit_id | int, FK→unit.id, nullable | Добавлено v63, ПОСЛЕ первого деплоя таблицы |
| price_excl_vat / price_incl_vat | float | Взаимный пересчёт через `ComputedPair`, ставка — живая ссылка на `constant.vat_rate` |
| price_vb_incl_vat | float, default 0.0 | Цена с НДС в валюте бренда-поставщика; независимый факт, связь с `Brand.rate_vb` считается на лету только в калькуляции |
| owner_id | int, indexed, nullable | Задел под многопользовательскую модель, не используется |
| is_deleted | bool, default False, indexed | |

Движок: `delete_mode="soft"`, `enable_search_toggles=True`.

### `kit_group` / `kit_section` / `kit` / `kit_item` — дерево комплектов
Без изменений с v48 по структуре, см. историю в git при необходимости:
- `kit_group` (1-й уровень): `name`(unique), `sort_order`, `is_deleted`.
  `delete_mode="simple"`, `hierarchy(child_key="kit_section")`.
- `kit_section` (2-й уровень): + `kit_group_id`.
  `delete_mode="simple"`, `hierarchy(parent_field="kit_group_id", child_key="kit")`.
- `kit` (3-й, нижний уровень): + `kit_section_id`.
  `delete_mode="soft"` (в отличие от group/section — на kit ссылаются
  `calculation_item.kit_id`), `edit_mode="items_modal"`,
  `items_source_table_key="kit_item"`.
- `kit_item` (состав комплекта): `kit_id`, `material_id`, `quantity`
  (default 1.0, дробные — метры кабеля/ленты). `delete_mode="hard"`
  (безусловное) — ничто не ссылается на конкретный `kit_item`,
  калькуляция хранит только `kit_id` и разворачивает состав live при
  пересчёте.

### `specification` (спецификация) — снимок по варианту заявки
| Поле | Тип | Назначение |
|---|---|---|
| id | int, PK | |
| document_number, document_date, document_time | | Номер по счётчику префикса "S" |
| request_id | int, FK→request.id, nullable | Родитель В ЦЕПОЧКЕ ДОКУМЕНТОВ (не calculation — одна спецификация агрегирует несколько калькуляций сразу) |
| brand_slot | int, nullable | 1/2/3, какой вариант заявки |
| client_id | int, FK→client.id, nullable | Снэпшот `Request.client_id` на момент формирования |
| total_amount | float, default 0.0 | Снэпшот суммы строк |
| is_deleted | bool, default False, indexed | |

Механика (кнопка «Спецификация N» на request): собрать все АКТИВНЫЕ
(`status="active"`) calculation этого `(request_id, brand_slot)` → для
каждой — снэпшот `full_name`/`final_total`/`quantity` БЕЗ
предварительного пересчёта калькуляций → **update in place** если для
этой пары уже существовала спецификация (тот же id/номер, только
даты обновляются) + каскад на привязанный invoice, иначе создать
новую. Каждая калькуляция — всегда отдельная строка, без схлопывания
одинаковых `product_name`.

### `specification_item` (строки спецификации)
| Поле | Тип | Назначение |
|---|---|---|
| id | int, PK | |
| specification_id | int, FK→specification.id, nullable | |
| calculation_id | int, FK→calculation.id, nullable | НЕ для live-подтяжки — только трассировка/повторное формирование |
| product_name | str, default "" | СНЭПШОТ ← `Calculation.full_name` |
| unit_price | float, default 0.0 | СНЭПШОТ ← `Calculation.final_total` |
| quantity | float, default 1.0 | СНЭПШОТ ← `Calculation.quantity` |
| line_total | float, default 0.0 | = unit_price × quantity |

Нет собственного поля единицы измерения — при необходимости (печатные
формы, `invoice_item.unit_name`) unit подтягивается по цепочке через
`calculation_id → Calculation.unit_id → Unit.name`, каждое звено
nullable, при обрыве — пустая строка без падения. Нет soft-delete —
строки полностью пересоздаются при каждом формировании (delete-all+
create-all).

### `firm` (справочник фирм-поставщиков — "Постачальник" в счёте)
| Поле | Тип | Назначение |
|---|---|---|
| id | int, PK | |
| full_name | str, default "" | |
| is_default | bool, default False, indexed | Управляется ТОЛЬКО через action-кнопку "Сделать по умолчанию", НЕ через обычное поле формы — Postgres отвергает пустую строку для boolean, отправляемую HTML-формой при unchecked чекбоксе |
| egrpou_code, tax_id, vat_certificate_number | str, default "" | ЄДРПОУ / ІПН / № свідоцтва платника ПДВ |
| bank_account, bank_name, bank_mfo | str, default "" | Р/р (IBAN) / Банк / МФО |
| phone, address | str, default "" | |
| is_deleted | bool, default False, indexed | |

### `invoice` (счёт-фактура)
| Поле | Тип | Назначение |
|---|---|---|
| id | int, PK | |
| document_number, document_date, document_time | | Номер по счётчику префикса "I" |
| request_id | int, FK→request.id, nullable | |
| specification_id | int, FK→specification.id, nullable | NULL после "Отвязать" — счёт остаётся как есть, просто больше не обновляется каскадом |
| firm_id | int, FK→firm.id, nullable | При создании — дефолтная Firm (`is_default=True`) |
| client_id | int, FK→client.id, nullable | Заказчик — снэпшот `Request.client_id` |
| client_invoice_id | int, FK→client.id, nullable | Плательщик; пусто → печатается "той самий" |
| total_excl_vat, vat_amount, total_incl_vat | float, default 0.0 | Пересчитываются по сумме `InvoiceItem.line_total` и ставке `constant.vat_rate` |
| is_frozen | bool, default False | Добавлено v96 (план "Перепроведение"). Переключается вручную кнопкой "Заморозить" (НЕ автоматически). Пока False — счёт при повторном "Создать счёт" на том же наборе калькуляций обновляется на месте; True — создаётся новый документ |
| is_deleted | bool, default False, indexed | |

Движок: `own_page_url="/invoice-v2"`, `invoice_items_tab` (построчная
таблица с редактируемой скидкой). Кнопки: «Обновить» (пересобрать
позиции из спецификации), «Отвязать от спецификации», «Скачать PDF»,
«Скачать Excel» (обе `client_side=True`, открывают
`/invoice-print/{id}/pdf|xlsx`), «Дать скидку» (bulk через
`window.prompt()`, применяет один `discount_percent` на все строки).

### `invoice_item` (строки счёта)
| Поле | Тип | Назначение |
|---|---|---|
| id | int, PK | |
| invoice_id | int, FK→invoice.id, nullable | |
| specification_item_id | int, FK→specificationitem.id, nullable | Только трассировка, ПУТЬ ЧЕРЕЗ СПЕЦИФИКАЦИЮ (уходящий) |
| calculation_id | int, FK→calculation.id, nullable | Добавлено v96 (план "Перепроведение"). НОВАЯ прямая трассировка, взамен пути через specification_item_id. Nullable, НЕ бэкфиллится — старые строки (созданные до v96 через Specification) остаются NULL, новые строки (создаваемые напрямую из отмеченных калькуляций заявки, минуя спецификацию) заполняют его при создании. Задача связать старые строки задним числом отложена до финального удаления Specification/SpecificationItem. Используется как ключ merge-логики при обновлении незамороженного счёта (сохранение discount_percent на совпавших позициях) |
| product_name | str, default "" | СНЭПШОТ ← `SpecificationItem.product_name` |
| unit_name | str, default "" | СНЭПШОТ единицы измерения. Добавлено v94 ПОСЛЕ первого деплоя таблицы — заполняется по цепочке `spec_item.calculation_id → Calculation.unit_id → Unit.name` при сборке/пересборке счёта. Существующие строки (созданные до v94) имеют `unit_name=""` — не тронуты, backfill не делался |
| quantity | float, default 1.0 | СНЭПШОТ |
| unit_price | float, default 0.0 | СНЭПШОТ, цена БЕЗ скидки |
| discount_percent | float, default 0.0 | ЕДИНСТВЕННОЕ редактируемое человеком поле строки. Знак: отрицательное = скидка, положительное = наценка |
| unit_price_after_discount | float, default 0.0 | РАСЧЁТНОЕ: `unit_price × (1 + discount_percent/100)` |
| line_total | float, default 0.0 | РАСЧЁТНОЕ: `unit_price_after_discount × quantity` |

Пересчёт `unit_price_after_discount`/`line_total` — на бэкенде при
каждом сохранении строки (`before_update_hook`), сервер — финальный
источник истины. Нет soft-delete — строки пересоздаются вместе со
всем счётом при пересборке (delete-all+create-all).

### `constant` (справочник констант)
| Поле | Тип | Назначение |
|---|---|---|
| id | int, PK | |
| key | str, unique, indexed | readonly в UI/API |
| value | str | Хранится строкой, тип приводится в коде использования |
| description | str, default "" | readonly |

Seed (`seed_constants()`, идемпотентен, `app/database.py`,
on_startup) включает как минимум: `vat_rate`, `default_page_size`,
`calculation_name_template`. Движок: `allow_create=False`,
`allow_delete=False` — только редактирование `value`.

### `document_counter` (служебная — общий счётчик номеров документов)
| Поле | Тип | Назначение |
|---|---|---|
| id | int, PK | |
| prefix | str, unique, indexed | "R" / "S" / "I" и т.п. |
| last_number | int, default 0 | |

Не в `ALL_TABLES` — нет своей страницы движка, используется только
внутри `document_numbering.py::next_document_number()`. Ручная правка
номера документа на бо́льшее значение подтягивает счётчик вверх.

---

## 3. Известные расхождения код ↔ спека / технический долг

| Что | В коде | Примечание |
|---|---|---|
| `app/models/__init__.py` | Не экспортирует все модели через `__all__` | Работает (движок импортирует напрямую из модулей), но неполный `__all__` может путать при будущих импортах "одной строкой" |
| `Brand.is_universal` | Отсутствует | Было в исходной спеке материалов (флаг спецбренда "Universal"), не реализовано, не поднималось с v48 |
| Старые `calculation`/`invoice_item` без `unit_id`/`unit_name` | `unit_id=NULL` / `unit_name=""` для записей, созданных до v91/v94 | Backfill сознательно не делался — Вахтанг пересоздаёт нужные документы вручную по необходимости |
| `purge_kit`/остальные `purge_*` | Не проверяют зависимости перед физическим удалением | Актуально пересмотреть при первом реальном инциденте с оборванной ссылкой |
| specification_item | Нет собственного поля unit | Решение: unit не дублируется на каждом уровне снимка, подтягивается по цепочке до `Calculation` только там, где реально нужен (invoice_item, печатные формы) |

Критерий принятия решения при расхождении код/спека (согласовано с
Вахтангом): приоритет — чистый, читаемый, универсальный, легко
расширяемый код; спецификация может быть неполной и подлежит правке,
если код лучше. Каждый случай обсуждается отдельно, не подгоняется
автоматически. Названия таблиц/полей/функций согласовываются с
Вахтангом до фиксации в коде — особенно когда английские термины
могут быть неоднозначны.

---

## 4. Статус реестра

Актуализирован по факту кода v94 (2026-08-31), в рамках наведения
порядка в документации проекта — этот файл теперь единственный
подробный технический реестр (файл `docs/HANDOFF_kits_and_calculation.md`
с историей проектирования удалён — весь спроектированный там
документооборот уже полностью закодирован, актуальные детали
перенесены сюда). `docs/HANDOFF.md` остаётся отдельным, короче и
живёт своей ролью — передача контекста между сессиями (что сделано в
последнем шаге, что открыто), не полный реестр сущностей.

Следующее обновление — тем же шагом, где меняется структура таблиц
или конфигурация движка (новое поле, новая таблица, новый
`TableConfig`-примитив) — не откладывать до отдельной "уборки", это и
привело к разрыву v48→v94.
