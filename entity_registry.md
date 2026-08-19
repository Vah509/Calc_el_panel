# Реестр сущностей — ЭлектроЩит

Единый источник правды по факту реального кода (не по плану из спеки).
Актуализирован под **v48** (2026-08-19) — заменяет собой прежние
`entity_registry_v1.md` (описывал ещё дошаговый CRUD «Шага 1», давно не
соответствовал коду) и `entity_registry_constants.md` (версия v26,
слился сюда). Обновляется тем же шагом, где менялся код.

Формат: сначала общая инфраструктура (движок, процессоры), затем каждая
таблица — данные / конфиг движка / примечания в одном месте.

---

## 1. Инфраструктура

### Файлы

```
app/
├── __init__.py
├── database.py         ← подключение к БД, get_session(), init_db(), seed_constants()
├── main.py              ← точка входа, регистрация роутеров движка + processors, /health
├── version.py            ← APP_VERSION, NAV_MENU (верхнее меню)
├── models/
│   ├── __init__.py        ← ⚠️ см. «Известные расхождения» ниже
│   ├── brand.py
│   ├── material.py
│   ├── constant.py
│   ├── kit_group.py
│   ├── kit_section.py
│   ├── kit.py
│   └── kit_item.py
├── engine/                ← универсальный CRUD/drill-down движок
│   ├── config.py            ← TableConfig, FieldConfig, Hierarchy, Relation, ComputedPair
│   ├── tables.py             ← экземпляры TableConfig для всех таблиц (ALL_TABLES)
│   ├── api.py               ← build_api_router() — универсальные REST-эндпоинты
│   ├── page.py               ← build_page_router() — HTML-страница (Alpine.js) + шаблон
│   ├── page_router.py          ← обвязка page.py в APIRouter
│   ├── register.py            ← регистрирует api+page роутеры для каждой ALL_TABLES записи
│   ├── formulas.py            ← вспомогательные формулы (ComputedPair пересчёт)
│   └── ENGINE.md              ← расширенная техническая документация движка (обновляется по запросу «свести документацию»)
├── processors/
│   ├── registry.py           ← PROCESSORS: recalc_material_vat + автосгенерированные purge_*
│   ├── page.py               ← HTML-страница /processors
│   └── router.py             ← роутинг страницы + запуск обработчика
├── static/style.css
└── templates/base.html         ← общий каркас, верхнее меню из NAV_MENU
```

Паттерн: 1 класс-таблица = 1 файл в `models/`. Вся CRUD/UI-логика — в
универсальном движке (`app/engine/`), не в отдельных роутерах на
таблицу — движок читает `TableConfig` и порождает REST + HTML сам.

### Универсальные REST-эндпоинты движка (на каждую таблицу из ALL_TABLES)

| Метод | Путь | Назначение |
|---|---|---|
| GET | `/api/{key}` | Список, поддерживает `parent_id` (drill-down), `q`/search-toggles, `page`/`page_size`, сортировку. Формат ответа: `{items, total, page, page_size, total_pages}` |
| POST | `/api/{key}` | Создать |
| PUT | `/api/{key}/{item_id}` | Обновить (readonly-поля в payload игнорируются) |
| DELETE | `/api/{key}/{item_id}` | Удалить — поведение зависит от `delete_mode` (см. ниже) |
| POST | `/api/{key}/{item_id}/copy` | Server-side копирование записи |
| PUT | `/api/{key}/{item_id}/items` | Полная замена дочерних записей (delete-all+create-all в одной транзакции) — используется `edit_mode="items_modal"` |
| POST | `/api/{key}/bulk-mark-delete` | Безусловная установка `is_deleted` для набора id (не toggle) — 422 для таблиц с `delete_mode != "soft"` |

HTML-страница: `GET {url_path}` (например `/material-v2`) — одна страница
на все уровни dril-down сразу (`config_json.levels[]`), без перезагрузки
между уровнями.

### `delete_mode` — три режима (см. `TableConfig.delete_mode`)

| Режим | Поведение DELETE | Таблицы |
|---|---|---|
| `"soft"` | Пометка `is_deleted=True`, физическое удаление — только через purge-processor | material, brand, kit |
| `"simple"` | Физическое удаление, но только если нет дочерних записей | kit_group, kit_section |
| `"hard"` (дефолт, если не указан) | Безусловное немедленное физическое удаление | kit_item |

### Processors (`/processors`)

- `recalc_material_vat` — пересчитывает `Material.price_incl_vat` по
  текущей ставке из `constant.vat_rate`.
