# Handoff

## Состояние
Движок v25. Материалы и Бренды работают ТОЛЬКО через движок:
/material-v2, /brand-v2. Корень / редиректит на /material-v2.
Старые ручные реализации физически удалены (cleanup из прошлой
сессии применён). Документация движка — app/engine/ENGINE.md,
актуальна.

## Сделано в этой сессии
Код-ревью на мусор по всему репозиторию (pyflakes + ручная проверка
CSS/шаблонов/роутеров), без функциональных изменений:
- app/engine/api.py: убрана неиспользуемая переменная relation_fields
- scripts/process_cleanup.py: убран лишний f-префикс у строки без
  плейсхолдеров (косметика)
- app/static/style.css: убраны 6 неиспользуемых классов —
  .col-full, .col-short, .icon-btn, .modal-close, .row-actions,
  .vat-tag (остатки вёрстки до текущего движкового рендера;
  проверено, что закрытие модалки идёт через .btn.btn-ghost, не
  через .modal-close)
- Всё протестировано через TestClient: /health, /, /material-v2,
  /brand-v2, CRUD по /api/material и /api/brand, relation-фильтр
  brand_id, ComputedPair (пересчёт НДС), search_fields — работает

Найден, но НЕ удалён в этом архиве (вынесено во второй,
cleanup-архив): app/routers/ — пустой пакет (__init__.py, 0 строк),
нигде не импортируется.

## Открыто
Ничего не открыто по итогам ревью. Второй архив (cleanup-request)
идёт отдельно — только app/routers/.
