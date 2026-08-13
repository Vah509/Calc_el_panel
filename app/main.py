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

from app.database import init_db, engine
from app.engine.register import register_engine_tables

app = FastAPI(title="ЭлектроЩит — Учёт калькуляций")

# Версия текущего билда — показывается в шапке каждой страницы (base.html),
# чтобы всегда было видно, какая версия сейчас открыта в браузере.
# Обновляется вручную при каждой значимой заливке — см. напоминание
# в конце ответа Claude при отправке нового архива.
APP_VERSION = "v25"

_static_dir = os.path.join(os.path.dirname(__file__), "static")
app.mount("/static", StaticFiles(directory=_static_dir), name="static")

# Материалы и Бренды: только универсальный движок. Старые HTMX/Alpine/
# sqladmin варианты (materials.py, brands.py, materials_api.py,
# brands_api.py, alpine_pages.py, admin.py) удалены после того, как
# движок доказал себя рабочим — см. docs/HANDOFF.md.
# Пути: /material-v2, /brand-v2 (API: /api/material, /api/brand).
register_engine_tables(app)


@app.on_event("startup")
def on_startup():
    init_db()


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
