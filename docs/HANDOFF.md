# Handoff

## Состояние
Движок v21. Активные страницы: /material-v2, /brand-v2 (старые страницы —
/materials, /brands, /materials-alpine, /brands-alpine — рядом, не тронуты).
Последнее: галочки поиска (short_name/full_name) для Материалов +
документация движка (app/engine/ENGINE.md).

## Сделано в этой сессии
- Галочки поиска: TableConfig.enable_search_toggles, FieldConfig.search_toggle
  (общая возможность движка, включена пока только у Материалов)
- API: GET /api/{key} принимает search_fields=... (обратная совместимость
  сохранена — без параметра ищет по всем searchable, как раньше)
- app/engine/ENGINE.md — техдокументация движка
- docs/HANDOFF.md — этот файл, правило описано в памяти чата

## Открыто
- (пусто)
