# app/documents_chain/router.py
# ============================================================
# Подключает страницу /documents-chain и API
# GET /api/documents-chain/{request_id} в приложение. Вызывается
# один раз из main.py, аналогично register_processors/
# register_engine_tables — тот же паттерн "свой раздел вне
# универсального движка таблиц" (см. app/processors/router.py).
#
# URL страницы БЕЗ {request_id} в пути (в отличие от API) —
# request_id передаётся query-параметром (?request_id=...), т.к.
# страница рендерится один раз статично (jinja_env.from_string,
# тот же приём, что и у /processors), а сам id читается и
# используется уже в браузере (см. init() в page.py). Кнопка
# "Показать подчинённые документы" в journal заявок формирует именно
# такую ссылку — см. engine/page.py::showDocumentsChain().
# ============================================================

from fastapi import APIRouter, FastAPI
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.documents_chain.api import router as chain_api_router
from app.documents_chain.page import render_documents_chain_page


def register_documents_chain(app: FastAPI, templates: Jinja2Templates) -> None:
    router = APIRouter(tags=["documents-chain"])

    @router.get("/documents-chain", response_class=HTMLResponse)
    def documents_chain_page():
        return render_documents_chain_page(templates.env)

    app.include_router(router)
    app.include_router(chain_api_router)
