# app/models/constant.py
# ============================================================
# Справочник глобальных констант (key-value). Первые записи:
# vat_rate (ставка НДС) и default_page_size (лимит строк в
# списках движка). Набор ключей фиксирован и задаётся один раз
# при старте приложения (см. app/database.py, seed_constants) —
# через UI можно менять только value, не key и не создавать/
# удалять записи (см. TableConfig в app/engine/tables.py,
# allow_create=False, allow_delete=False, readonly=True на key).
#
# value хранится строкой намеренно: разные константы имеют
# разную природу (числа — vat_rate, default_page_size; в
# будущем возможны текстовые). Приведение типа делается в коде
# там, где конкретная константа используется — отдельные
# типизированные поля (value_number/value_text) избыточны для
# небольшого набора констант.
# ============================================================

from typing import Optional
from sqlmodel import SQLModel, Field


class Constant(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    key: str = Field(index=True, unique=True)
    value: str
    description: str = ""
