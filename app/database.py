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
from sqlmodel import SQLModel, Session, create_engine, select

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./local.db")

# connect_args нужен только для SQLite (разрешаем использование
# соединения из разных потоков — uvicorn может обращаться к БД
# не из того потока, где было создано соединение).
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(DATABASE_URL, echo=False, connect_args=connect_args)


def _ensure_is_deleted_columns() -> None:
    """
    SQLModel.metadata.create_all() создаёт только отсутствующие
    ТАБЛИЦЫ целиком — если таблица material/brand уже существует
    на Railway (Postgres) без новой колонки is_deleted (soft-delete,
    добавлено после того, как эти таблицы уже были в проде), она
    останется без неё молча, и первое же обращение к is_deleted
    упадёт с ошибкой БД.

    Поэтому для каждой (таблица, колонка) при старте проверяем через
    information_schema (Postgres) — если колонки нет, добавляем её
    сами через ALTER TABLE. Идемпотентно: если колонка уже есть
    (например при переносах между окружениями), ничего не делаем.
    NOT NULL DEFAULT false безопасен и для существующих строк —
    Postgres проставит значение всем сразу при добавлении колонки.

    Для SQLite (локальная разработка) эта миграция не нужна —
    create_all и так создаёт таблицу с нуля со всеми полями модели.
    """
    if not DATABASE_URL.startswith("postgres"):  # покрывает и postgres://, и postgresql://
        return
    from sqlalchemy import text

    tables_columns = [("material", "is_deleted"), ("brand", "is_deleted")]
    with engine.connect() as conn:
        for table, column in tables_columns:
            exists = conn.execute(
                text(
                    "SELECT 1 FROM information_schema.columns "
                    "WHERE table_name = :table AND column_name = :column"
                ),
                {"table": table, "column": column},
            ).first()
            if exists is None:
                conn.execute(
                    text(f"ALTER TABLE {table} ADD COLUMN {column} BOOLEAN NOT NULL DEFAULT false")
                )
                conn.commit()


def init_db() -> None:
    """Создаёт таблицы, если их ещё нет, и добавляет недостающие
    колонки к уже существующим таблицам. На старте приложения."""
    SQLModel.metadata.create_all(engine)
    _ensure_is_deleted_columns()


def get_session():
    """Дать сессию БД на время одного запроса (FastAPI Depends)."""
    with Session(engine) as session:
        yield session


def seed_constants() -> None:
    """
    Создаёт стартовый набор констант, если их ещё нет в БД —
    по одной проверке на каждый key (идемпотентно, безопасно
    вызывать при каждом старте приложения). Значение меняет
    только пользователь через UI /constant-v2 — повторный seed
    существующую запись не трогает и не перезаписывает.
    """
    # Импорт внутри функции, а не в начале файла — чтобы избежать
    # цикличного импорта (models импортирует database для типов
    # в других местах проекта не требуется, но так безопаснее).
    from app.models.constant import Constant

    defaults = [
        ("vat_rate", "20", "Ставка НДС (%), используется при пересчёте цен материалов"),
        ("default_page_size", "100", "Максимальное число строк в списках"),
    ]
    with Session(engine) as session:
        for key, value, description in defaults:
            existing = session.exec(select(Constant).where(Constant.key == key)).first()
            if existing is None:
                session.add(Constant(key=key, value=value, description=description))
        session.commit()
