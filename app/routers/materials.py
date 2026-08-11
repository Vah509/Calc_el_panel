# app/routers/materials.py
# ============================================================
# CRUD для справочника материалов. Каждый эндпоинт возвращает
# HTML-фрагмент (не JSON) — паттерн HTMX: сервер сам решает,
# какой кусок разметки прислать в ответ на действие, а фронт
# просто вставляет его в нужное место страницы.
#
# Авто-пересчёт НДС: при сохранении, если поменялась одна из цен
# или ставка НДС, вторая цена пересчитывается автоматически —
# но только если её не тронули руками в этом же запросе (см.
# recalc_prices ниже). Это отражает решение из спецификации:
# "мутуальный авто-пересчёт, но с возможностью ручного override".
# ============================================================

from typing import Optional
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select, func

from app.database import get_session
from app.models.material import Material
from app.models.brand import Brand

import os

router = APIRouter(prefix="/materials", tags=["materials"])
_templates_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "templates")
templates = Jinja2Templates(directory=_templates_dir)


def recalc_prices(
    price_excl_vat: float,
    price_incl_vat: float,
    vat_rate: float,
    changed_field: str,
) -> tuple[float, float]:
    """
    Пересчитывает вторую цену на основе той, которую реально
    изменил пользователь. changed_field говорит, какое поле
    считать "источником истины" в этом сохранении.
    """
    if changed_field == "price_excl_vat":
        price_incl_vat = round(price_excl_vat * (1 + vat_rate / 100), 2)
    elif changed_field == "price_incl_vat":
        price_excl_vat = round(price_incl_vat / (1 + vat_rate / 100), 2)
    return price_excl_vat, price_incl_vat


@router.get("", response_class=HTMLResponse)
def list_materials(
    request: Request,
    q: Optional[str] = None,
    brand_id: Optional[int] = None,
    session: Session = Depends(get_session),
):
    statement = select(Material)
    if q:
        # Регистронезависимый поиск: приводим и колонку, и запрос к нижнему регистру.
        # Ищем и по short_name, и по артикулу — так поле поиска работает для обоих случаев.
        q_lower = q.lower()
        statement = statement.where(
            func.lower(Material.short_name).contains(q_lower)
            | func.lower(Material.sku_article).contains(q_lower)
        )
    if brand_id:
        statement = statement.where(Material.brand_id == brand_id)

    materials = session.exec(statement).all()
    brands = session.exec(select(Brand)).all()

    return templates.TemplateResponse(
        request,
        "materials/list.html",
        {"materials": materials, "brands": brands, "active_brand_id": brand_id, "q": q or ""},
    )


@router.get("/new", response_class=HTMLResponse)
def new_material_form(request: Request, session: Session = Depends(get_session)):
    brands = session.exec(select(Brand)).all()
    return templates.TemplateResponse(
        request,
        "materials/_form.html",
        {"material": None, "brands": brands},
    )


@router.get("/{material_id}/edit", response_class=HTMLResponse)
def edit_material_form(material_id: int, request: Request, session: Session = Depends(get_session)):
    material = session.get(Material, material_id)
    brands = session.exec(select(Brand)).all()
    return templates.TemplateResponse(
        request,
        "materials/_form.html",
        {"material": material, "brands": brands},
    )


@router.post("", response_class=HTMLResponse)
def create_material(
    request: Request,
    short_name: str = Form(...),
    full_name: str = Form(...),
    brand_id: Optional[int] = Form(None),
    sku_article: Optional[str] = Form(None),
    price_excl_vat: float = Form(0.0),
    price_incl_vat: float = Form(0.0),
    vat_rate: float = Form(20.0),
    price_source: str = Form("price_excl_vat"),
    session: Session = Depends(get_session),
):
    price_excl_vat, price_incl_vat = recalc_prices(
        price_excl_vat, price_incl_vat, vat_rate, price_source
    )

    material = Material(
        short_name=short_name,
        full_name=full_name,
        brand_id=brand_id,
        sku_article=sku_article,
        price_excl_vat=price_excl_vat,
        price_incl_vat=price_incl_vat,
        vat_rate=vat_rate,
    )
    session.add(material)
    session.commit()

    return _render_tbody(request, session)


@router.put("/{material_id}", response_class=HTMLResponse)
def update_material(
    material_id: int,
    request: Request,
    short_name: str = Form(...),
    full_name: str = Form(...),
    brand_id: Optional[int] = Form(None),
    sku_article: Optional[str] = Form(None),
    price_excl_vat: float = Form(0.0),
    price_incl_vat: float = Form(0.0),
    vat_rate: float = Form(20.0),
    price_source: str = Form("price_excl_vat"),
    session: Session = Depends(get_session),
):
    material = session.get(Material, material_id)
    if not material:
        return _render_tbody(request, session)

    price_excl_vat, price_incl_vat = recalc_prices(
        price_excl_vat, price_incl_vat, vat_rate, price_source
    )

    material.short_name = short_name
    material.full_name = full_name
    material.brand_id = brand_id
    material.sku_article = sku_article
    material.price_excl_vat = price_excl_vat
    material.price_incl_vat = price_incl_vat
    material.vat_rate = vat_rate

    session.add(material)
    session.commit()

    return _render_tbody(request, session)


@router.delete("/{material_id}", response_class=HTMLResponse)
def delete_material(material_id: int, request: Request, session: Session = Depends(get_session)):
    material = session.get(Material, material_id)
    if material:
        session.delete(material)
        session.commit()

    return _render_tbody(request, session)


def _render_tbody(request: Request, session: Session, q: Optional[str] = None, brand_id: Optional[int] = None):
    """
    Общий рендер только содержимого <tbody> таблицы материалов —
    используется после create/update/delete, чтобы не перезагружать
    всю страницу (меню, фильтры, поле поиска остаются как есть).
    Ответ несёт заголовок HX-Trigger (не HX-Trigger-After-Swap!) — у
    HX-Trigger-After-Swap есть известный баг в самом HTMX: событие
    не всплывает до document.body, поэтому глобальный слушатель в
    base.html его не ловит. Из-за этого возврат к обычному HX-Trigger,
    а порядок "сначала таблица, потом закрытие" обеспечивается на
    фронте — слушателем htmx:afterSwap прямо на #materials-tbody,
    а не через это кастомное событие.
    """
    statement = select(Material)
    if q:
        q_lower = q.lower()
        statement = statement.where(
            func.lower(Material.short_name).contains(q_lower)
            | func.lower(Material.sku_article).contains(q_lower)
        )
    if brand_id:
        statement = statement.where(Material.brand_id == brand_id)

    materials = session.exec(statement).all()

    response = templates.TemplateResponse(
        request,
        "materials/_tbody.html",
        {"materials": materials},
    )
    response.headers["HX-Trigger"] = "materialSaved"
    return response
