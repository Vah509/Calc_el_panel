# app/routers/materials_api.py
# ============================================================
# ЭКСПЕРИМЕНТ: JSON API для материалов, без HTML-фрагментов.
# Alpine.js на фронте сам управляет состоянием (список, модалка,
# что редактируется) и вызывает эти эндпоинты через fetch().
#
# Отличие от app/routers/materials.py (текущий HTMX-роутер):
# здесь каждый эндпоинт отдаёт чистый JSON, не рендерит Jinja-
# шаблоны вообще. Роутер существует ПАРАЛЛЕЛЬНО со старым —
# ничего не удаляет и не меняет в текущей рабочей версии.
# ============================================================

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select, func

from app.database import get_session
from app.models.material import Material
from app.models.brand import Brand

router = APIRouter(prefix="/api/materials", tags=["materials-api"])


class MaterialIn(BaseModel):
    short_name: str
    full_name: str
    brand_id: Optional[int] = None
    sku_article: Optional[str] = None
    price_excl_vat: float = 0.0
    price_incl_vat: float = 0.0
    vat_rate: float = 20.0
    price_source: str = "price_excl_vat"  # какое поле цены менял пользователь


def recalc_prices(price_excl_vat: float, price_incl_vat: float, vat_rate: float, changed_field: str):
    if changed_field == "price_excl_vat":
        price_incl_vat = round(price_excl_vat * (1 + vat_rate / 100), 2)
    elif changed_field == "price_incl_vat":
        price_excl_vat = round(price_incl_vat / (1 + vat_rate / 100), 2)
    return price_excl_vat, price_incl_vat


@router.get("")
def list_materials(
    q: Optional[str] = None,
    brand_id: Optional[int] = None,
    session: Session = Depends(get_session),
):
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
    return materials


@router.post("")
def create_material(data: MaterialIn, session: Session = Depends(get_session)):
    price_excl_vat, price_incl_vat = recalc_prices(
        data.price_excl_vat, data.price_incl_vat, data.vat_rate, data.price_source
    )
    material = Material(
        short_name=data.short_name,
        full_name=data.full_name,
        brand_id=data.brand_id,
        sku_article=data.sku_article,
        price_excl_vat=price_excl_vat,
        price_incl_vat=price_incl_vat,
        vat_rate=data.vat_rate,
    )
    session.add(material)
    session.commit()
    session.refresh(material)
    return material


@router.put("/{material_id}")
def update_material(material_id: int, data: MaterialIn, session: Session = Depends(get_session)):
    material = session.get(Material, material_id)
    if not material:
        raise HTTPException(status_code=404, detail="Материал не найден")

    price_excl_vat, price_incl_vat = recalc_prices(
        data.price_excl_vat, data.price_incl_vat, data.vat_rate, data.price_source
    )

    material.short_name = data.short_name
    material.full_name = data.full_name
    material.brand_id = data.brand_id
    material.sku_article = data.sku_article
    material.price_excl_vat = price_excl_vat
    material.price_incl_vat = price_incl_vat
    material.vat_rate = data.vat_rate

    session.add(material)
    session.commit()
    session.refresh(material)
    return material


@router.delete("/{material_id}")
def delete_material(material_id: int, session: Session = Depends(get_session)):
    material = session.get(Material, material_id)
    if not material:
        raise HTTPException(status_code=404, detail="Материал не найден")
    session.delete(material)
    session.commit()
    return {"deleted": True, "id": material_id}
