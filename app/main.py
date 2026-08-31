# app/main.py
# ============================================================
# Точка входа приложения. Подключает роутеры, создаёт таблицы
# при старте, отдаёт /health для CI-проверки (см.
# scripts/lib/test_build.py — именно этот эндпоинт опрашивается
# после запуска uvicorn в staging, чтобы понять "приложение живое").
# ============================================================

import os

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlmodel import Session, text

from app.database import init_db, engine, seed_constants
from app.engine.register import register_engine_tables
from app.processors.router import register_processors
from app.documents_chain.router import register_documents_chain
from app.invoice_print.router import register_invoice_print
from app.version import APP_VERSION

app = FastAPI(title="ЭлектроЩит — Учёт калькуляций")

_static_dir = os.path.join(os.path.dirname(__file__), "static")
app.mount("/static", StaticFiles(directory=_static_dir), name="static")

# Материалы и Бренды: только универсальный движок. Старые HTMX/Alpine/
# sqladmin варианты (materials.py, brands.py, materials_api.py,
# brands_api.py, alpine_pages.py, admin.py) удалены после того, как
# движок доказал себя рабочим — см. docs/HANDOFF.md.
# Пути: /material-v2, /brand-v2 (API: /api/material, /api/brand).
_templates = register_engine_tables(app)

# Раздел "Обработки" (меню NAV_MENU) — переиспользует то же Jinja2
# окружение, что и движок таблиц (тот же base.html, тот же APP_VERSION).
register_processors(app, _templates)

# Страница "Цепочка документов" (/documents-chain) — доступна только
# по кнопке "Показать подчинённые документы" в журнале заявок, своей
# ссылки в NAV_MENU сознательно нет (см. app/documents_chain/router.py).
register_documents_chain(app, _templates)

# Скачивание печатной формы счёта (кнопка "Скачать PDF" на карточке
# invoice) — GET /invoice-print/{invoice_id}/pdf, см.
# app/invoice_print/router.py.
register_invoice_print(app)


@app.on_event("startup")
def on_startup():
    init_db()
    seed_constants()


@app.get("/health")
def health():
    """
    Простая проверка живости — используется тестовой сборкой в CI.
    Не просто "процесс запустился", а ещё и "может достучаться до БД":
    иначе можно словить ложный успех, если БД недоступна, но uvicorn
    всё равно поднялся.
    """
    with Session(engine) as session:
        session.exec(text("SELECT 1"))
    return {"status": "ok"}


@app.get("/")
def root():
    return RedirectResponse(url="/material-v2")
