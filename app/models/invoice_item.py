# app/models/invoice_item.py
# ============================================================
# InvoiceItem — одна строка счёта (см. подробный комментарий
# механики в app/models/invoice.py). "Строка = калькуляция" — тот
# же принцип, что и у SpecificationItem (одна SpecificationItem уже
# = одна калькуляция, InvoiceItem копирует её 1-в-1 при создании
# счёта), решение Вахтанга 2026-08-29.
#
# invoice_id — FK на Invoice (родитель, шапка документа).
#
# specification_item_id — FK на SpecificationItem, ТОЛЬКО для
# трассировки (аналог SpecificationItem.calculation_id) — не для
# live-подтяжки цены. Nullable — если исходная SpecificationItem
# будет физически удалена (спецификация переформирована заново),
# уже созданная строка счёта не должна пропасть вместе с ней (тот
# же принцип "замороженного снимка", что у specification_item.
# calculation_id).
#
# product_name/unit_name/unit_price/quantity — СНЭПШОТЫ на момент
# создания/обновления строки счёта:
#   - product_name <- SpecificationItem.product_name
#   - unit_name    <- SpecificationItem.calculation_id -> Calculation.unit_id
#                      -> Unit.name (SpecificationItem САМА не хранит unit —
#                      см. комментарий в specification_item.py; путь тот же,
#                      что раньше использовался ТОЛЬКО в печатных формах,
#                      см. app/invoice_print/data.py). Добавлено 2026-08-31
#                      по прямому запросу Вахтанга — колонка "Од." нужна не
#                      только в PDF/Excel, но и в самой табличке позиций
#                      счёта на форме редактирования. СНЭПШОТ, не живая
#                      ссылка на Unit (решение Вахтанга: "как и остальные
#                      поля InvoiceItem") — если единицу измерения в
#                      калькуляции поменяют ПОСЛЕ создания счёта, здесь
#                      ничего не изменится, ту же логику "замороженного
#                      снимка" уже используют product_name/unit_price.
#   - unit_price   <- SpecificationItem.unit_price (цена БЕЗ скидки)
#   - quantity     <- SpecificationItem.quantity
#
# discount_percent — РЕДАКТИРУЕМОЕ человеком поле (в отличие от
# остальных полей строки, которые снэпшот) — единственное поле
# InvoiceItem, не заимствованное из спецификации. Знак определяет
# скидку/наценку: -10 = скидка 10%, +10 = наценка 10% (решение
# Вахтанга 2026-08-29). 0 по умолчанию — новая строка без скидки.
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
# счётом при повторном формировании из спецификации (тот же принцип,
# что у CalculationItem/SpecificationItem), отдельного ручного
# удаления одной строки в этом шаге нет.
#
# calculation_id — FK на Calculation, добавлено v96 (план
# "Перепроведение", см. docs/HANDOFF_reprovodenie.md) — НОВАЯ прямая
# трассировка строки счёта на калькуляцию, взамен пути через
# specification_item_id -> SpecificationItem -> calculation_id.
# Причина: спецификация как документ-прослойка выводится из цепочки
# (Request -> вкладки по брендам с чекбоксами калькуляций -> Invoice
# напрямую), specification_item_id сохранён только для СТАРЫХ строк
# и печатных форм, дальше не используется для новых.
#
# Nullable, СТРОГО не бэкфиллится сейчас — старые строки (созданные
# через путь Specification, есть в проде) остаются с
# calculation_id=NULL, ничего не трогаем. НОВЫЕ строки (создаваемые
# в обход спецификации, см. план "Сессия 4") будут заполнять это
# поле сразу при создании. Задача связать старые строки с
# calculation_id задним числом (через
# specification_item_id -> SpecificationItem.calculation_id)
# сознательно отложена до финального удаления таблиц
# Specification/SpecificationItem (последний пункт плана) — решение
# Вахтанга 2026-09-03, чтобы не рисковать существующими данными
# раньше времени.
#
# Используется как ключ merge-логики при обновлении незамороженного
# счёта (см. Invoice.is_frozen) — искать существующую InvoiceItem по
# calculation_id, чтобы сохранить discount_percent на совпавших
# позициях вместо текущего delete-all+create-all.
# ============================================================

from typing import Optional
from sqlmodel import SQLModel, Field


class InvoiceItem(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    invoice_id: Optional[int] = Field(default=None, foreign_key="invoice.id")
    specification_item_id: Optional[int] = Field(default=None, foreign_key="specificationitem.id")
    calculation_id: Optional[int] = Field(default=None, foreign_key="calculation.id")

    product_name: str = Field(default="")
    unit_name: str = Field(default="")
    quantity: float = Field(default=1.0)
    unit_price: float = Field(default=0.0)
    discount_percent: float = Field(default=0.0)
    unit_price_after_discount: float = Field(default=0.0)
    line_total: float = Field(default=0.0)
