# app/invoice_print/pdf_builder.py
# ============================================================
# Печатная форма счёта-фактуры в PDF — макет утверждён Вахтангом
# 2026-08-31 по образцу реального документа СФ-0000040 (после двух
# итераций правок: рамка "Увага!" по центру сверху с отступом,
# итоги "Разом без ПДВ/ПДВ/Всього з ПДВ" как последние 3 строки
# ОСНОВНОЙ таблицы позиций с общей рамкой вокруг суммы).
#
# Библиотека — reportlab (чистый Python, БЕЗ системных зависимостей),
# сознательно НЕ WeasyPrint: обсуждали 2026-08-31, WeasyPrint требует
# системных библиотек (Pango/Cairo) внутри Docker-образа на Railway,
# что означает отдельный шаг доработки деплоя (Dockerfile вместо
# Nixpacks) — риск рассинхронизации сред того же класса, что уже
# ловили с Postgres/SQLite (см. HANDOFF). reportlab ставится как
# обычный pip-пакет, работает одинаково в SQLite-тестах и на
# Railway.
#
# Кириллица — через встроенный TTF-шрифт DejaVuSans (файл лежит в
# app/invoice_print/fonts/, НЕ системный шрифт хоста — тот же принцип
# независимости от окружения).
#
# "Виписав(ла)" и "Рахунок дійсний до сплати до" — пока НЕТ полей в
# моделях Invoice/Firm под это (не обсуждали), печатаются как пустые
# строки для заполнения от руки — по умолчанию до явного запроса
# добавить соответствующие поля.
# ============================================================

import io
import os

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Table, TableStyle

from app.invoice_print.data import InvoicePrintData
from app.invoice_print.amount_in_words import amount_in_words_uk

_FONTS_DIR = os.path.join(os.path.dirname(__file__), "fonts")
_FONTS_REGISTERED = False


def _ensure_fonts_registered() -> None:
    global _FONTS_REGISTERED
    if _FONTS_REGISTERED:
        return
    pdfmetrics.registerFont(TTFont("DejaVuSans", os.path.join(_FONTS_DIR, "DejaVuSans.ttf")))
    pdfmetrics.registerFont(TTFont("DejaVuSans-Bold", os.path.join(_FONTS_DIR, "DejaVuSans-Bold.ttf")))
    _FONTS_REGISTERED = True


