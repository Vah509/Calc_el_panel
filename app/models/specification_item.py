# app/models/specification_item.py
# ============================================================
# SpecificationItem — одна строка спецификации (см. подробный
# комментарий механики формирования в app/models/specification.py).
#
# Каждая строка соответствует ОДНОЙ калькуляции — БЕЗ схлопывания
# повторов, даже если у нескольких калькуляций совпадает product_name
# (решение Вахтанга 2026-08-27). Это отличает SpecificationItem от,
# например, CalculationItem, где количество тоже своё поле, но смысл
# другой — здесь "строка = калькуляция", там "строка = позиция
# состава".
#
# specification_id — FK на Specification (родитель, шапка документа).
#
# calculation_id — FK на Calculation, НЕ для live-подтяжки цены (та
# же логика снимка, что у Kit -> KitItem применительно к
# калькуляции — см. calculation_item.py), а чтобы при БУДУЩЕМ
# повторном формировании (или диагностике/трассировке) можно было
# пройти по ссылке и увидеть, из какой именно калькуляции взята
# строка. Nullable — на случай, если исходная калькуляция будет
# впоследствии удалена: строка спецификации (уже сформированный
# снимок) не должна исчезать или падать вместе с ней.
#
# product_name/unit_price/quantity/line_total — СНЭПШОТЫ на момент
# формирования спецификации:
#   - product_name  <- Calculation.full_name
#   - unit_price    <- Calculation.final_total (цена ОДНОГО изделия)
#   - quantity      <- Calculation.quantity
#   - line_total    = unit_price * quantity
# Между формированиями (повторными нажатиями кнопки "Спека N")
# ничего не "плывёт" само по себе — та же философия "замороженной"
# цены, что и у CalculationItem.price_excl_vat.
#
# Нет soft-delete (is_deleted) — та же логика, что и у
# CalculationItem/KitItem: строки полностью удаляются и создаются
# заново при каждом формировании спецификации (delete-all+create-all,
# delete_mode="hard" в движке, дефолт), отдельного ручного
# редактирования строк спецификации в этом шаге нет.
# ============================================================

from typing import Optional
from sqlmodel import SQLModel, Field


class SpecificationItem(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    specification_id: Optional[int] = Field(default=None, foreign_key="specification.id")
    calculation_id: Optional[int] = Field(default=None, foreign_key="calculation.id")
    product_name: str = Field(default="")
    unit_price: float = Field(default=0.0)
    quantity: float = Field(default=1.0)
    line_total: float = Field(default=0.0)
