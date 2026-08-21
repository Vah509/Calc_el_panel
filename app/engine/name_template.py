# app/engine/name_template.py
# ============================================================
# Подстановка плейсхолдеров в шаблон полного названия калькуляции
# (Calculation.name_template -> Calculation.full_name).
#
# Пересчёт НЕ автоматический — вызывается только по кнопке
# "Пересчитать название" (см. extra_actions в app/engine/tables.py и
# обработчик в app/engine/api.py), решение Вахтанга: не перезаписывать
# руками поправленное full_name при каждом save.
#
# Поддерживаемые плейсхолдеры на этом шаге (согласовано 2026-08-21):
#   {client_name}     — Calculation.client_name (рабочее название)
#   {brand_slot}      — Calculation.brand_slot (число 1/2/3, или
#                        пусто, если слот не выбран)
#   {request_number}  — document_number связанной заявки (через
#                        request_id); пусто, если заявка не привязана
#
# Неизвестный плейсхолдер в шаблоне оставляется как есть (не падает,
# не подставляет пустоту молча) — так человек сразу видит опечатку
# в фигурных скобках, а не теряет часть названия без объяснения.
# ============================================================

from typing import Optional
from sqlmodel import Session


def render_name_template(
    template: str,
    *,
    client_name: str,
    brand_slot: Optional[int],
    request_number: Optional[str],
) -> str:
    """Собирает full_name из name_template и текущих значений полей.
    Чистая функция, без обращения к БД — все значения передаются
    готовыми (request_number уже вытянут из связанной заявки
    вызывающим кодом, см. build_full_name_for_calculation)."""
    values = {
        "client_name": client_name or "",
        "brand_slot": str(brand_slot) if brand_slot else "",
        "request_number": request_number or "",
    }
    result = template
    for key, value in values.items():
        result = result.replace("{" + key + "}", value)
    return result


def build_full_name_for_calculation(session: Session, calculation) -> str:
    """Обёртка над render_name_template, которая сама вытягивает
    номер связанной заявки (request_number) по calculation.request_id,
    если он задан. calculation — уже загруженный instance модели
    Calculation (или dict с теми же ключами)."""
    request_number = None
    request_id = getattr(calculation, "request_id", None) if not isinstance(calculation, dict) else calculation.get("request_id")
    if request_id:
        from app.models.request import Request
        req = session.get(Request, request_id)
        if req:
            request_number = req.document_number

    if isinstance(calculation, dict):
        client_name = calculation.get("client_name", "")
        brand_slot = calculation.get("brand_slot")
        template = calculation.get("name_template", "")
    else:
        client_name = calculation.client_name
        brand_slot = calculation.brand_slot
        template = calculation.name_template

    return render_name_template(
        template,
        client_name=client_name,
        brand_slot=brand_slot,
        request_number=request_number,
    )
