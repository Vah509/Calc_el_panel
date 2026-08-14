# app/processors/router.py
# ============================================================
# Подключает страницу /processors и API POST /api/processors/{key}/run
# в приложение. Вызывается один раз из main.py, аналогично
# register_engine_tables для движка таблиц.
# ============================================================

from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.database import get_session
from app.processors.page import render_processors_page
from app.processors.registry import get_processor


def register_processors(app: FastAPI, templates: Jinja2Templates) -> None:
    router = APIRouter(tags=["processors"])

    @router.get("/processors", response_class=HTMLResponse)
    def processors_page():
        return render_processors_page(templates.env)

    @router.post("/api/processors/{key}/run")
    def run_processor(key: str):
        processor = get_processor(key)
        if processor is None:
            raise HTTPException(status_code=404, detail="Обработчик не найден")
        session_gen = get_session()
        session = next(session_gen)
        try:
            result = processor.run(session)
        finally:
            session_gen.close()
        return {"message": result.message, "processed": result.processed, "updated": result.updated}

    app.include_router(router)
