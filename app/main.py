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
from sqlmodel import Session, select, text

from app.database import init_db, engine, get_session
from app.routers import materials, brands, materials_api, brands_api, alpine_pages

app = FastAPI(title="ЭлектроЩит — Учёт калькуляций")

_static_dir = os.path.join(os.path.dirname(__file__), "static")
app.mount("/static", StaticFiles(directory=_static_dir), name="static")

app.include_router(materials.router)
app.include_router(brands.router)

# ЭКСПЕРИМЕНТ: Alpine.js + JSON API — параллельные роуты, не
# затрагивают текущие рабочие /materials и /brands на HTMX.
app.include_router(materials_api.router)
app.include_router(brands_api.router)
app.include_router(alpine_pages.router)


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
    return RedirectResponse(url="/materials")
