# HANDOFF

## Состояние

**v80 — исправлена недоработка v79, обнаруженная Вахтангом: переключение
radio "Способ расчёта стоимости" (Наценка/По часам) не меняло "Итоговую
стоимость" на экране.**

Причина: `final_total` — обычное readonly-поле формы, значение которого
менялось ТОЛЬКО на сервере, внутри `_recalc_cost_totals` (то есть только
по клику "Пересчитать" или при открытии формы через
`refresh_cost_totals`, см. v79). Переключение radio `cost_method`
меняло `editing.cost_method` в браузере, но никак не трогало
`editing.final_total` — старое значение просто оставалось висеть на
экране до следующего похода на сервер.

Исправлено в два слоя:
1. **Мгновенный клиентский пересчёт при переключении radio** — новый
   `CLIENT_ACTIONS.pick_final_total` (page.py): выбирает уже известное
   `editing.markup_total` либо `editing.hours_total` под текущий
   `cost_method`, без похода на сервер. Подключается через
   `FieldConfig.on_change_action` — этот примитив уже существовал, но
   раньше применялся только к `<select>`-полям (например
   `brand_slot_labels` у `request_id`); теперь Jinja-разметка
   radio-виджета тоже поддерживает `on_change_action`.
2. **Синхронизация при сохранении** — `final_total` помечен
   `readonly=True`, поэтому даже мгновенно обновлённое клиентом значение
   отбрасывалось обычным PUT (readonly-поля игнорируются в
   `update_item`, engine/api.py) — из базы после "Сохранить" снова
   читалось бы устаревшее значение. Новый универсальный примитив
   движка `TableConfig.before_update_hook` — функция `fn(instance,
   session)`, вызываемая ВНУТРИ `update_item` сразу после применения
   полей PUT-payload, до commit. У `calculation` зарегистрирован
   `_sync_final_total_before_save` — пересчитывает `final_total` из уже
   применённого (из этого же payload) `cost_method`, не трогая
   остальные суммы.

## Сделано в этой сессии

- `app/engine/page.py`:
  - `CLIENT_ACTIONS.pick_final_total` — клиентский пересчёт
    `final_total` из `markup_total`/`hours_total` под текущий
    `cost_method`
  - Radio-виджет (Jinja) — добавлена поддержка `f.on_change_action`
    (по образцу `<select>`)
- `app/engine/tables.py`:
  - `cost_method` — добавлен `on_change_action="pick_final_total"`
  - Новая функция `_sync_final_total_before_save` — зарегистрирована
    как `before_update_hook` у `calculation_table`
- `app/engine/config.py` — новое поле `TableConfig.before_update_hook`
  (универсальный примитив: `fn(instance, session)`, вызывается внутри
  `update_item`, engine/api.py, сразу после применения полей payload,
  до commit — не хардкод под calculation)
- `app/engine/api.py` — `update_item` вызывает
  `config.before_update_hook(instance, session)` после применения
  полей, до commit, если хук задан
- `app/version.py` — `APP_VERSION = "v80"`
- Тестирование:
  - Node: `CLIENT_ACTIONS.pick_final_total` изолированно — markup/hours/
    ещё-не-посчитанные-значения (undefined -> 0), все три случая верны
  - `TestClient`: полный сценарий PUT с переключённым `cost_method` —
    `final_total` в БД после сохранения синхронен с выбранным способом
    (без хука тест падал, воспроизведя ровно баг Вахтанга)
  - Повторный клик "Пересчитать" после переключения способа — сервер
    тоже корректно выставляет `final_total` под новый `cost_method`
  - Частичный PUT без поля `cost_method` в payload — хук не падает,
    `cost_method`/`final_total` остаются дефолтными
  - Регрессия: `/calculation-v2`, `/request-v2`, `/documents-chain` —
    200
  - `node --check` — синтаксис извлечённого JS корректен

## Открыто

- Не проверено на реальном устройстве — переключение radio и
  визуальное обновление "Итоговой стоимости" в браузере, а также
  реальное нажатие "Сохранить" после переключения, проверялись только
  через TestClient/Node, не вживую
- Рефакторинг `enginePage()` (app/engine/page.py, ~1850+ строк / ~60+
  методов) — по-прежнему сознательно отложен до начала кодирования
  specification
- Следующий шаг дорожной карты (после того как v80 будет подтверждена
  рабочей): specification — открытый вопрос, от чего наследуется
  (request или calculation) и как участвует бренд, см.
  docs/HANDOFF_kits_and_calculation.md
- `invoice`, ценообразование, "перепроведение" остальных документов,
  Excel/PDF — не начаты
