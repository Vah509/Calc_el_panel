# HANDOFF

## Состояние

**v73 — "Показать подчинённые документы" (цепочка документов заявки) реализована.**

Новый раздел `app/documents_chain/` (page.py + api.py + router.py):
страница `/documents-chain?request_id={id}` — полноэкранный журнал,
доступный ТОЛЬКО по кнопке из панели выделения заявок (после того
как выделена ровно одна заявка). Показывает саму заявку и все
дочерние документы плоским списком, сгруппированным по типу.
Выделение сквозное across групп, копирование/пометка на удаление
переиспользуют существующие per-table API движка
(`POST /api/{key}`, `POST /api/{key}/bulk-mark-delete`) — никакой
новой бизнес-логики для этих действий не писалось.

Связи между типами документов вынесены в реестр
`app/engine/document_chain.py` (`CHAIN_LINKS`) — декларативный
список `ChainLink(child_key, parent_key, fk_field)`. Сейчас в
реестре одна связь: `calculation -> request` через `request_id`.
Когда появятся `specification`/`invoice`, для каждого добавляется
одна строка в `CHAIN_LINKS` — код страницы/API менять не нужно,
обход графа рекурсивный по реестру.

`TableConfig` (config.py) получил новое поле `documents_chain_url`
— по аналогии с уже существовавшим `create_child_document_url`.
Вторая кнопка `child_document_actions[1]` ("Показать подчинённые
документы") у `request_table` (tables.py) перестала быть
disabled-заглушкой — теперь ведёт на `/documents-chain`.

## Сделано в этой сессии

- `app/engine/document_chain.py` — реестр `CHAIN_LINKS` + `children_of()`/`parent_of()`
- `app/documents_chain/api.py` — `GET /api/documents-chain/{request_id}`, BFS вниз по реестру
- `app/documents_chain/page.py` — Alpine-страница журнала цепочки (группы, сквозное выделение, copy/bulk-delete)
- `app/documents_chain/router.py` — регистрирует страницу и API, подключён в `main.py`
- `config.py::TableConfig.documents_chain_url` — новое поле
- `tables.py` — `request_table.documents_chain_url = "/documents-chain"`
- `page.py` — кнопки `child_document_actions` теперь проверяются НЕЗАВИСИМО (была одна проверка на обе кнопки сразу — если первая не задана заглушками становились обе; теперь у каждой своё условие), добавлена `showDocumentsChain()`, `CONFIG.documentsChainUrl`
- Протестировано через `TestClient` (SQLite): создание client→request→calculation, `GET /api/documents-chain/{id}` возвращает обе группы с полями/relations, 404 на несуществующей заявке, страницы `/documents-chain` и `/request-v2` рендерятся, copy/bulk-mark-delete по паттерну фронта цепочки отрабатывают штатно, другие страницы движка (`/calculation-v2`, `/material-v2`) не задеты
- Новых полей моделей НЕ добавлялось — миграций/`_ensure_is_deleted_columns()` не требуется
- **HANDOFF.md переписан целиком** (было 15 накопленных версионных блоков вместо одного актуального — расходится с принципом "single overwritten file", восстановлен)

## Открыто

- Не проверено на реальном устройстве (только TestClient/SQLite)
- Не проверено визуально, как выглядит группа с 0 документами и как выглядит группа с большим числом строк на мобильном экране
- `specification`/`invoice` по-прежнему не реализованы — при их появлении: (1) создать TableConfig в tables.py, (2) добавить `ChainLink` в `CHAIN_LINKS`, больше ничего в document_chain не трогать
- Действие "Показать подчинённые документы" сейчас есть только у `request_table`; если понадобится аналогичная кнопка у `calculation_table` (посмотреть цепочку "вверх" от калькуляции) — текущий дизайн это не покрывает, `documents_chain_url` жёстко подразумевает REQUEST как корень (`ROOT_KEY` в document_chain.py)
