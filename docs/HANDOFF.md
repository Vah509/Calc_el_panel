# HANDOFF

## Состояние

**v82 — упрощена статусная модель calculation.**

`status` теперь допускает только `active`/`delete_pending` (было 4:
draft/active/archived_pending/delete_pending). Причина: в v81 при
создании калькуляции дефолтом ставился `"draft"`, и на форме поле было
скрыто (`in_form=False`) — переключить статус вручную было НЕЧЕМ, из-за
чего ВСЕ существующие калькуляции остались черновиками, а кнопка
«Спецификация» (фильтрует по `status="active"`) не находила ничего для
сборки.

Решение Вахтанга: черновик как промежуточное состояние не нужен —
сохранил калькуляцию, значит она сразу активна. Архив
(`archived_pending`) уберём/добавим отдельно позже своим шагом. Поле
`status` теперь ВИДНО и РЕДАКТИРУЕМО на форме калькуляции (было
`in_form=False`, стало `in_form=True` по умолчанию — просто убрал
явный `False`), рядом с «Рабочее название»/«Количество изделий».

Массовой миграции существующих `draft`-записей на production НЕ
делали — Вахтанг переставит/удалит их вручную через форму после
деплоя.

## Сделано в этой сессии

- `app/models/calculation.py` — `status` default `"draft"` -> `"active"`
- `app/engine/tables.py` — `calculation_table`, поле `status`:
  - `in_form=False` убран (поле теперь видно на форме)
  - `options` сокращены до `[("active", "Активна"), ("delete_pending", "К удалению")]`
    (убраны `"draft"`/`"archived_pending"`)
  - `dot_colors` синхронно сокращены
  - добавлен в `form_rows`: `FormRow(["client_name", "quantity", "status"])`
- `docs/HANDOFF_kits_and_calculation.md` — закрыт открытый вопрос
  "механика переходов статуса calculation не проговорена" (раздел 2 и
  раздел 3 "что осталось открытым")
- `app/version.py` — `APP_VERSION = "v82"`
- Тестирование (`TestClient`): новая калькуляция без явного `status`
  создаётся `active`; смена на `delete_pending` через `PUT` работает;
  регрессия `/calculation-v2` — 200

## Открыто

- `app/models/calculation.py` — новое поле `quantity` (float, default 1.0)
- `app/database.py` — `_ensure_is_deleted_columns()`: миграция
  `calculation.quantity` (существующая на Postgres таблица)
- `app/models/specification.py` (новый файл) — модель `Specification`
- `app/models/specification_item.py` (новый файл) — модель
  `SpecificationItem`
- `app/engine/config.py` — новое поле `FieldConfig.row_action_names`:
  параллельный `row_actions` список имён action (None — кнопка остаётся
  disabled-заглушкой, строка — кнопка активна и вызывает `runAction`).
  Первый row_action, получивший реальный обработчик, не отдельным
  `ActionButton`-блоком, а прямо рядом с полем.
- `app/engine/page.py`:
  - Шаблон row_actions теперь рендерит активную кнопку, если для
    позиции задано имя в `row_action_names` (иначе — как раньше,
    disabled)
  - `runAction()` — новый универсальный контракт: если ответ сервера
    содержит `redirect_url`, делает `window.location.href` вместо
    обычного подмешивания результата в `editing` (нужно для действий,
    создающих ДРУГОЙ документ, а не правящих текущую запись)
- `app/engine/tables.py`:
  - `_build_specification_handler(brand_slot)` — фабрика обработчика
    кнопки «Спецификация» слота 1/2/3 (один обработчик на слот —
    action_handlers плоский словарь по имени, номер слота зашит в
    самом имени `build_specification_1/2/3`)
  - `request_table` — `action_handlers` с этими тремя обработчиками,
    `row_action_names=["build_specification_N", None]` у каждого
    `brand_slot_N_id`
  - `calculation_table` — новое поле `quantity` в `fields`/`form_rows`
  - `specification_table` (новый) — `allow_create=False`,
    `allow_delete=False` (создание/удаление ТОЛЬКО через кнопку
    «Спецификация» у заявки), `own_page_url="/specification-v2"`,
    `document_prefix="S"`
  - `specification_item_table` (новый) — `allow_create=False`,
    `allow_delete=False`, `hierarchy(parent_field="specification_id")`
    только ради `?parent_id=` фильтра API (не пункт меню, не
    drill-down)
  - Обе добавлены в `ALL_TABLES`
