# app/models/kit.py
# ============================================================
# Kit — комплект (третий, нижний уровень иерархии разделов
# комплектов: kit_group -> kit_section -> kit). Пример: в разделе
# "Подключение силовых автоматов" сами комплекты — "Подключение
# ВА47 3P 63А", "Подключение ВА47 3P 100А" и т.д.
#
# ВРЕМЕННО (v39) заведён как ОБЫЧНАЯ ПЛОСКАЯ ТАБЛИЦА старого
# движка (список + модалка, kit_section_id — простой select без
# поиска, Relation), а не как третий уровень drill-down дерева.
# Осознанное решение Вахтанга: нужен быстрый способ вручную занести
# пробные записи ДО того, как будет спроектирован и закодирован
# полноценный подбор материалов внутри карточки комплекта — это
# отдельная большая задача. Когда подбор будет готов, эта же модель
# подключится к drill-down движку (hierarchy без child_key,
# edit_mode="own_page", delete_mode="soft" — see HANDOFF_kits_and_
# calculation.md) без изменения схемы данных, только конфиг в
# tables.py и сама карточка поменяются.
#
# is_deleted — soft-delete, а не "hard"/"simple" как у kit_group/
# kit_section: на kit в будущем ссылаются calculation_item (см.
# HANDOFF_kits_and_calculation.md, принцип "живая ссылка"), поэтому
# нужен purge-processor с проверкой использования, а не простое
# физическое удаление "если нет детей" (у kit as such детей нет —
# kit_items это состав, не дочерний уровень дерева).
# ============================================================

from typing import Optional
from sqlmodel import SQLModel, Field


class Kit(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True)
    sort_order: int = Field(default=0)
    kit_section_id: Optional[int] = Field(default=None, foreign_key="kitsection.id")

    # is_deleted — визуальная пометка "к удалению" (soft-delete),
    # НЕ фильтрация — см. комментарий в app/models/material.py.
    is_deleted: bool = Field(default=False, index=True)
