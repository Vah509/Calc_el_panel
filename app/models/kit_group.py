# app/models/kit_group.py
# ============================================================
# KitGroup — верхний уровень двухуровневой иерархии разделов
# комплектов (kit_group -> kit_section -> kit). Пример: группа
# "Подключение" объединяет подразделы "Подключение силовых
# автоматов", "Подключение модульных автоматов" и т.д.
#
# sort_order — управляемый порядок обхода в UI (по практике 1С:
# открыл раздел -> выбрал нужные комплекты -> закрыл -> следующий
# раздел; порядок важен для удобства работы, не алфавитный).
# ============================================================

from typing import Optional
from sqlmodel import SQLModel, Field


class KitGroup(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True, unique=True)
    sort_order: int = Field(default=0)

    # is_deleted — визуальная пометка "к удалению" (soft-delete),
    # НЕ фильтрация — см. комментарий в app/models/material.py.
    is_deleted: bool = Field(default=False, index=True)
