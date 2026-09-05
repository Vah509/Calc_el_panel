# app/invoice_print/data.py
# ============================================================
# Сборка данных одного счёта (Invoice) в плоские dataclass — единая
# точка правды для ЛЮБОГО экспортёра печатной формы. Согласовано
# 2026-08-31 (Вахтанг: "нужно учесть, что нужно будет ещё
# экселевский вариант счёта") — расчёт сумм/прописи/реквизитов не
# должен дублироваться между pdf_builder.py и будущим
# xlsx_builder.py, поэтому вся работа с БД и сборка данных живёт
# ЗДЕСЬ, а builder'ы принимают уже готовый InvoicePrintData и просто
# рисуют.
#
# Единица измерения строки (InvoiceItem.unit_name) — СНЭПШОТ,
# заполняется напрямую из Calculation.unit_id при создании/
# обновлении строки счёта (см. _build_invoice_from_slot_handler,
# app/engine/tables.py) — печать просто читает готовое поле, без
# дополнительных join'ов. До v105 здесь был обходной путь через
# InvoiceItem.specification_item_id -> SpecificationItem ->
# Calculation (Specification выведена из цепочки документов, см.
# docs/HANDOFF_specification_cleanup.md) — убран, т.к. новая
# архитектура ("Перепроведение") всегда заполняет unit_name сама,
# а старых строк, созданных через Specification, в БД не осталось.
# ============================================================

from dataclasses import dataclass, field
from typing import Optional

from sqlmodel import Session, select

from app.models.invoice import Invoice
from app.models.invoice_item import InvoiceItem
from app.models.firm import Firm
from app.models.client import Client


@dataclass
class InvoicePrintLine:
    position: int
    name: str
    unit: str
    quantity: float
    unit_price: float          # unit_price_after_discount — цена, реально идущая клиенту
    line_total: float


@dataclass
class InvoicePrintData:
    document_number: str
    document_date_str: str      # "24 Серпня 2026 р."

    firm_full_name: str
    firm_egrpou_code: str
    firm_phone: str
    firm_bank_account: str
    firm_bank_name: str
    firm_bank_mfo: str
    firm_tax_id: str
    firm_vat_certificate_number: str
    firm_address: str

    client_full_name: str
    client_phone: str
    is_same_payer: bool         # True -> печатать "той самий" вместо повторного имени

    lines: list[InvoicePrintLine] = field(default_factory=list)

    total_excl_vat: float = 0.0
    vat_amount: float = 0.0
    total_incl_vat: float = 0.0


_UKR_MONTHS = [
    "", "Січня", "Лютого", "Березня", "Квітня", "Травня", "Червня",
    "Липня", "Серпня", "Вересня", "Жовтня", "Листопада", "Грудня",
]


def _format_date_uk(d) -> str:
    return f"{d.day} {_UKR_MONTHS[d.month]} {d.year} р."


def build_invoice_print_data(invoice_id: int, session: Session) -> Optional[InvoicePrintData]:
    invoice = session.get(Invoice, invoice_id)
    if not invoice:
        return None

    firm = session.get(Firm, invoice.firm_id) if invoice.firm_id else None
    client = session.get(Client, invoice.client_id) if invoice.client_id else None
    client_payer = (
        session.get(Client, invoice.client_invoice_id)
        if invoice.client_invoice_id else None
    )
    # "той самий" — если плательщик явно не задан отдельно, либо
    # совпадает с заказчиком (та же трактовка, что в Request:
    # "если поле не заполнено — плательщик по умолчанию = заказчик").
    is_same_payer = (
        client_payer is None
        or (client is not None and client_payer.id == client.id)
    )

    items = session.exec(
        select(InvoiceItem)
        .where(InvoiceItem.invoice_id == invoice_id)
        .order_by(InvoiceItem.id)
    ).all()

    lines: list[InvoicePrintLine] = []
    for idx, item in enumerate(items, start=1):
        lines.append(InvoicePrintLine(
            position=idx,
            name=item.product_name,
            unit=item.unit_name,
            quantity=item.quantity,
            unit_price=item.unit_price_after_discount,
            line_total=item.line_total,
        ))

    return InvoicePrintData(
        document_number=invoice.document_number,
        document_date_str=_format_date_uk(invoice.document_date),
        firm_full_name=firm.full_name if firm else "",
        firm_egrpou_code=firm.egrpou_code if firm else "",
        firm_phone=firm.phone if firm else "",
        firm_bank_account=firm.bank_account if firm else "",
        firm_bank_name=firm.bank_name if firm else "",
        firm_bank_mfo=firm.bank_mfo if firm else "",
        firm_tax_id=firm.tax_id if firm else "",
        firm_vat_certificate_number=firm.vat_certificate_number if firm else "",
        firm_address=firm.address if firm else "",
        client_full_name=(client.full_name if client else ""),
        client_phone=(client.phone if client else ""),
        is_same_payer=is_same_payer,
        lines=lines,
        total_excl_vat=invoice.total_excl_vat,
        vat_amount=invoice.vat_amount,
        total_incl_vat=invoice.total_incl_vat,
    )
