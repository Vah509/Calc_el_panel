# app/database.py
# ============================================================
# Подключение к БД через SQLModel.
#
# DATABASE_URL берётся из переменной окружения — это единая точка
# конфигурации что для Railway (там будет строка Postgres), что для
# локального запуска, что для тестовой сборки в CI (там будет SQLite,
# чтобы раннер GitHub Actions был самодостаточным и не поднимал
# отдельный сервис БД).
#
# Если переменная не задана вообще — используем sqlite-файл рядом
# с проектом, чтобы можно было просто `uvicorn app.main:app` без
# какой-либо настройки для быстрой локальной проверки.
# ============================================================

import os
from sqlmodel import SQLModel, Session, create_engine

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./local.db")

# connect_args нужен только для SQLite (разрешаем использование
# соединения из разных потоков — uvicorn может обращаться к БД
# не из того потока, где было создано соединение).
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(DATABASE_URL, echo=False, connect_args=connect_args)


def init_db() -> None:
    """Создаёт таблицы, если их ещё нет. На старте приложения."""
    SQLModel.metadata.create_all(engine)


def get_session():
    """Дать сессию БД на время одного запроса (FastAPI Depends)."""
    with Session(engine) as session:
        yield session
