# HANDOFF

## Состояние

**v86 — счёт (invoice) как четвёртый документ цепочки.**

zayavka -> calculation -> specification -> **invoice** (счёт-фактура,
образец печатной формы — СФ-0000040, обсуждение 2026-08-29). Кнопка
«Создать счёт» — на карточке спецификации. Полный цикл проверен
TestClient: создание фирмы, создание счёта из спецификации,
построчная скидка/наценка, кнопка «Дать скидку» на все строки разом,
отвязка от спецификации, повторное создание счёта из той же (уже
изменённой) спецификации создаёт НОВЫЙ документ. Печатная форма (сам
бланк по образцу) — ЕЩЁ НЕ СДЕЛАНА, это только редактируемая карточка
документа.

## Сделано в этой сессии

- **Новые модели**: `app/models/firm.py` (справочник СВОИХ юрлиц-
  продавцов — полное название, ЄДРПОУ, ІПН, № свідоцтва ПДВ, банковские
  реквизиты, телефон, адрес, `is_default`), `app/models/invoice.py`
  (шапка счёта), `app/models/invoice_item.py` (строки счёта, снэпшот +
  редактируемая `discount_percent`). Подробная механика — в docstring-
  комментариях каждого файла, там же зафиксированы решения Вахтанга
  из обсуждения.
- **Новый универсальный примитив движка** `invoice_items_tab` (по
  аналогии с `readonly_items_tab` из v85, но с ОДНИМ редактируемым
  полем на строку — скидка) — `app/engine/config.py`:
  `invoice_items_tab` / `invoice_items_table_key` /
  `invoice_items_columns` / `invoice_items_discount_field` /
  `invoice_items_price_field` / `invoice_items_price_after_discount_
  field` / `invoice_items_line_total_field` / `invoice_items_sum_field`
  / `invoice_items_bulk_discount_action`.
- **`app/engine/api.py`**: `POST /{item_id}/actions/{action}` теперь
  ПРИНИМАЕТ необязательный JSON-body (`payload`) — нужен для «Дать
  скидку» (единственное действие в движке, которому нужны данные от
  человека, не только id записи). Обратная совместимость: payload
  передаётся обработчику, только если тот объявлен с 3-м позиционным
  параметром (проверка через `handler.__code__.co_argcount`) —
  существующие `action_handlers` (recalc_full_name и т.д.) не тронуты.
- **`app/engine/tables.py`**:
  - `_sync_invoice_items_from_specification` — полная перезапись
    InvoiceItem по текущим SpecificationItem (delete-all+create-all,
    как и у `_build_specification_handler`)
  - `_recalculate_invoice_totals` — Σ InvoiceItem.line_total +
    constants['vat_rate']
  - `_build_invoice_handler` (кнопка «Создать счёт» на спецификации):
    ищет НЕ отвязанный Invoice по `specification_id`, если нет —
    создаёт новый (firm = is_default, client_invoice_id = Request.
    client_invoice_id ИЛИ Request.client_id), в обоих случаях
    синхронизирует строки и пересчитывает итоги
  - `_unlink_invoice_handler` (кнопка «Отвязать от спецификации») —
    сбрасывает ТОЛЬКО specification_id, request_id и все данные счёта
    остаются
  - `_refresh_invoice_items_handler` (кнопка «Обновить») — пока
    привязан, перечитывает строки заново
  - `_apply_bulk_discount_handler` (кнопка «Дать скидку», payload=
    {"discount_percent": число}) — перезаписывает ВСЕ строки
    одинаковым значением, включая уже изменённые вручную (решение
    Вахтанга: без исключений)
  - `_recalc_invoice_item_before_update` (`before_update_hook` у
    `invoice_item_table`) — при обычном PUT одной строки (правка
    скидки прямо в таблице) пересчитывает unit_price_after_discount/
    line_total строки И итоги шапки счёта (важно: без этого правка
    ОДНОЙ строки не обновляла бы «Разом без ПДВ» до нажатия «Дать
    скидку»/«Обновить» — исправлено сразу в этой же сессии после
    обнаружения тестом)
  - `_set_default_firm_handler` — кнопка «Сделать по умолчанию» на
    firm (is_default НЕ обычное FieldConfig-поле — движок не умеет
    коэрсить bool из `<select>`/`<radio>`, та же логика, что у
    is_deleted; отдельная кнопка снимает флаг со всех остальных фирм)
  - `firm_table`, `invoice_table`, `invoice_item_table` — новые
    TableConfig, добавлены в `ALL_TABLES`
  - `specification_table` — добавлена `ActionButton(action=
    "build_invoice", label="Создать счёт")`
