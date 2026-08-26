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

    if config.own_page_url:
        # Плоские таблицы с собственной формой-страницей (v75:
        # request/calculation) — список и форма живут на РАЗНЫХ URL:
        # url_path (например "/request-v2") — только список
        # (render_mode="list", без модалки в разметке вообще);
        # url_path + "/new" и url_path + "/{item_id}" — форма на весь
        # экран (render_mode="form"), сама подхватывает нужную запись
        # по последнему сегменту пути (см. maybeOpenOwnPage() в JS).
        # own_page_url в TableConfig ДОЛЖЕН совпадать с url_path этой
        # же таблицы — если когда-нибудь разъедутся, здесь просто
        # заработает по своему url_path, а весь код, ссылающийся на
        # CONFIG.ownPageUrl (openDocumentRow/copySelected/цепочка
        # документов), поедет по own_page_url — их надо менять вместе.
        @router.get(url_path, response_class=HTMLResponse)
        def table_list_page():
            return render_table_page(config, templates.env, render_mode="list")

        @router.get(url_path + "/new", response_class=HTMLResponse)
        def table_create_page():
            return render_table_page(config, templates.env, render_mode="form")

        @router.get(url_path + "/{item_id}", response_class=HTMLResponse)
        def table_edit_page(item_id: int):
            return render_table_page(config, templates.env, render_mode="form")

        return router

    @router.get(url_path, response_class=HTMLResponse)
    def table_page():
        return render_table_page(config, templates.env)

    return router
