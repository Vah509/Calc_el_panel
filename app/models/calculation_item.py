# app/models/calculation_item.py
# ============================================================
# CalculationItem — одна позиция материала в составе калькуляции
# (вкладка «Материалы» формы calculation). Отличается от KitItem
# принципиально важной деталью: здесь ЦЕНА — СНЭПШОТ, а не живая
# ссылка на material.price_excl_vat.
#
# Почему снэпшот (решение Вахтанга, 2026-08-23): в будущем
# спецификация должна показывать материал, его единицу измерения
# (живой lookup на material/unit по material_id), количество и
# ЦЕНУ, ЗАФИКСИРОВАННУЮ в калькуляции — не текущую цену из
# справочника. Если бы цена всегда бралась live, стоимость
# калькуляции "плавала" бы при любом изменении прайса материала,
# что ломало бы уже согласованные с клиентом расчёты.
#
# price_excl_vat здесь — КОПИЯ Material.price_excl_vat на момент
# добавления позиции ЛИБО на момент последнего нажатия "Пересчитать"
# (см. _recalc_prices_handler в app/engine/tables.py). Между
# пересчётами цена в позиции не меняется, даже если материал в
# справочнике подорожал/подешевел — это ожидаемое поведение
# ("замороженная" цена), не баг.
#
# material_id, quantity — как у KitItem. name/unit НЕ дублируются
# здесь (не денормализуются) — при отображении подтягиваются live
# через material_id -> material.short_name / material.unit_id ->
# unit.name, т.к. название/единица материала не "снэпшотятся"
# осознанно (Вахтанг: важно зафиксировать именно количество и цену,
# название/единица показываются актуальные).
#
# calculation_id — FK на Calculation. Нет soft-delete (is_deleted) —
# та же логика, что и у KitItem: ничто не ссылается на конкретный
# CalculationItem напрямую (будущая спецификация будет строиться по
# снимку на момент своего формирования, не по live-ссылке на
# CalculationItem.id), поэтому удаление позиции — всегда безусловное
# физическое удаление сразу (delete_mode="hard" в движке, дефолт).
#
# quantity — float, не int: та же причина, что и у KitItem (метры
# кабеля, ленты и т.п.).
# ============================================================

from typing import Optional
from sqlmodel import SQLModel, Field


class CalculationItem(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    calculation_id: Optional[int] = Field(default=None, foreign_key="calculation.id")
    material_id: Optional[int] = Field(default=None, foreign_key="material.id")
    quantity: float = Field(default=1.0)

    # Снэпшот Material.price_excl_vat на момент добавления/последнего
    # пересчёта — см. обоснование в комментарии модуля выше.
    price_excl_vat: float = Field(default=0.0)
