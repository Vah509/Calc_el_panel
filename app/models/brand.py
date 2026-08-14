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

    # is_deleted — визуальная пометка "к удалению" (soft-delete),
    # НЕ фильтрация — см. комментарий в app/models/material.py.
    is_deleted: bool = Field(default=False, index=True)
