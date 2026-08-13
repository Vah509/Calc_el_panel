# Handoff

## Состояние
Движок v24. Материалы и Бренды работают ТОЛЬКО через движок:
/material-v2, /brand-v2. Корень / редиректит на /material-v2.
Старые роуты (materials.py, brands.py, materials_api.py, brands_api.py,
alpine_pages.py, admin.py/sqladmin) отключены в app/main.py — их файлы
физически ещё в репозитории, удаляются отдельным cleanup-запросом
(cleanup_2026-08-13.txt в cleanup-requests/, залит вместе с этим архивом).

## Сделано в этой сессии
- app/main.py: убраны импорты и include_router() старых роутеров и
  register_admin(); корневой редирект / → /material-v2 (был /materials)
- app/templates/base.html: убран HTMX-скрипт и DOMContentLoaded-блок
  (были нужны только для старых HTMX-страниц, движок их не использует)
- app/static/style.css: убраны мёртвые .nav-dropdown-*/.nav-caret
- requirements.txt: убран sqladmin==0.31.0 (протестировано в чистом
  venv без пакета — приложение стартует нормально)
- cleanup_2026-08-13.txt — список файлов на физическое удаление:
  старые роутеры/API, admin.py + admin_templates/ + admin-theme.css,
  templates/materials/, templates/brands/, мусорный zip с прошлых сессий

## Открыто
- После того как Вахтанг запустит "Repo Cleanup" в GitHub Actions —
  стоит один раз пересобрать/передеплоить на Railway и проверить, что
  всё поднимается (requirements.txt уже без sqladmin, но это стоит
  подтвердить на реальном деплое, не только локальным TestClient)
