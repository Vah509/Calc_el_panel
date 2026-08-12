# app/routers/brands_api.py
# ============================================================
# ЭКСПЕРИМЕНТ: JSON API для брендов — см. materials_api.py для
# общего объяснения подхода. Тот же паттерн, тот же принцип.
# ============================================================

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from app.database import get_session
from app.models.brand import Brand
from app.models.material import Material

router = APIRouter(prefix="/api/brands", tags=["brands-api"])


class BrandIn(BaseModel):
    name: str


@router.get("")
def list_brands(q: Optional[str] = None, session: Session = Depends(get_session)):
    statement = select(Brand)
    if q:
        statement = statement.where(Brand.name.contains(q))
    brands = session.exec(statement).all()

    result = []
    for brand in brands:
        count = len(session.exec(select(Material).where(Material.brand_id == brand.id)).all())
        result.append({"id": brand.id, "name": brand.name, "materials_count": count})
    return result


@router.post("")
def create_brand(data: BrandIn, session: Session = Depends(get_session)):
    brand = Brand(name=data.name)
    session.add(brand)
    session.commit()
    session.refresh(brand)
    return brand


@router.put("/{brand_id}")
def update_brand(brand_id: int, data: BrandIn, session: Session = Depends(get_session)):
    brand = session.get(Brand, brand_id)
    if not brand:
        raise HTTPException(status_code=404, detail="Бренд не найден")
    brand.name = data.name
    session.add(brand)
    session.commit()
    session.refresh(brand)
    return brand


@router.delete("/{brand_id}")
def delete_brand(brand_id: int, session: Session = Depends(get_session)):
    brand = session.get(Brand, brand_id)
    if not brand:
        raise HTTPException(status_code=404, detail="Бренд не найден")
    session.delete(brand)
    session.commit()
    return {"deleted": True, "id": brand_id}