- `purge_{table_key}` — автогенерируется для КАЖДОЙ таблицы с
  `delete_mode == "soft"` (сейчас: `purge_material`, `purge_brand`,
  `purge_kit`). Физически удаляет все строки с `is_deleted=True`.
  **⚠️ Без проверки зависимостей** — просто `session.delete()` по
  списку. Для `purge_kit` это значит: если на момент запуска
  обработчика на удалённый kit уже будут ссылаться `calculation_item`
  (появятся в следующем крупном блоке), физическое удаление снесёт
  ссылку без предупреждения. Отмечено в коде как известное упрощение
  («более сложную проверку допишем отдельным шагом, когда появится
  реальная потребность») — актуально пересмотреть, как только
  calculation_item будет существовать.

---

## 2. Таблицы

### `brand`
| Поле | Тип | Назначение |
|---|---|---|
| id | int, PK | |
| name | str, unique, indexed | Название бренда |
| rate_vb | float, default 0.0 | Курс валюты поставщика (EUR/USD→грн), правится вручную. Используется калькуляцией (когда появится) вместе с `Material.price_vb_incl_vat` |
| is_deleted | bool, default False, indexed | Soft-delete пометка |

Движок: `delete_mode="soft"`. Поля в форме/списке: `name`, `rate_vb`.

⚠️ Спека предполагала ещё `is_universal` (флаг спецбренда «Universal»
для непривязанных к производителю компонентов) — в коде этого поля
по-прежнему нет.

### `material`
| Поле | Тип | Назначение |
|---|---|---|
| id | int, PK | |
| short_name | str, indexed | Короткое имя (поиск, списки) |
| full_name | str | Полное имя (для документов) |
| brand_id | int, FK→brand.id, nullable | |
| sku_article | str, indexed, nullable | Артикул производителя |
| price_excl_vat | float | Цена без НДС |
| price_incl_vat | float | Цена с НДС (взаимный пересчёт с price_excl_vat через `ComputedPair`, ставка — живая ссылка на `constant.vat_rate`) |
| price_vb_incl_vat | float, default 0.0 | Цена с НДС в валюте бренда-поставщика. Независимый факт, не авто-пересчитывается; связь с `Brand.rate_vb` считается «на лету» только в будущей калькуляции |
| owner_id | int, indexed, nullable | Задел под многопользовательскую модель, пока не используется |
| is_deleted | bool, default False, indexed | Soft-delete |

Движок: `delete_mode="soft"`, `enable_search_toggles=True` (поиск по
short_name/full_name/sku_article с переключателями полей).

⚠️ `vat_rate` как поле модели **удалён** (v28) — ставка теперь общая,
только в `constant.vat_rate`. Есть пометка «удалить физически колонку
`vat_rate` из таблицы на Railway» — открытый ручной шаг, ждёт
подтверждения после пересчёта реальных данных (см. `docs/HANDOFF.md`,
блок «Ждёт ручного действия от Вахтанга»).

### `constant`
| Поле | Тип | Назначение |
|---|---|---|
| id | int, PK | |
| key | str, unique, indexed | Ключ (readonly в UI/API) |
| value | str | Значение, хранится строкой, тип приводится в коде использования |
| description | str, default "" | Пояснение (readonly) |

Seed (`seed_constants()`, идемпотентен, `app/database.py`, on_startup):
- `vat_rate = "20"`
- `default_page_size = "100"`

Движок: `allow_create=False`, `allow_delete=False` — записи только
редактируются (`value`), не создаются/не удаляются через UI. Нет
панели выделения (allow_create=False).

### `kit_group` (1-й уровень дерева комплектов)
| Поле | Тип | Назначение |
|---|---|---|
| id | int, PK | |
| name | str, unique, indexed | |
| sort_order | int, default 0 | Порядок обхода в UI (не алфавитный — важен для рабочего процесса) |
| is_deleted | bool, default False, indexed | |

Движок: `delete_mode="simple"` (физическое удаление, только если нет
дочерних kit_section), `hierarchy=Hierarchy(child_key="kit_section")`.

### `kit_section` (2-й уровень)
| Поле | Тип | Назначение |
|---|---|---|
| id | int, PK | |
| name | str, indexed | |
| sort_order | int, default 0 | Порядок внутри своей группы |
| kit_group_id | int, FK→kit_group.id, nullable | |
| is_deleted | bool, default False, indexed | |