- `app/engine/document_chain.py` — `CHAIN_LINKS`: добавлена
  `ChainLink(child_key="specification", parent_key="request", ...)`
  (родитель — request, НЕ calculation: одна спецификация агрегирует
  НЕСКОЛЬКО калькуляций, N:1 не вписывается в один FK)
- `app/documents_chain/api.py` — исправлен BFS-обход `get_documents_chain`:
  раньше `parent_key` с НЕСКОЛЬКИМИ дочерними связями сразу (теперь
  именно так — calculation И specification оба дети request) терял
  часть найденных id на следующей итерации (одна общая
  `next_level_key`/`next_level_ids` на все связи уровня). Переписано на
  очередь `pending_levels: list[tuple[child_key, ids]]` — каждая ветка
  обходится дальше вниз независимо. На практике сейчас ни у calculation,
  ни у specification нет дальнейших потомков, поэтому старый баг не
  проявлялся бы прямо сейчас, но всплыл бы при первом же добавлении
  третьего уровня цепочки — исправлено сразу, пока добавляю первый
  реальный multi-child случай.
- `app/version.py` — `APP_VERSION = "v81"`, пункт меню «Спецификации»
  (`/specification-v2`)
- Тестирование (`TestClient`, контекстный менеджер, SQLite):
  - Полный сценарий: заявка + 4 калькуляции (2 активные слот 1, 1
    активная слот 2, 1 draft слот 1) → кнопка слота 1 → спецификация
    содержит РОВНО 2 строки (draft и чужой слот исключены), суммы
    построчно и итого верны, `client_id` — снэпшот заявки
  - Повторное нажатие той же кнопки после изменения `final_total`
    калькуляции — старая спецификация и её строки физически удалены,
    новая пересчитана верно (проверено количество строк в БД до/после,
    без утечки старых)
  - Слоты 2 и 3 собираются независимо, не трогая уже созданную
    спецификацию слота 1; пустой слот (нет калькуляций) — спецификация
    с `total_amount=0`, без ошибки
  - `allow_create=False`/`allow_delete=False` — ручной POST/DELETE на
    `specification`/`specification_item` отклоняется 422 с понятным
    текстом
  - `GET /api/documents-chain/{id}` — три группы (request, calculation,
    specification) с верным количеством строк в каждой
  - Регрессия: `/calculation-v2`, `/request-v2`, `/documents-chain`,
    `/specification-v2` — 200; `PUT /api/calculation/{id}` с `quantity`
    сохраняется корректно, остальные поля вкладки «Стоимость» не
    затронуты

## Открыто

- Не проверено на реальном устройстве — только TestClient/бэкенд;
  внешний вид кнопки «Спецификация» на форме заявки, переход на
  созданную карточку, отображение строк спецификации (через отдельный
  список `/specification_item-v2?parent_id=`, встроенного виджета в
  форму specification в этом шаге нет — см. ниже) нужно проверить
  вживую на телефоне
- Просмотр строк спецификации внутри самой карточки specification НЕ
  встроен (в отличие от вкладки «Материалы» калькуляции) — строки
  видны только отдельным списком `specification_item` (без своего
  пункта меню, доступен по прямому URL с `?parent_id=`). Возможное
  улучшение следующим шагом: простой readonly-виджет на форме
  specification по образцу `materials_tab`, но без add/picker
  (полноценный `materials_tab` слишком тесно завязан на редактируемый
  состав калькуляции, специально не стал туда лезть в этом шаге)
- Кнопка «Пересчитать» рядом с «Спецификация» у каждого брендового
  слота заявки — по-прежнему disabled-заглушка (`row_action_names`
  на этой позиции = None), своей логики ещё нет
- Рефакторинг `enginePage()` (app/engine/page.py, ~1850+ строк / ~60+
  методов) — по-прежнему сознательно отложен
- `invoice`, ценообразование, «перепроведение» остальных документов,
  Excel/PDF — не начаты. Открытый вопрос из
  docs/HANDOFF_kits_and_calculation.md: счёт-фактура при создании из
  спецификации копирует себе данные (снимок снимка) или может
  сослаться на specification_item напрямую — уточнить в начале работы
  над invoice
