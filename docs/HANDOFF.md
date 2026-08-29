# HANDOFF

## Состояние

**v85 — табличная часть спецификации (строки на карточке документа).**

После v84 (фикс FK-бага) спецификации собираются стабильно, но карточка
`/specification-v2/{id}` показывала только шапку с итоговой суммой —
сами позиции (SpecificationItem) существовали в БД, но нигде не
отображались. v85 добавляет таблицу строк прямо на форму.

## Сделано в этой сессии

- **Новый универсальный примитив движка** (по прямой просьбе Вахтанга —
  "может пригодиться и для счёта", не одноразовый хак под
  specification): `TableConfig.readonly_items_tab` /
  `readonly_items_table_key` / `readonly_items_columns` /
  `readonly_items_sum_field` (app/engine/config.py). Рендерит ПРОСТОЙ
  read-only список дочерних строк — без единого интерактивного
  элемента (не путать с materials_tab/kits_tab — там есть добавление/
  удаление/инлайн-редактирование количества). Для таблиц без
  `form_tabs` (как specification) рендерится безусловно в обычной
  (не-вкладочной) ветке формы.
- `app/engine/tables.py`, `specification_table`: добавлены
  `extra_lookups=["calculation"]` (нужен для колонки "Калькуляция" —
  document_number по calculation_id, без похода на сервер) и
  `readonly_items_tab="Позиции"` / `readonly_items_table_key=
  "specification_item"` / `readonly_items_columns` = [Калькуляция,
  Изделие, Кол-во, Цена за ед., Итого] / `readonly_items_sum_field=
  "total_amount"`.
- `app/engine/page.py`:
  - Jinja-блок таблицы строк в не-вкладочной ветке формы (там же, где
    `render_form_rows(form_layout_by_tab[''])`) — `<table
    class="readonly-items-table">`, колонки из
    `config.readonly_items_columns`, строка "Итого" снизу из
    `readonly_items_sum_field`
  - JS: `readonlyItems` (state), `loadReadonlyItems()` (тот же
    parent_id-механизм, что и `loadMaterialsItems()`, без фильтрации —
    таблица однородна), `readonlyItemsColumnValue(row, fieldName,
    format)` — читает поле row напрямую ("text"/"money" форматы) ЛИБО,
    для специального поля `"calculation_number"`, ищет
    document_number калькуляции в уже загруженном
    `relationOptions.calculation` по `row.calculation_id`
  - `openEdit()` — вызывает `loadReadonlyItems()`, когда
    `CONFIG.readonlyItemsTab && editing.id` (та же точка входа
    отрабатывает и для full-page форм типа specification — они внутри
    вызывают тот же `openEdit()` через `maybeOpenOwnPage()`)
  - Новые ключи в CONFIG: `readonlyItemsTab`, `readonlyItemsTableKey`
- `app/static/style.css` — `.readonly-items-table`/`.readonly-items-
  total`/`.readonly-items-empty` (простой стиль таблицы, не
  переиспользует `.materials-row` — та разметка несёт интерактивные
  элементы)
- Тест (ad hoc, TestClient): создал заявку+калькуляцию, вызвал
  `build_specification_1`, открыл `/specification-v2/{id}` — HTML
  содержит `readonly-items-table`, цикл `x-for="row in
  readonlyItems"`, заголовок колонки "Калькуляция", блок
  `readonly-items-total`. Отдельно проверил
  `GET /api/specification_item?parent_id=` — строка возвращается с
  верными `unit_price`/`quantity`/`line_total` (100 × 2 = 200).
- `app/version.py` — `APP_VERSION = "v85"`

## Открыто

- **Проверить на реальном устройстве**: открыть S-000009/S-000010 у
  заявки R-000009 — убедиться, что таблица строк отображается с
  правильными калькуляциями/суммами, и что "Итого" совпадает с шапкой
- v83 (автопересчёт стоимости на клиенте) — всё ещё не проверен
  вживую на устройстве
- Рефакторинг `enginePage()` — по-прежнему сознательно отложен
- `invoice`, ценообразование, «перепроведение» остальных документов,
  Excel/PDF — не начаты. `invoice` теперь может переиспользовать
  `readonly_items_tab`, если его строки тоже окажутся снэпшотом
  (решать отдельно на сессии по счёту)
