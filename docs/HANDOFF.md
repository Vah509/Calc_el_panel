# HANDOFF

## Состояние

Работает: универсальный CRUD-движок (`app/engine/`) — `config.py`, `formulas.py`, `api.py`, `page.py`, `page_router.py`, `tables.py`, `register.py`. Активные страницы: `/material-v2`, `/brand-v2`, `/constant-v2`.

Последнее изменение: v26 — таблица `constants` (справочник key-value) через движок.

## Сделано в этой сессии

1. Модель `Constant` (`app/models/constant.py`): `id`, `key` (unique), `value` (строка, тип приводится в коде при использовании), `description`.
2. `seed_constants()` в `app/database.py` — идемпотентный seed при старте: `vat_rate=20`, `default_page_size=100`. Вызывается в `on_startup` после `init_db()`. Проверено: повторный старт не дублирует и не перезаписывает изменённые значения.
3. Движок расширен минимально под нужды constants:
   - `FieldConfig.readonly: bool` — поле рендерится в форме как текст, не input; на бэкенде `update_item` игнорирует readonly-поля, даже если их прислать напрямую в API.
   - `TableConfig.allow_create` / `allow_delete: bool` — кнопки "+ Добавить" / "Удалить" скрываются в UI, POST/DELETE эндпоинты возвращают 422.
4. `constant_table` в `tables.py`: `key` — readonly, searchable; `value` — редактируемое; `description` — readonly, только в списке (`in_form=False`). `allow_create=False`, `allow_delete=False` (набор ключей фиксирован, задаётся только seed'ом).
5. CSS: `.field-readonly-text` для отображения readonly-полей в форме.

Протестировано локально через TestClient: seed идемпотентен, `value` редактируется, `key` защищён от изменения и на фронте, и на бэкенде, create/delete запрещены (422), старые таблицы material/brand не затронуты, HTML-страница `/constant-v2` рендерится корректно.

**НЕ делали в этом шаге (сознательно, по порядку из прошлой сессии):** таблица `material` не тронута — `vat_rate` там всё ещё своё собственное поле per-material, `computed_pairs` не меняли. Применение `vat_rate` из constants к материалам — следующий шаг.

## Открыто

**Порядок реализации (из прошлой сессии, продолжаем по порядку):**
1. ~~`constants`~~ — готово (этот шаг).
2. Soft-delete — `TableConfig.soft_delete`, `is_deleted` в Material и Brand, API delete_item ставит флаг вместо физического удаления, UI-маркер в списке. Без фильтрации видимости — помеченные записи остаются в обычных списках.
3. Bulk-recalculate — зависит от constants (готово) и soft-delete. Первая функция: пересчёт `price_incl_vat` по `vat_rate` из constants. Пересчитывать ВСЕ позиции наравне, включая помеченные на удаление.

Каждый пункт — свой архив, свой APP_VERSION, тест на устройстве между шагами.

**Отложено осознанно (не поднимать без явного запроса):** kits/kit_items как отдельная страница-карточка; RBAC/роли (второго пользователя нет); валидация уникальности вне движка; bulk-операции через чекбоксы в UI и экспорт CSV.

**Вопрос без ответа:** нет.