- **`app/engine/document_chain.py`** — `ChainLink(child_key="invoice",
  parent_key="request", fk_field="request_id")`. specification_id у
  Invoice сознательно НЕ зарегистрирован отдельным ChainLink (nullable,
  может быть отвязан) — цепочка обходится только через request_id.
- **`app/engine/page.py`**:
  - HTML-блок `invoice_items_tab` (параллельно `readonly_items_tab`) —
    таблица строк с редактируемым `<input>` скидки на каждой строке +
    кнопка «Дать скидку» сверху
  - JS: `invoiceItemDiscountChanged(row)` (PUT одной строки),
    `invoiceItemsRefreshTotals()` (перечитывает шапку после правки),
    `invoiceItemsApplyBulkDiscount()` (`window.prompt()` + POST на
    action с payload); `loadReadonlyItems()` доработан — читает
    `CONFIG.invoiceItemsTableKey` как fallback к `readonlyItemsTableKey`
  - Новые ключи в CONFIG: `invoiceItemsTab`, `invoiceItemsTableKey`,
    `invoiceItemsDiscountField`, `invoiceItemsPriceField`,
    `invoiceItemsPriceAfterDiscountField`, `invoiceItemsLineTotalField`,
    `invoiceItemsSumField`, `invoiceItemsBulkDiscountAction`
- **`app/static/style.css`** — `.invoice-discount-input`
- **`app/version.py`** — `APP_VERSION = "v86"`, меню: «Счета» (в
  «Документы»), «Наши фирмы» (в «Справочники»)
- **Тест (ad hoc, TestClient, sqlite)**: полный цикл фирма → клиент →
  заявка → калькуляция (final_total=1000) → спецификация → счёт;
  проверено арифметически: скидка -10% → 900.00, наценка +10% →
  1100.00 (после фикса — итоги шапки: 1100 excl / 220 VAT (20%) / 1320
  incl); кнопка «Дать скидку» перезаписывает все строки; отвязка +
  повторное «Создать счёт» из той же спецификации создаёт ВТОРОЙ,
  отдельный документ (id 1 ≠ id 2); `/api/documents-chain/{request_id}`
  показывает группу `invoice` с обоими счетами. Страницы `/invoice-v2`,
  `/firm-v2` рендерятся без ошибок (200, непустой HTML).

## Открыто

- **Печатная форма счёта** (реальный бланк по образцу СФ-0000040 —
  Постачальник/Одержувач/Платник в шапке, таблица, пропись суммы) —
  ЕЩЁ НЕ СДЕЛАНА. Сейчас есть только карточка редактирования (форма
  движка), не документ для печати/PDF. Обсудить формат вывода (HTML
  для печати из браузера? PDF-экспорт? когда переходить к
  Excel/PDF-экспорту по общему пункту дорожной карты) отдельно.
- **`is_default` у Firm выведен как readonly-текст** (`True`/`False`
  без перевода) в списке/форме — работает, но некрасиво. Можно
  доделать позже отдельным движковым примитивом для boolean-полей
  (сейчас в движке в принципе нет универсального способа показать/
  редактировать `bool`-поле модели через обычный FieldConfig — то же
  ограничение обошли и здесь, и раньше у is_deleted через спецкейс).
- **Не проверено на реальном устройстве** — вся проверка пока только
  TestClient/sqlite локально в контейнере, живого Railway-деплоя с
  Postgres не было в этой сессии.
- Пункты 2–4 дорожной карты (ценообразование/актуализация цен,
  «перепроведение» остальных документов, Excel/PDF-экспорт) — не
  начаты.
- Рефакторинг `enginePage()` — по-прежнему сознательно отложен.