def build_invoice_pdf(data: InvoicePrintData) -> bytes:
    """Возвращает готовый PDF (bytes) печатной формы счёта."""
    _ensure_fonts_registered()

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    width, height = A4
    margin = 15 * mm
    y = height - margin

    def underlined_label(text, x, y_pos, font="DejaVuSans-Bold", size=9.5):
        c.setFont(font, size)
        c.drawString(x, y_pos, text)
        w = pdfmetrics.stringWidth(text, font, size)
        c.line(x, y_pos - 1.2, x + w, y_pos - 1.2)

    def wrapped(text, font="DejaVuSans", size=9, max_width=None, dy=4.3 * mm, x=None):
        nonlocal y
        if not text:
            y -= dy
            return
        if x is None:
            x = margin
        if max_width is None:
            max_width = width - 2 * margin - (x - margin)
        c.setFont(font, size)
        words = text.split(" ")
        cur = ""
        for w in words:
            test = (cur + " " + w).strip()
            if pdfmetrics.stringWidth(test, font, size) > max_width and cur:
                c.drawString(x, y, cur)
                y -= dy
                cur = w
            else:
                cur = test
        if cur:
            c.drawString(x, y, cur)
            y -= dy

    # --- "Увага!" в рамке, по центру сверху ---
    box_top = y
    c.setFont("DejaVuSans-Bold", 12)
    c.drawCentredString(width / 2, y - 5.5 * mm, "Увага!")
    c.setFont("DejaVuSans-Bold", 9.5)
    c.drawCentredString(width / 2, y - 10.5 * mm,
                         "У зв'язку з відкриттям нового розрахункового рахунку, реквізити змінені.")
    c.drawCentredString(width / 2, y - 15 * mm, "Рахунок закривається актом виконаних робіт.")
    box_bottom = y - 18.5 * mm
    c.setLineWidth(0.8)
    c.rect(margin, box_bottom, width - 2 * margin, box_top - box_bottom)
    y = box_bottom - 8 * mm

    # --- Постачальник / Одержувач / Платник ---
    label_x = margin
    value_x = margin + 33 * mm
    row_h = 4.6 * mm

    underlined_label("Постачальник", label_x, y)
    wrapped(data.firm_full_name, x=value_x, dy=row_h)
    egrpou_line = f"ЄДРПОУ {data.firm_egrpou_code}" if data.firm_egrpou_code else ""
    if data.firm_phone:
        egrpou_line += f", тел. {data.firm_phone}."
    wrapped(egrpou_line, x=value_x, dy=row_h)
    if data.firm_bank_account or data.firm_bank_name:
        wrapped(f"Р/р {data.firm_bank_account} в {data.firm_bank_name}", x=value_x, dy=row_h)
    if data.firm_bank_mfo:
        wrapped(f"МФО {data.firm_bank_mfo}", x=value_x, dy=row_h)
    if data.firm_tax_id or data.firm_vat_certificate_number:
        wrapped(f"ІПН {data.firm_tax_id}, номер свідоцтва {data.firm_vat_certificate_number}",
                x=value_x, dy=row_h)
    if data.firm_address:
        wrapped(f"Адреса {data.firm_address}", x=value_x, dy=row_h)

    underlined_label("Одержувач", label_x, y)
    wrapped(data.client_full_name, x=value_x, dy=row_h)
    if data.client_phone:
        wrapped(f"тел. {data.client_phone}", x=value_x, dy=row_h)

    underlined_label("Платник", label_x, y)
    wrapped("той самий" if data.is_same_payer else data.client_full_name, x=value_x, dy=row_h)

    y -= 3 * mm
    c.setFont("DejaVuSans-Bold", 12)
    c.drawCentredString(width / 2, y, f"Рахунок-фактура № {data.document_number}")
    y -= 5.2 * mm
    c.setFont("DejaVuSans", 10)
    c.drawCentredString(width / 2, y, f"від {data.document_date_str}")
    y -= 7 * mm

    # --- Основная таблица позиций + 3 строки итогов внизу (та же таблица) ---
    col_widths = [8 * mm, 68 * mm, 15 * mm, 24 * mm, 30 * mm, 32 * mm]
    header = ["№", "Назва", "Од.", "Кількість", "Ціна без ПДВ", "Сума без ПДВ"]
    table_data = [header]
    for line in data.lines:
        table_data.append([
            str(line.position), line.name, line.unit,
            f"{line.quantity:.3f}", f"{line.unit_price:.2f}", f"{line.line_total:.2f}",
        ])

    n_items = len(data.lines)
    table_data.append(["", "Разом без ПДВ:", "", "", "", f"{data.total_excl_vat:.2f}"])
    table_data.append(["", "ПДВ:", "", "", "", f"{data.vat_amount:.2f}"])
    table_data.append(["", "Всього з ПДВ:", "", "", "", f"{data.total_incl_vat:.2f}"])

    t = Table(table_data, colWidths=col_widths)
    totals_start = n_items + 1

    style = [
        ("FONTNAME", (0, 0), (-1, -1), "DejaVuSans"),
        ("FONTNAME", (0, 0), (-1, 0), "DejaVuSans-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("FONTSIZE", (0, 0), (-1, 0), 8.3),
        ("GRID", (0, 0), (-1, totals_start - 1), 0.5, colors.black),
        ("ALIGN", (0, 0), (0, totals_start - 1), "CENTER"),
        ("ALIGN", (3, 0), (-1, totals_start - 1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("SPAN", (1, totals_start), (4, totals_start)),
        ("SPAN", (1, totals_start + 1), (4, totals_start + 1)),
        ("SPAN", (1, totals_start + 2), (4, totals_start + 2)),
        ("FONTNAME", (1, totals_start), (-1, -1), "DejaVuSans-Bold"),
        ("ALIGN", (1, totals_start), (4, -1), "RIGHT"),
        ("ALIGN", (5, totals_start), (5, -1), "RIGHT"),
        ("BOX", (1, totals_start), (-1, -1), 0.8, colors.black),
        ("INNERGRID", (1, totals_start), (-1, -1), 0.5, colors.black),
        ("LINEABOVE", (1, totals_start), (-1, totals_start), 0.8, colors.black),
    ]
    t.setStyle(TableStyle(style))
    tw, th = t.wrapOn(c, width - 2 * margin, y)
    t.drawOn(c, margin, y - th)
    y -= th + 7 * mm

    wrapped("Всього на суму:", font="DejaVuSans", size=10)
    wrapped(amount_in_words_uk(data.total_incl_vat), font="DejaVuSans-Bold", size=10)
    wrapped(f"ПДВ:    {data.vat_amount:.2f} грн.", font="DejaVuSans", size=9.5)
    y -= 6 * mm

    c.setFont("DejaVuSans", 10)
    c.drawString(width / 2 - 5 * mm, y, "Виписав(ла):")
    c.line(width / 2 + 25 * mm, y - 1, width - margin, y - 1)
    y -= 10 * mm
    c.drawString(width / 2 - 5 * mm, y, "Рахунок дійсний до сплати до   .  .")

    c.save()
    return buf.getvalue()
