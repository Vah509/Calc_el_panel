# app/routers/alpine_pages.py
# ============================================================
# ЭКСПЕРИМЕНТ: страницы-обёртки для варианта Alpine.js + JSON API.
# Каждый эндпоинт просто рендерит пустую HTML-страницу с Alpine
# x-data — весь список данных страница подгружает сама через
# fetch() к /api/materials, /api/brands (см. materials_api.py,
# brands_api.py). Отдельные пути, чтобы не пересекаться с текущими
# рабочими /materials и /brands на HTMX.
# ============================================================

import os
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

router = APIRouter(tags=["alpine-experiment"])
_templates_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "templates")
templates = Jinja2Templates(directory=_templates_dir)


@router.get("/materials-alpine", response_class=HTMLResponse)
def materials_alpine_page(request: Request):
    return templates.TemplateResponse(request, "materials/list_alpine.html", {})


@router.get("/brands-alpine", response_class=HTMLResponse)
def brands_alpine_page(request: Request):
    return templates.TemplateResponse(request, "brands/list_alpine.html", {})
