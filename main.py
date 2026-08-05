import os

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

app = FastAPI(title="Pricing App — Электрощиты")


@app.get("/", response_class=HTMLResponse)
async def root():
    """
    Стартовая страница. Показывает, что приложение живо и (если задана)
    подключение к базе данных настроено.
    """
    db_status = "не настроена (переменная DATABASE_URL отсутствует)"
    db_url = os.environ.get("DATABASE_URL")
    if db_url:
        # Не выводим сам URL целиком (там пароль) — только факт наличия
        db_status = "переменная DATABASE_URL найдена ✅"

    return f"""
    <html>
        <head>
            <meta charset="utf-8">
            <title>Pricing App</title>
            <style>
                body {{
                    font-family: -apple-system, Segoe UI, Roboto, sans-serif;
                    max-width: 640px;
                    margin: 60px auto;
                    padding: 0 20px;
                    color: #1a1a1a;
                }}
                .ok {{ color: #16a34a; font-weight: 600; }}
                code {{
                    background: #f1f1f1;
                    padding: 2px 6px;
                    border-radius: 4px;
                }}
            </style>
        </head>
        <body>
            <h1>🎉 Деплой прошёл успешно</h1>
            <p class="ok">Приложение запущено и отвечает на запросы.</p>
            <p>Статус базы данных: {db_status}</p>
            <p>Это стартовый каркас проекта автоматизации ценообразования
            электрощитов. Дальше сюда будет добавляться функциональность
            блок за блоком.</p>
        </body>
    </html>
    """


@app.get("/health")
async def health():
    """Простой healthcheck-эндпоинт — Railway может его использовать
    для проверки, что сервис жив."""
    return {"status": "ok"}
