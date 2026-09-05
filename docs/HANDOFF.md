# HANDOFF

## Состояние

**v102 — первый проход зачистки Specification (после формального
завершения плана "Перепроведение" на v101).**

Активная цепочка документов сокращена до `request → calculation →
invoice`. Кнопка "Спецификация" на заявке и кнопка "Обновить" на
старых счетах — убраны из UI и движка. Таблицы `specification`/
`specification_item` в БД, поля `Invoice.specification_id`/
`InvoiceItem.specification_item_id` — намеренно НЕ тронуты (решение
Вахтанга: DROP откладывается до отдельного решения по 3-4 старым
счетам). Подробности и открытые вопросы — `docs/HANDOFF_specification_
cleanup.md` (файл для второго прохода).

## Сделано в этой сессии

1. **`app/engine/tables.py`**:
   - Удалён `_build_specification_handler` целиком.
   - Убраны `build_specification_1/2/3` из `action_handlers`
     request_table; кнопка "Спецификация" убрана из
     `row_actions`/`row_action_names` у `brand_slot_1/2/3_id` (осталась
     только "Пересчитать").
   - Удалены `_sync_invoice_items_from_specification` и
     `_refresh_invoice_items_handler`.
   - Убрана кнопка/handler `refresh_invoice_items` из
     `action_buttons`/`action_handlers` invoice_table.
   - `Invoice.specification_id` — `FieldConfig` теперь
     `in_list=False, in_form=False`, убран из `Relation`/`FormRow`.
   - `specification_table`/`specification_item_table` оставлены как
     есть (роуты `/specification-v2/*` продолжают работать напрямую).
   - Обновлены комментарии, описывавшие трёхзвенную цепочку.
2. **`app/engine/document_chain.py`** — убран
   `ChainLink(child_key="specification", ...)` из `CHAIN_LINKS`.
   `/documents-chain` больше не показывает уровень "Спецификации".
3. **`app/version.py`** — `APP_VERSION` v101 → v102; пункт меню
   "Спецификации" убран из `NAV_MENU`.
4. **`docs/HANDOFF_specification_cleanup.md`** — создан, чек-лист для
   второго прохода (DROP таблиц/полей, судьба 3-4 старых счетов,
   fallback в `invoice_print/data.py`).
5. **`entity_registry.md`** — раздел "Документооборот" переписан под
   новую цепочку, отмечено, что оставлено намеренно и почему.
6. Изменений в схеме БД нет — `_ensure_is_deleted_columns()` и
   `_drop_obsolete_columns()` не трогались.
7. Проверено локально (SQLite, `TestClient` context manager):
   - `/invoice-v2/new`, `/request-v2/new`, `/calculation-v2/new`,
     `/specification-v2/new`, `/documents-chain` — 200, без исключений;
   - HTML `/request-v2/new` не содержит рендер кнопки "Спецификация"
     (`>Спецификация<` отсутствует), POST на `build_specification_1`
     напрямую → 422 (не 500);
   - HTML `/invoice-v2/new` не содержит рендер кнопки "Обновить"
     (`refresh_invoice_items` нет среди `runAction()`), POST на
     `refresh_invoice_items` напрямую → 422 (не 500);
   - `toggle_frozen` по-прежнему работает (200);
   - создан тестовый СТАРЫЙ счёт (с заполненным `specification_id`,
     как в проде) — открывается на `/invoice-v2/{id}` без ошибок;
   - PDF и Excel печать этого старого счёта отрабатывают без ошибок
     (fallback через Specification в `invoice_print/data.py` не
     тронут и продолжает работать);
   - `/api/documents-chain/{request_id}` для заявки с этим старым
     invoice — группы `['request', 'calculation', 'invoice']`, без
     `specification`.

## Открыто

- Второй проход зачистки Specification (DROP таблиц/полей) — весь
  чек-лист и открытые вопросы в `docs/HANDOFF_specification_cleanup.md`.
  Ключевой вопрос: что делать с 3-4 старыми счетами, у которых
  `specification_id` заполнен, прежде чем можно будет убрать таблицы.
- Рефакторинг `enginePage()` — отдельная будущая сессия, не входит
  сюда.
