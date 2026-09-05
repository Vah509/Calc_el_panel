# HANDOFF: зачистка Specification — второй проход

Первый проход (v102, 2026-09-05) убрал участие Specification из
активной цепочки документов и UI — код-уровень. Таблицы БД и поля-FK
намеренно НЕ тронуты. Этот файл — чек-лист для второго прохода, когда
Вахтанг даст отдельное явное решение (после того как разберётся с
документами в базе).

## Что уже сделано (первый проход, v102)

- `_build_specification_handler` — удалён целиком (кнопка
  "Спецификация" на брендовых слотах заявки).
- `_sync_invoice_items_from_specification` /
  `_refresh_invoice_items_handler` — удалены (кнопка "Обновить" на
  счёте, работала только для счетов с заполненным `specification_id`).
- Пункт меню "Спецификации" — убран из `NAV_MENU` (`app/version.py`).
- `ChainLink(child_key="specification", ...)` — убран из
  `CHAIN_LINKS` (`app/engine/document_chain.py`) — `/documents-chain`
  больше не показывает уровень спецификаций.
- `Invoice.specification_id` — `FieldConfig` изменён на
  `in_list=False, in_form=False`, убран из `Relation`/`FormRow` в
  `invoice_table`. Поле физически осталось в модели/БД.
- Комментарии, описывающие цепочку как `request -> calculation ->
  specification -> invoice`, поправлены на `request -> calculation ->
  invoice` в основных местах (`tables.py`, `entity_registry.md`).

## Что сознательно НЕ тронуто в первом проходе

1. **Таблицы `specification` / `specificationitem` в БД** — существуют
   как были, ничего не удалено, DROP не выполнялся.
2. **`specification_table` / `specification_item_table`** в
   `app/engine/tables.py` — остаются зарегистрированными в
   `ALL_TABLES`. Роуты `/specification-v2/*` по-прежнему работают —
   это единственный способ посмотреть старые спецификации (не через
   удалённую кнопку "Спецификация", а прямым переходом по URL или из
   списка `/specification-v2`, если кто-то туда зайдёт напрямую).
3. **`Invoice.specification_id`** — поле модели осталось, значение в
   БД не трогалось. Скрыто из UI, но всё ещё читается кодом печати
   (см. п.4).
4. **`InvoiceItem.specification_item_id`** — поле модели осталось
   (было и раньше `in_list=False, in_form=False`, без изменений).
5. **`app/invoice_print/data.py`** — fallback-путь для получения
   единицы измерения строки через `InvoiceItem.specification_item_id
   → SpecificationItem → Calculation.unit_id → Unit.name` НЕ убран.
   Это единственный работающий путь для СТАРЫХ счетов (те самые 3-4,
   по оценке Вахтанга) — их `InvoiceItem.unit_name` мог быть пустым,
   т.к. поле `unit_name` на `InvoiceItem` появилось позже (v94/v96).
   Удалять эту функцию нельзя, пока эти счета не проверены/не
   исправлены — иначе PDF/Excel печать старых счетов может показывать
   пустую колонку "Од.".

## Открытые вопросы для второго прохода (решает Вахтанг)

1. **Судьба 3-4 старых Invoice с заполненным `specification_id`.**
   Варианты:
   - оставить архивом навсегда, ничего не трогать (просто убедиться,
     что печать продолжает работать через fallback);
   - разово забэкфиллить `InvoiceItem.unit_name` для этих счетов из
     старой цепочки (через `SpecificationItem`/`Calculation`), после
     чего fallback в `invoice_print/data.py` можно будет убрать;
   - что-то ещё, зависит от того, что именно Вахтанг имел в виду про
     "есть ещё какие-то задачи по документам".
2. **DROP TABLE specification / specificationitem** — только после
   решения по п.1 и явного подтверждения Вахтанга (необратимая
   операция на Postgres). Порядок при выполнении:
   a. Убедиться, что ни один активный код-путь (включая
      `invoice_print/data.py`) больше не читает эти таблицы.
   b. Убрать `Invoice.specification_id` и
      `InvoiceItem.specification_item_id` из моделей.
   c. Добавить обе колонки в `_drop_obsolete_columns()`
      (`app/database.py`) с `ALTER TABLE ... DROP COLUMN IF EXISTS`.
   d. Убрать `specification_table`/`specification_item_table` из
      `app/engine/tables.py` и из `ALL_TABLES` — `/specification-v2/*`
      перестанут открываться (ожидаемо).
   e. Убрать модели `app/models/specification.py`,
      `app/models/specification_item.py` — но ТОЛЬКО после того, как
      `SQLModel.metadata.create_all()` для них больше нигде не
      вызывается (иначе на старте будет ошибка отсутствующей модели
      при попытке движка её найти).
   f. Дропнуть сами таблицы через миграцию/явный DDL при старте
      (`_drop_obsolete_columns()` или отдельный разовый скрипт —
      обсудить с Вахтангом, т.к. DROP TABLE необратим и стоит сделать
      осознанно, не автоматически при каждом деплое).
   g. Обновить `entity_registry.md`/`ENGINE.md`/`docs/HANDOFF.md` в
      том же коммите.
3. **Рефакторинг `enginePage()`** — по-прежнему отдельная будущая
   сессия, не связана с этой задачей.

## Технический ориентир (где искать при следующей сессии)

- `app/engine/tables.py` — `specification_table`,
  `specification_item_table` (обе TableConfig ближе к концу файла).
- `app/models/specification.py`, `app/models/specification_item.py`.
- `app/models/invoice.py` — `specification_id` (комментарий в самой
  модели уже описывает историю поля).
- `app/models/invoice_item.py` — `specification_item_id`.
- `app/invoice_print/data.py` — fallback unit_name lookup (строки
  ~110-118 на момент v102).
- `app/database.py` — `_ensure_is_deleted_columns()` /
  `_drop_obsolete_columns()` — сюда добавлять DDL при финальном
  дропе.
