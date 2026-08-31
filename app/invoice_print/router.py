# app/invoice_print/router.py
# ============================================================
# Подключает GET /invoice-print/{invoice_id}/pdf — отдаёт готовый PDF
# счёта-фактуры (см. pdf_builder.py) для скачивания клиентом. Тот же
# паттерн "свой раздел вне универсального движка таблиц", что и у
# app/documents_chain/router.py (вызывается один раз из main.py).
#
# Путь БЕЗ префикса /api — это не JSON-эндпоинт движка, а прямая
# ссылка для браузера (кнопка "Скачать PDF" на карточке invoice —
# см. ActionButton с kind="link", app/engine/tables.py). Синхронная
# def (не async) — сборка PDF синхронная и небыстрая (reportlab), тот
# же принцип, что и у остальных обработчиков движка.
# ============================================================

from fastapi import APIRouter, FastAPI, HTTPException, Depends
from fastapi.responses import Response
from sqlmodel import Session

from app.database import get_session
from app.invoice_print.data import build_invoice_print_data
from app.invoice_print.pdf_builder import build_invoice_pdf


def register_invoice_print(app: FastAPI) -> None:
    router = APIRouter(tags=["invoice-print"])

    @router.get("/invoice-print/{invoice_id}/pdf")
    def download_invoice_pdf(invoice_id: int, session: Session = Depends(get_session)):
        data = build_invoice_print_data(invoice_id, session)
        if data is None:
            raise HTTPException(status_code=404, detail="Счёт не найден")

        pdf_bytes = build_invoice_pdf(data)
        filename = f"{data.document_number or ('invoice_' + str(invoice_id))}.pdf"
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    app.include_router(router)
