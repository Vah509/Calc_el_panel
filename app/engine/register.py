# app/engine/register.py
# ============================================================
# Регистрирует API + HTML-страницы для всех таблиц из
# app/engine/tables.py. Один вызов register_engine_tables(app)
# в main.py подключает движок целиком.
#
# URL-путь страницы = /{key}-v2 (например /material-v2,
# /brand-v2) — суффикс "-v2", чтобы не пересекаться с уже
# существующими /materials-alpine, /brands-alpine на время
# обкатки движка. После проверки на реальном устройстве можно
# будет либо переименовать путь, либо оставить как есть и
# добавить ссылку в меню.
# ============================================================

import os
from fastapi import FastAPI
from fastapi.templating import Jinja2Templates

from app.engine.tables import ALL_TABLES
from app.engine.api import build_api_router
from app.engine.page_router import build_page_router


def register_engine_tables(app: FastAPI) -> None:
    templates_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "templates")
    templates = Jinja2Templates(directory=templates_dir)

    for config in ALL_TABLES:
        app.include_router(build_api_router(config))
        app.include_router(build_page_router(config, templates, url_path=f"/{config.key}-v2"))
