# app/models/material.py
# ============================================================
# Материал каталога. Два независимых поля цены (без НДС / с НДС)
# с взаимным авто-пересчётом через движок (см. app/engine/api.py,
# ComputedPair) — в модели они просто два поля, ничего "магического"
# на уровне БД не происходит.
#
# Ставки НДС в модели больше нет (была vat_rate, удалена v28) —
# ставка общая для всех материалов и хранится ТОЛЬКО в справочнике
# constants (ключ vat_rate). В карточке материала показывается как
# "живая ссылка": readonly, всегда актуальное значение из constants,
# используется при пересчёте price_excl_vat <-> price_incl_vat
# (см. tables.py, ComputedPair.rate_constant_key).
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

    # owner_id — задел под будущую многопользовательскую модель
    # (см. спецификацию: разграничение по owner_id, без ролей)
    owner_id: Optional[int] = Field(default=None, index=True)
