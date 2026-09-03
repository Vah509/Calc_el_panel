# app/models/invoice.py
# ============================================================
# Invoice (рахунок-фактура / счёт) — четвёртый документ цепочки
# zayavka -> calculation -> specification -> invoice (обсуждение
# 2026-08-29, образец печатной формы — СФ-0000040).
#
# request_id — FK на Request, родитель В ЦЕПОЧКЕ ДОКУМЕНТОВ (см.
# app/engine/document_chain.py), ВСЕГДА заполнен и НИКОГДА не
# сбрасывается — счёт остаётся виден в цепочке заявки независимо от
# того, привязан ли он ещё к своей спецификации (см. specification_id
# ниже). Это отличает связь с request от связи с specification.
#
# specification_id — FK на Specification, ОБЯЗАТЕЛЕН при создании
# (счёт всегда собирается ИЗ спецификации), но nullable дальше —
# кнопка "Отвязать" сбрасывает его в NULL, оставляя все остальные
# поля/позиции как есть (решение Вахтанга 2026-08-29: "счёт
# остаётся как есть, всё редактируется, просто мы не обновляем
# его" — отвязка нужна, чтобы зафиксировать выставленную клиенту
# цену, даже если спецификацию/калькуляции потом пересчитают).
# Пока specification_id заполнен — кнопка "Обновить" на счёте вправе
# перечитать позиции из спецификации заново (см.
# _build_invoice_handler/_refresh_invoice_items_handler в
# app/engine/tables.py). После отвязки повторное нажатие
# "Создать счёт" у ТОЙ ЖЕ спецификации не находит "своего" счёта
# (ищет по specification_id) и создаёт НОВЫЙ документ Invoice.
#
# client_id / client_invoice_id — СНЭПШОТ Request.client_id /
# Request.client_invoice_id на момент создания (тот же принцип, что
# у Specification.client_id) — не live-ссылка через request_id,
# чтобы более поздняя правка заявки не "сдвигала" уже выставленный
# счёт задним числом. client_invoice_id — Плательщик в шапке печатной
# формы (см. Request.client_invoice_id: "заказчик может быть не тем,
# кто платит"); если у заявки это поле не заполнено, при создании
# счёта подставляется client_id (плательщик по умолчанию = заказчик).
#
# firm_id — FK на Firm (справочник СВОИХ юрлиц-продавцов, см.
# app/models/firm.py) — "Постачальник" в шапке. При создании
# подставляется дефолтная фирма (Firm.is_default=True), дальше
# свободно редактируется.
#
# total_excl_vat / vat_amount / total_incl_vat — снэпшот итогов,
# пересчитывается заново на каждое сохранение позиций (см.
# _recalculate_invoice_totals в app/engine/tables.py) — Σ по
# InvoiceItem.line_total (уже с учётом построчной скидки/наценки) и
# фиксированная ставка НДС из справочника constants (тот же
# constants['vat_rate'], что использует material/calculation).
#
# document_number/document_date/document_time — тот же принцип
# нумерации, что и у request/calculation/specification, свой
# префикс "I" (см. app/engine/document_numbering.py — единственный
# ещё не занятый однобуквенный префикс из R/C/S).
#
# is_frozen — добавлено v96 (план "Перепроведение", см.
# docs/HANDOFF_reprovodenie.md). Заменяет собой смысл кнопки
# "Отвязать" (specification_id -> NULL) в НОВОЙ схеме, где счёт
# создаётся напрямую из отмеченных калькуляций заявки, минуя
# спецификацию. False по умолчанию — обычный счёт.
#
# Переключается вручную человеком (кнопка "Заморозить" на форме
# счёта, точное место в UI — сессия 5), НЕ автоматически по событию
# типа печати PDF (решение Вахтанга 2026-09-03).
#
# Логика при "Создать счёт" по набору отмеченных калькуляций (см.
# handler в сессии 4):
#   - is_frozen=False (обычный, или ранее уже существующий для
#     этого набора) -> обновляется НА МЕСТЕ (merge по
#     InvoiceItem.calculation_id, discount_percent на совпавших
#     позициях сохраняется);
#   - is_frozen=True, или счёта для этого набора ещё нет ->
#     создаётся НОВЫЙ документ Invoice (is_frozen=False по
#     умолчанию для нового).
# ============================================================

from datetime import date, time, datetime
from typing import Optional
from sqlmodel import SQLModel, Field


def _now_time() -> time:
    return datetime.now().time().replace(microsecond=0)


class Invoice(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    document_number: str = Field(default="")
    document_date: date = Field(default_factory=date.today)
    document_time: time = Field(default_factory=_now_time)

    request_id: Optional[int] = Field(default=None, foreign_key="request.id")
    specification_id: Optional[int] = Field(default=None, foreign_key="specification.id")

    firm_id: Optional[int] = Field(default=None, foreign_key="firm.id")
    client_id: Optional[int] = Field(default=None, foreign_key="client.id")
    client_invoice_id: Optional[int] = Field(default=None, foreign_key="client.id")

    total_excl_vat: float = Field(default=0.0)
    vat_amount: float = Field(default=0.0)
    total_incl_vat: float = Field(default=0.0)

    is_frozen: bool = Field(default=False)

    # is_deleted — визуальная пометка "к удалению" (soft-delete),
    # НЕ фильтрация — см. комментарий в app/models/material.py.
    is_deleted: bool = Field(default=False, index=True)