Движок: `delete_mode="simple"`,
`hierarchy=Hierarchy(parent_field="kit_group_id", parent_key="kit_group", child_key="kit")`.

### `kit` (3-й, нижний уровень дерева)
| Поле | Тип | Назначение |
|---|---|---|
| id | int, PK | |
| name | str, indexed | |
| sort_order | int, default 0 | |
| kit_section_id | int, FK→kit_section.id, nullable | |
| is_deleted | bool, default False, indexed | |

Движок: `delete_mode="soft"` (в отличие от group/section — на kit в
будущем ссылаются `calculation_item`, нужен purge с пометкой, не
безусловное physical-if-no-children), `edit_mode="items_modal"`,
`items_source_table_key="kit_item"`,
`hierarchy=Hierarchy(parent_field="kit_section_id", parent_key="kit_section")`
(без `child_key` — это последний уровень дерева; состав — не дочерний
уровень, а модалка).

Открытие карточки: клик по строке → модалка просмотра состава →
кнопка «Редактировать» → полноэкранный **MaterialPicker** (черновик
состава, сохранение — `PUT /api/kit/{id}/items`, полная замена).
Переименование — отдельная иконка ✎ в строке дерева. Поддерживает
выделение чекбоксом + групповые операции (пометка/снятие, копирование
одного выделенного комплекта со всем составом через
`POST /api/kit/{id}/copy`).

### `kit_item` (состав комплекта)
| Поле | Тип | Назначение |
|---|---|---|
| id | int, PK | |
| kit_id | int, FK→kit.id, nullable | |
| material_id | int, FK→material.id, nullable | |
| quantity | float, default 1.0 | Не int — дробные количества (метры кабеля/ленты) |

Движок: `delete_mode` не указан → дефолт `"hard"` (безусловное
немедленное физическое удаление, без пометки — обосновано тем, что
ничто не ссылается на конкретный `kit_item` напрямую: калькуляция
хранит ссылку только на `kit_id` и разворачивает состав live).
`hierarchy=Hierarchy(parent_field="kit_id", parent_key="kit")` — без
`child_key`, используется исключительно ради `parent_id`-фильтра в
`GET /api/kit_item?parent_id={kit_id}`. Не отдельная страница/пункт
меню — доступна только через модалку/MaterialPicker таблицы `kit`.
Дубликаты `material_id` в рамках одного kit допустимы (не суммируются).

---

## 3. Известные расхождения код ↔ спека / прочий техдолг

| Что | В коде | Примечание |
|---|---|---|
| `app/models/__init__.py` | Экспортирует только `Brand`, `Material` (`__all__ = ["Brand", "Material"]`) | Kit/KitGroup/KitSection/KitItem/Constant не добавлены в `__init__.py`, хотя используются в движке напрямую через собственные модули — работает, но неполный `__all__` может путать при будущих импортах «одной строкой». Не блокирует ничего, править по мере необходимости |
| Имя поля артикула | `sku_article` | Спека когда-то предлагала `sku` — решено в пользу кода как более читабельного (зафиксировано ранее) |
| Структура моделей | `models/` — папка, файл на класс | Читабельнее на текущем масштабе (7 таблиц), решено ранее |
| `Brand.is_universal` | Отсутствует в коде | Было в исходной спеке материалов, не реализовано, не поднималось с тех пор |
| `Material.vat_rate` (колонка в БД, Railway) | Поле удалено из модели (v28), но физическая колонка в БД Railway ещё не дропнута | Ждёт ручного `ALTER TABLE material DROP COLUMN vat_rate;` от Вахтанга после проверки пересчёта реальных данных |
| `purge_kit` | Не проверяет зависимости перед физическим удалением | См. раздел 1 «Processors» выше — актуально пересмотреть с появлением `calculation_item` |

Критерий принятия решения при расхождении код/спека (согласовано с
Вахтангом): приоритет — чистый, читаемый, универсальный, легко
расширяемый код; спецификация может быть неполной и подлежит правке,
если код лучше. Каждый случай обсуждается отдельно, не подгоняется
автоматически.

---

## 4. Статус реестра

Актуализирован по факту кода v48 (2026-08-19), перед стартом работы над
`zayavka`/`calculation` (см. `docs/HANDOFF_kits_and_calculation.md`,
раздел 2). Следующее обновление — по факту кодирования `zayavka` (шаг 1
из раздела 2.1 того файла), тем же шагом, где будет меняться код —
пункт, который в прошлый раз выпал из процесса и привёл к сильному
устареванию; держать этот файл в ногу с каждым значимым архивом.
