# HANDOFF

## Состояние

**v105 — второй проход зачистки Specification: физическое удаление
(за один шаг, без бэкфилла).**

Вахтанг подтвердил, что в БД на момент этой сессии не было ни одного
`Invoice` — бэкфилл `InvoiceItem.calculation_id` и осторожная
миграция старых строк, которые планировались в
`docs/HANDOFF_specification_cleanup.md`, оказались не нужны. Сделано
сразу и полностью: код, модели, поля и сами таблицы Specification/
SpecificationItem удалены в одну сессию.

Активная и единственная цепочка документов: `request → calculation →
invoice`.

## Сделано в этой сессии

1. **`app/invoice_print/data.py`** — убран fallback-путь через
   Specification (`InvoiceItem.specification_item_id →
   SpecificationItem → Calculation.unit_id → Unit.name`). Единица
   измерения строки теперь читается напрямую из уже готового поля
   `InvoiceItem.unit_name` (снэпшот, заполняется из
   `Calculation.unit_id → Unit.name` при создании строки в
   `_build_invoice_from_slot_handler`). Убран импорт
   `SpecificationItem`/`Calculation`/`Unit` — они здесь больше не
   нужны.
2. **`app/models/invoice.py`** — поле `specification_id` удалено из
   модели. Шапка комментария переписана под единственную актуальную
   цепочку (упоминания Specification убраны).
3. **`app/models/invoice_item.py`** — поле `specification_item_id`
   удалено из модели. Комментарии переписаны: `calculation_id` теперь
   описан как единственная и живая трассировка строки счёта.
4. **`app/engine/tables.py`**:
   - `specification_table`/`specification_item_table` (оба
     `TableConfig`) удалены целиком.
   - Импорты `Specification`/`SpecificationItem` убраны.
   - `FieldConfig(name="specification_id", ...)` убран из
     `invoice_table`, `FieldConfig(name="specification_item_id", ...)`
     убран из `invoice_item_table`.
   - `specification_id=None` убран из создания `Invoice` в
     `_build_invoice_from_slot_handler`.
   - Оба ключа убраны из `ALL_TABLES`.
5. **`app/engine/document_chain.py`** — комментарии над `CHAIN_LINKS`
   обновлены (сама логика уже не содержала Specification с v102).
6. **`app/database.py`**:
   - `_drop_obsolete_columns()` — добавлены
     `("invoice", "specification_id")` и
     `("invoiceitem", "specification_item_id")`.
   - Новая функция `_drop_obsolete_tables()` — `DROP TABLE IF EXISTS
     specificationitem CASCADE`, затем `DROP TABLE IF EXISTS
     specification CASCADE` (дочерняя первая, из-за FK). Вызывается
     из `init_db()` после `_drop_obsolete_columns()`.
7. **Удалены файлы** `app/models/specification.py`,
   `app/models/specification_item.py`.
8. **`app/version.py`** — `APP_VERSION` v104 → v105.
9. **`entity_registry.md`** — разделы "Документооборот", "delete_mode",
   "Processors", "Печатные формы счёта" переписаны под финальное
   состояние (Specification нигде не упоминается как существующая
   сущность, только в истории).
10. Проверено локально (SQLite, `TestClient` context manager):
    - `/invoice-v2/new`, `/request-v2/new`, `/calculation-v2/new`,
      `/documents-chain`, `/processors` — все 200.
    - `/specification-v2/new` — теперь корректно 404 (таблица больше
      не зарегистрирована в `ALL_TABLES`).
    - Полный сквозной сценарий: создание `Request` + `Calculation` с
      `unit_id` → `POST /api/request/{id}/actions/build_invoice_slot_1`
      → `Invoice` создан, `InvoiceItem.unit_name` корректно заполнен
      напрямую из калькуляции, `calculation_id` заполнен → `GET
      /invoice-print/{id}/pdf` — 200, без исключений.
    - Импорты моделей `Specification`/`SpecificationItem` нигде в
      коде больше не встречаются (проверено `grep` по всему `app/`).

## Открыто

- `ENGINE.md` — НЕ обновлялся (там ещё старые упоминания
  `specification` в примерах) — по правилу проекта обновляется
  только по явному запросу "свести документацию", не входит в эту
  сессию.
- Рефакторинг `enginePage()` — отдельная будущая сессия, не входит
  сюда.
- Обработчики `purge_*` пока без проверки зависимостей ВНЕ дерева
  иерархии — отложено до реальной потребности.
- `docs/HANDOFF_specification_cleanup.md` теперь полностью закрыт
  (весь чек-лист выполнен) — можно удалить файл в следующую сессию,
  если Вахтанг подтвердит, что он больше не нужен как история.
