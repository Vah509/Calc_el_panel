# app/engine/register.py
# ============================================================
# Регистрирует API + HTML-страницы для всех таблиц из
# app/engine/tables.py. Один вызов register_engine_tables(app)
# в main.py подключает движок целиком.
#
# URL-путь страницы = /{key}-v2 (например /material-v2,
# /brand-v2). Суффикс "-v2" остался с этапа обкатки движка рядом
# со старыми HTMX-страницами — те давно удалены (см.
# docs/HANDOFF.md), движок теперь единственная реализация; путь
# не переименован, чтобы не трогать закладки/ссылки без необходимости.
# ============================================================

import os
from fastapi import FastAPI
from fastapi.templating import Jinja2Templates

from app.engine.tables import ALL_TABLES
from app.engine.api import build_api_router
from app.engine.page_router import build_page_router
from app.version import APP_VERSION, NAV_MENU


def register_engine_tables(app: FastAPI) -> Jinja2Templates:
    templates_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "templates")
    templates = Jinja2Templates(directory=templates_dir)

    # APP_VERSION и меню шапки (base.html) — общие для всех страниц
    # движка, задаются один раз здесь как Jinja-globals, а не
    # прокидываются вручную в каждый рендер отдельной таблицы.
    templates.env.globals["APP_VERSION"] = APP_VERSION
    templates.env.globals["NAV_MENU"] = NAV_MENU

    for config in ALL_TABLES:
        app.include_router(build_api_router(config))
        app.include_router(build_page_router(config, templates, url_path=f"/{config.key}-v2"))

    # Возвращаем templates наружу — main.py переиспользует то же
    # Jinja2Templates окружение (с уже настроенными globals) для
    # регистрации других разделов приложения вне движка таблиц
    # (например app/processors — раздел "Обработки" в меню),
    # чтобы не плодить второй Jinja2Templates с задвоенной настройкой.
    return templates
