# app/engine/page_router.py
# ============================================================
# Фабрика роутера HTML-страницы по TableConfig. Использует общий
# Jinja2Templates.env приложения (передаётся снаружи), чтобы
# {% extends "base.html" %} внутри сгенерированного шаблона
# движка нашёл base.html через тот же loader, что и остальные
# страницы приложения.
# ============================================================

from fastapi import APIRouter
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.engine.config import TableConfig
from app.engine.page import render_table_page


def build_page_router(config: TableConfig, templates: Jinja2Templates, url_path: str) -> APIRouter:
    router = APIRouter(tags=[f"{config.key}-page"])

    @router.get(url_path, response_class=HTMLResponse)
    def table_page():
        return render_table_page(config, templates.env)

    return router
