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
