# app/models/material.py
# ============================================================
# Материал каталога. Два независимых поля цены (без НДС / с НДС)
# с взаимным авто-пересчётом на уровне бизнес-логики (см.
# app/routers/materials.py) — в модели они просто два поля,
# ничего "магического" на уровне БД не происходит.
#
# short_name / full_name — два разных имени: короткое (для быстрого
# поиска и списков, по конвенции бренд-код + тип + параметры) и
# длинное (человекочитаемое полное название).
# ============================================================

from typing import Optional
from sqlmodel import SQLModel, Field


class Material(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)

    short_name: str = Field(index=True)
    full_name: str

    brand_id: Optional[int] = Field(default=None, foreign_key="brand.id")
    sku_article: Optional[str] = Field(default=None, index=True)

    price_excl_vat: float = Field(default=0.0)
    price_incl_vat: float = Field(default=0.0)
    vat_rate: float = Field(default=20.0)

    # owner_id — задел под будущую многопользовательскую модель
    # (см. спецификацию: разграничение по owner_id, без ролей)
    owner_id: Optional[int] = Field(default=None, index=True)
