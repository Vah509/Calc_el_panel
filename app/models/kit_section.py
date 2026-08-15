# app/models/kit_section.py
# ============================================================
# KitSection — второй (нижний) уровень двухуровневой иерархии
# разделов комплектов (kit_group -> kit_section -> kit). Пример:
# в группе "Подключение" подраздел "Подключение силовых
# автоматов" объединяет сами комплекты ("Подключение автомата
# 100А" и т.д.).
#
# sort_order — управляемый порядок обхода внутри своей группы,
# по той же логике, что и KitGroup.sort_order.
# ============================================================

from typing import Optional
from sqlmodel import SQLModel, Field


class KitSection(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True)
    sort_order: int = Field(default=0)
    kit_group_id: Optional[int] = Field(default=None, foreign_key="kitgroup.id")

    # is_deleted — визуальная пометка "к удалению" (soft-delete),
    # НЕ фильтрация — см. комментарий в app/models/material.py.
    is_deleted: bool = Field(default=False, index=True)
