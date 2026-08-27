# app/models/specification.py
# ============================================================
# Specification (спецификация) — третий документ цепочки
# zayavka -> calculation -> specification -> invoice (см.
# docs/HANDOFF_kits_and_calculation.md, раздел 2.6). Промежуточный
# документ между калькуляциями одного варианта (бренда) заявки и
# будущим счётом-фактурой: перечень изделий не всегда переносится в
# счета 1-в-1 (из одной спецификации может быть создано НЕСКОЛЬКО
# счетов), поэтому спецификация — стабильная база для такой гибкой
# нарезки, а не просто представление калькуляций "на лету".
#
# ЭТО СНИМОК, не live-агрегация калькуляций (та же логика, что и у
# calculation_item.price_excl_vat — см. app/models/calculation_item.py):
# если бы спецификация каждый раз пересчитывалась динамически, то
# после того как её "нарезали" на выставленный счёт, а исходную
# калькуляцию потом изменили/пересчитали — уже выставленный счёт
# задним числом "поехал" бы в цене, что недопустимо для финансового
# документа.
#
# request_id — FK на Request, родитель В ЦЕПОЧКЕ ДОКУМЕНТОВ (см.
# app/engine/document_chain.py) — сознательно НЕ calculation, потому
# что одна спецификация агрегирует НЕСКОЛЬКО калькуляций сразу (все
# активные калькуляции этой заявки с данным brand_slot), связь
# calculation -> specification была бы N:1 и не вписывалась бы в
# текущую линейную модель CHAIN_LINKS (один FK = один родитель).
# specification_item.calculation_id (см. ниже) даёт трассировку к
# конкретным калькуляциям для будущего перечитывания.
#
# brand_slot — номер варианта (1/2/3), тот же принцип, что и у
# Calculation.brand_slot и Request.brand_slot_N_id — сама спецификация
# формируется ПО ОДНОМУ варианту сразу (кнопка "Спека N" собирает
# только калькуляции этого слота).
#
# client_id — FK на Client, СНЭПШОТ Request.client_id на момент
# формирования (не live-relation через request_id) — тот же принцип
# "снимок", что и у остальных полей документа: если заказчика в
# заявке позже поменяют, уже сформированная спецификация не должна
# "поехать" следом.
#
# total_amount — снэпшот суммы всех SpecificationItem.line_total,
# пересчитывается заново при каждом формировании (см. механику ниже).
#
# document_number/document_date/document_time — тот же принцип
# нумерации, что и у request/calculation (см.
# app/engine/document_numbering.py), свой префикс "S".
#
# Механика формирования (row_action "Спека N" на request, см.
# _build_specification_handler в app/engine/tables.py):
#   1. Собрать все Calculation с request_id=этой заявки,
#      brand_slot=N, status="active" (черновики/к архивации/к
#      удалению НЕ включаются — решение Вахтанга 2026-08-27).
#   2. Если для этой пары (request_id, brand_slot) уже есть
#      Specification — удалить её вместе со всеми её
#      SpecificationItem, создать заново (полная перезапись, а не
#      правка построчно — то же "delete-all+create-all", что описано
#      в HANDOFF_kits_and_calculation.md).
#   3. Создать новую Specification (client_id = request.client_id).
#   4. На каждую отобранную калькуляцию — одна SpecificationItem
#      (product_name=Calculation.full_name, unit_price=
#      Calculation.final_total, quantity=Calculation.quantity,
#      line_total=unit_price*quantity) — БЕЗ схлопывания повторов:
#      каждая калькуляция — всегда отдельная строка, даже если
#      product_name у нескольких калькуляций совпадает (решение
#      Вахтанга 2026-08-27).
#   5. total_amount = Σ line_total.
# Кнопка НЕ пересчитывает сами калькуляции перед сборкой — берёт
# final_total как есть на момент нажатия (решение Вахтанга
# 2026-08-27: "кнопка только собирает и показывает спеку").
# ============================================================

from datetime import date, time, datetime
from typing import Optional
from sqlmodel import SQLModel, Field


def _now_time() -> time:
    return datetime.now().time().replace(microsecond=0)


class Specification(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    document_number: str = Field(default="")
    document_date: date = Field(default_factory=date.today)
    document_time: time = Field(default_factory=_now_time)
    request_id: Optional[int] = Field(default=None, foreign_key="request.id")
    brand_slot: Optional[int] = Field(default=None)
    client_id: Optional[int] = Field(default=None, foreign_key="client.id")
    total_amount: float = Field(default=0.0)

    # is_deleted — визуальная пометка "к удалению" (soft-delete),
    # НЕ фильтрация — см. комментарий в app/models/material.py.
    is_deleted: bool = Field(default=False, index=True)
