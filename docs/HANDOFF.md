# HANDOFF

## Состояние

**v75 — форма документа переведена с модалки на отдельную полноэкранную
страницу для плоских типов документов (request, calculation).**

Раньше (v73-v74) список и форма редактирования жили на одном URL —
форма была модалкой поверх списка. Теперь для таблиц с заданным
`own_page_url` (сейчас: request, calculation) действует новая схема:

- `/{key}-v2` — ТОЛЬКО список, без модалки в разметке вообще
- `/{key}-v2/new` — форма создания на весь экран
- `/{key}-v2/{id}` — форма редактирования на весь экран

Клик по строке списка и кнопка "+ Запись" теперь ПЕРЕХОДЯТ на форму
(полная перезагрузка), а не открывают модалку на месте. "Закрыть"/
после "Сохранить"/после "Удалить" на форме делают `history.back()` —
человек возвращается туда, откуда реально пришёл (свой журнал, чужой
журнал через "Создать документ на основании", или страница "Цепочка
документов" — путь назад везде общий, без хардкода одного URL
возврата).

Таблицы БЕЗ `own_page_url` (material, brand, client, unit, constant,
kit_group и вся hierarchy) продолжают работать по-старому — список +
модалка на одном URL, ничего не изменилось. Флаг `render_mode`
("both"/"list"/"form") в `render_table_page()` управляет тем, какая
часть общего Jinja-шаблона рендерится; hierarchy-таблицы всегда
получают "both" независимо от переданного значения.

**Цепочка документов** (`app/documents_chain/`) обновлена: клик по
строке теперь ведёт на `own_page_url + '/' + id` (путь) вместо
`?open_id=` (query, было временным решением v74).

**Копирование** (`copySelected()` на списке) для таблиц с
`own_page_url` больше не может выставить `this.editing` напрямую (на
странице списка формы в разметке нет) — вместо этого данные копии
кладутся в `sessionStorage` под ключом `engineCopyPrefill:{key}`,
переход на `/new`, а форма читает и сразу удаляет этот ключ при
открытии (`maybeOpenOwnPage()`).

**"Создать документ на основании"** (`createChildDocument()`) теперь
ведёт на `.../new?from_request={id}` вместо `...?from_request={id}` —
путь `/new` появился, `?from_request=` остался как query-параметр,
обрабатывается внутри `maybeOpenOwnPage()` на ветке `new`.

## Сделано в этой сессии

- `app/engine/page.py`:
  - `_PAGE_TEMPLATE_SOURCE` — список обёрнут в `{% if render_mode != 'form' %}`, модалка — в `{% if render_mode != 'list' %}`; на `render_mode == 'form'` (и НЕ hierarchy) модалка рендерится full-screen (inline-стили вместо оверлея)
  - Новый мини-topbar с кнопкой "← К цепочке" на form-страницах (раньше кнопка была только в общем topbar списка, который на form-странице больше не рендерится)
  - `render_table_page()` принимает `render_mode` (default `"both"`, hierarchy всегда форсирует `"both"`)
  - `config_json` получил `renderMode`; `_serialize_level_config()` — `ownPageUrl` (из `config.own_page_url`)
  - Новые JS-функции: `openDocumentRow()`, `openCreateRow()`, `maybeOpenOwnPage()`, `closeToList()`
  - `copySelected()` — новая ветка для таблиц с `ownPageUrl` (sessionStorage-префилл + переход на `/new`)
  - `close()`/`save()`/`remove()` — вызывают `closeToList()` вместо `modalOpen=false` когда `CONFIG.renderMode === 'form'`
  - `createChildDocument()` — URL с `/new`
  - `maybeOpenById()` (v74) заменена на `maybeOpenOwnPage()` — читает id из ПУТИ, а не query
- `app/engine/page_router.py` — `build_page_router()` регистрирует ТРИ роута для таблиц с `own_page_url` (list/new/{id}), один роут как раньше — для остальных
- `app/engine/register.py` — защитная проверка на старте: `own_page_url` должен совпадать с фактическим `url_path`, иначе `ValueError` при регистрации
- `app/documents_chain/page.py` — `openDocument()` использует новый путь `own_page_url + '/' + id` вместо `?open_id=`
- Тестирование:
  - `TestClient`: все страницы (list/new/{id} для request и calculation, material/brand/client/unit/constant, kit_group, documents-chain, `from_request` сценарий) — 200 OK
  - Проверено, что список и форма РЕАЛЬНО разделены в разметке (`modal-backdrop`/`<table` присутствуют в правильных, не смешанных комбинациях)
  - Проверено, что `material-v2` (без `own_page_url`) не затронут — список+модалка по-прежнему на одной странице
  - `node --check` — синтаксис извлечённого JS корректен на всех 4 типах страниц (list/form/chain/hierarchy)
  - Изолированные unit-тесты в node (мок `window`/`fetch`/`sessionStorage`) на ключевую логику: разбор последнего сегмента пути, `chain_request_id`, sessionStorage round-trip, `closeToList()` (оба случая: `history.back()` и fallback)
  - Базовый CRUD через API (create/update/get/delete) — не задет
- Новых полей моделей НЕ добавлялось — миграций не требуется

## Открыто

- Не проверено на реальном устройстве (только TestClient/SQLite + изолированные node-тесты) — сама интерактивность (клики, реальные переходы браузера, визуальное расположение кнопок) не проверялась вживую
- Дублирование заголовка на form-странице: мини-topbar показывает "{Тип документа}" (например "Заявка"), а `.modal-header` внутри показывает "Редактирование"/"Новая запись" — не проверено визуально, не выглядит ли это избыточным на экране телефона
- `specification`/`invoice` по-прежнему не реализованы — когда появятся, потребуется задать им `own_page_url` в `TableConfig` для попадания в новую схему (иначе останутся на старой список+модалка схеме, что тоже допустимо, если так решим)
- Drill-down таблицы (kit_group/kit_section/kit) сознательно НЕ переведены на отдельные страницы — по договорённости с Вахтангом это осталось вне рамок задачи
