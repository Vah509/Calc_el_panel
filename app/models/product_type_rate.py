# app/models/product_type_rate.py
# ============================================================
# ProductTypeRate — справочник "Стоимость сборки" (2026-08-26).
# Плоская таблица: тип изделия -> стоимость часа работы по нему.
# Используется способом расчёта стоимости калькуляции "по часам"
# (Calculation.cost_method == "hours", см. app/models/calculation.py)
# — итоговая цена изделия учитывает assembly_hours * hourly_rate
# выбранной здесь записи (Calculation.product_type_rate_id).
#
# Бывают более сложные и более простые изделия, стоимость часа
# работы по ним может отличаться — отсюда отдельный справочник,
# а не одна общая константа "стоимость часа".
#
# Обычный плоский справочник движка (как Brand/Unit) — без
# hierarchy, delete_mode="soft" как у большинства справочников
# проекта (см. TableConfig в app/engine/tables.py).
# ============================================================

from typing import Optional
from sqlmodel import SQLModel, Field


class ProductTypeRate(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True)
    hourly_rate: float = Field(default=0.0)

    # is_deleted — визуальная пометка "к удалению" (soft-delete),
    # НЕ фильтрация — см. комментарий в app/models/material.py.
    is_deleted: bool = Field(default=False, index=True)
