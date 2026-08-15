# app/models/brand.py
# ============================================================
# Бренд материала. Есть специальная запись "Universal" — для
# компонентов, не привязанных к конкретному производителю
# (см. спецификацию, раздел про материалы).
# ============================================================

from typing import Optional
from sqlmodel import SQLModel, Field


class Brand(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True, unique=True)

    # rate_vb — курс валюты поставщика этого бренда (напр. EUR/USD → грн),
    # выставляется вручную при изменении курса. Используется калькуляцией
    # (когда она появится) вместе с Material.price_vb_incl_vat для расчёта
    # цены материала "на лету" по курсу поставщика, как альтернатива
    # обычной гривневой цене (price_incl_vat). Сам факт хранения курса
    # здесь не пересчитывает ничего в Material — это делает калькуляция.
    rate_vb: float = Field(default=0.0)

    # is_deleted — визуальная пометка "к удалению" (soft-delete),
    # НЕ фильтрация — см. комментарий в app/models/material.py.
    is_deleted: bool = Field(default=False, index=True)
