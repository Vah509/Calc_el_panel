# app/models/invoice_item.py
# ============================================================
# InvoiceItem — одна строка счёта. "Строка = калькуляция" — строится
# напрямую из отмеченных Calculation заявки (см.
# _build_invoice_from_slot_handler, app/engine/tables.py), минуя
# Specification (выведена из цепочки документов, см.
# docs/HANDOFF_specification_cleanup.md).
#
# invoice_id — FK на Invoice (родитель, шапка документа).
#
# calculation_id — FK на Calculation, ЖИВАЯ трассировка строки счёта
# на калькуляцию, из которой она собрана. Используется как ключ
# merge-логики при обновлении незамороженного счёта (см.
# Invoice.is_frozen) — искать существующую InvoiceItem по
# calculation_id, чтобы сохранить discount_percent на совпавших
# позициях вместо delete-all+create-all.
#
# product_name/unit_name/unit_price/quantity — СНЭПШОТЫ на момент
# создания/обновления строки счёта, копируются из Calculation
# (product_name <- Calculation.full_name, unit_name <-
# Calculation.unit_id -> Unit.name, unit_price <-
# Calculation.final_total, quantity <- Calculation.quantity). Не
# живые ссылки — если калькуляцию поменяют ПОСЛЕ создания счёта,
# здесь ничего не изменится, пока счёт не пересоздадут кнопкой
# "Створити рахунок" повторно (см. handler).
#
# discount_percent — РЕДАКТИРУЕМОЕ человеком поле (в отличие от
# остальных полей строки, которые снэпшот) — единственное поле,
# которое человек правит напрямую. Знак определяет скидку/наценку:
# -10 = скидка 10%, +10 = наценка 10% (решение Вахтанга 2026-08-29).
# 0 по умолчанию — новая строка без скидки.
#
# unit_price_after_discount / line_total — РАСЧЁТНЫЕ поля, всегда
# производные от unit_price/discount_percent/quantity:
#   unit_price_after_discount = unit_price * (1 + discount_percent/100)
#   line_total = unit_price_after_discount * quantity
# Пересчитываются на бэкенде при каждом сохранении строки (см.
# _recalculate_invoice_item в app/engine/tables.py) — то же
# правило "сервер — финальный источник истины", что у
# ComputedPair (см. app/engine/config.py), просто не через
# универсальный ComputedPair-механизм (там нет умножения на третье
# поле quantity).
#
# Нет soft-delete — строки удаляются/пересоздаются вместе со всем
# счётом при повторном формировании (merge по calculation_id).
# ============================================================

from typing import Optional
from sqlmodel import SQLModel, Field


class InvoiceItem(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    invoice_id: Optional[int] = Field(default=None, foreign_key="invoice.id")
    calculation_id: Optional[int] = Field(default=None, foreign_key="calculation.id")

    product_name: str = Field(default="")
    unit_name: str = Field(default="")
    quantity: float = Field(default=1.0)
    unit_price: float = Field(default=0.0)
    discount_percent: float = Field(default=0.0)
    unit_price_after_discount: float = Field(default=0.0)
    line_total: float = Field(default=0.0)
