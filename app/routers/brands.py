# app/routers/brands.py
# ============================================================
# CRUD для справочника брендов. Тот же паттерн, что и materials.py:
# каждый эндпоинт возвращает готовый HTML-фрагмент (HTMX), не JSON.
# ============================================================

from typing import Optional
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select

from app.database import get_session
from app.models.brand import Brand
from app.models.material import Material

import os

router = APIRouter(prefix="/brands", tags=["brands"])
_templates_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "templates")
templates = Jinja2Templates(directory=_templates_dir)


@router.get("", response_class=HTMLResponse)
def list_brands(
    request: Request,
    q: Optional[str] = None,
    session: Session = Depends(get_session),
):
    statement = select(Brand)
    if q:
        statement = statement.where(Brand.name.contains(q))

    brands = session.exec(statement).all()

    # Для каждого бренда — количество материалов, которые на него ссылаются.
    # Нужно, чтобы предупредить перед удалением бренда, который уже используется.
    materials_count: dict[int, int] = {}
    for brand in brands:
        count = session.exec(
            select(Material).where(Material.brand_id == brand.id)
        ).all()
        materials_count[brand.id] = len(count)

    return templates.TemplateResponse(
        request,
        "brands/list.html",
        {"brands": brands, "materials_count": materials_count},
    )


@router.get("/new", response_class=HTMLResponse)
def new_brand_form(request: Request):
    return templates.TemplateResponse(
        request,
        "brands/_form.html",
        {"brand": None},
    )


@router.get("/{brand_id}/edit", response_class=HTMLResponse)
def edit_brand_form(brand_id: int, request: Request, session: Session = Depends(get_session)):
    brand = session.get(Brand, brand_id)
    return templates.TemplateResponse(
        request,
        "brands/_form.html",
        {"brand": brand},
    )


@router.post("", response_class=HTMLResponse)
def create_brand(
    request: Request,
    name: str = Form(...),
    session: Session = Depends(get_session),
):
    brand = Brand(name=name)
    session.add(brand)
    session.commit()

    return _render_tbody(request, session)


@router.put("/{brand_id}", response_class=HTMLResponse)
def update_brand(
    brand_id: int,
    request: Request,
    name: str = Form(...),
    session: Session = Depends(get_session),
):
    brand = session.get(Brand, brand_id)
    if not brand:
        return _render_tbody(request, session)

    brand.name = name
    session.add(brand)
    session.commit()

    return _render_tbody(request, session)


@router.delete("/{brand_id}", response_class=HTMLResponse)
def delete_brand(brand_id: int, request: Request, session: Session = Depends(get_session)):
    brand = session.get(Brand, brand_id)
    if brand:
        session.delete(brand)
        session.commit()

    return _render_tbody(request, session)


def _render_tbody(request: Request, session: Session):
    """
    Общий рендер только содержимого <tbody> таблицы брендов —
    используется после create/update/delete, чтобы не перезагружать
    всю страницу. Заголовок HX-Trigger говорит фронту закрыть модалку.
    """
    brands = session.exec(select(Brand)).all()

    materials_count: dict[int, int] = {}
    for brand in brands:
        count = session.exec(
            select(Material).where(Material.brand_id == brand.id)
        ).all()
        materials_count[brand.id] = len(count)

    response = templates.TemplateResponse(
        request,
        "brands/_tbody.html",
        {"brands": brands, "materials_count": materials_count},
    )
    response.headers["HX-Trigger"] = "brandSaved"
    return response
