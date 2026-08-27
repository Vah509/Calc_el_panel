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
    на Railway (Postgres) и в код добавляется новое поле модели
    (is_deleted, rate_vb, price_vb_incl_vat и т.д.), колонка в уже
    существующей таблице сама не появится, и первое же обращение
    к ней упадёт с ошибкой БД.

    Поэтому для каждой (таблица, колонка, тип) при старте проверяем
    через information_schema (Postgres) — если колонки нет, добавляем
    её сами через ALTER TABLE. Идемпотентно: если колонка уже есть
    (например при переносах между окружениями), ничего не делаем.
    DEFAULT безопасен и для существующих строк — Postgres проставит
    значение всем сразу при добавлении колонки.

    Название функции сохранено историческим (is_deleted было первым
    таким случаем) — по факту теперь покрывает любые новые колонки.

    ВАЖНО НА БУДУЩЕЕ: если поле добавляется в МОДЕЛЬ УЖЕ СУЩЕСТВУЮЩЕЙ
    НА PRODUCTION таблицы (не в новую таблицу, а в старую — как
    document_number/document_date в Request в v51, при том что Request
    как таблица появилась ещё в v49) — эту функцию НАДО обновить в ТОЙ
    ЖЕ версии, иначе на SQLite (create_all создаёт таблицу с нуля,
    ошибки не будет) всё протестируется зелёным, а на Postgres-проде
    (таблица уже есть, колонки физически нет) любой INSERT упадёт 500 —
    именно так был пропущен баг v51->v52 (см. HANDOFF.md, история
    решения). Если поле добавляется в СОВСЕМ НОВУЮ таблицу (её первый
    деплой) — этот список трогать не надо, create_all() создаст её
    сразу со всеми полями.

    Для SQLite (локальная разработка) эта миграция не нужна —
    create_all и так создаёт таблицу с нуля со всеми полями модели.
    """
    if not DATABASE_URL.startswith("postgres"):  # покрывает и postgres://, и postgresql://
        return
    from sqlalchemy import text

    tables_columns = [
        ("material", "is_deleted", "BOOLEAN NOT NULL DEFAULT false"),
        ("brand", "is_deleted", "BOOLEAN NOT NULL DEFAULT false"),
        ("brand", "rate_vb", "DOUBLE PRECISION NOT NULL DEFAULT 0"),
        ("material", "price_vb_incl_vat", "DOUBLE PRECISION NOT NULL DEFAULT 0"),
        # v51: document_number/document_date добавлены в модель Request
        # ПОСЛЕ того, как таблица request уже была создана на Postgres
        # в v49 (первый деплой request/client). create_all() не добавляет
        # колонки в уже существующую таблицу — тот же класс проблемы, что
        # и с is_deleted/rate_vb выше, просто для request. DEFAULT ''/
        # CURRENT_DATE — безопасен для уже существующих строк (созданных
        # в v49/v50 без этих полей).
        ("request", "document_number", "VARCHAR NOT NULL DEFAULT ''"),
        ("request", "document_date", "DATE NOT NULL DEFAULT CURRENT_DATE"),
        # v55: note добавлено в модель Request ПОСЛЕ того, как таблица
        # request уже существует на Postgres (та же ловушка, см. выше) —
        # DEFAULT '' безопасен для уже существующих строк.
        ("request", "note", "VARCHAR NOT NULL DEFAULT ''"),
        # v63: material.unit_id добавлено в модель ПОСЛЕ того, как таблица
        # material уже существует на Postgres (та же ловушка, см. выше).
        # NULL допустим и по умолчанию (nullable на уровне БД сознательно —
        # см. app/models/material.py) — существующие материалы получат
        # unit_id=NULL, поправить руками через UI по желанию.
        ("material", "unit_id", "INTEGER NULL"),
        # v67: kit_id добавлено в модель CalculationItem ПОСЛЕ того, как
        # таблица calculationitem уже существует на Postgres (создана в
        # v64 вместе с вкладкой "Материалы" калькуляции) — та же ловушка,
        # см. комментарии выше. NULL по умолчанию: старые позиции — это
        # материалы (kit_id не относится к ним), новые позиции комплектов
        # получат kit_id явно при создании (см. вкладка "Комплекты").
        ("calculationitem", "kit_id", "INTEGER NULL"),
        # 2026-08-26: вкладка "Стоимость" — все поля ниже добавлены в
        # модель Calculation ПОСЛЕ того, как таблица calculation уже
        # существует на Postgres (создана в v?? вместе с request_id/
        # client_name и т.д.) — та же ловушка, см. комментарии выше.
        # DEFAULT для каждого поля СОВПАДАЕТ с default= в модели Python
        # (см. app/models/calculation.py) — существующие калькуляции
        # получат те же значения, что получила бы новая запись, пока
        # человек не нажмёт "Пересчитать"/не поправит вручную.
        ("calculation", "cost_method", "VARCHAR NOT NULL DEFAULT 'markup'"),
        ("calculation", "markup_percent", "DOUBLE PRECISION NOT NULL DEFAULT 1.4"),
        ("calculation", "insurance_markup", "DOUBLE PRECISION NOT NULL DEFAULT 1.1"),
        ("calculation", "assembly_hours", "DOUBLE PRECISION NOT NULL DEFAULT 0"),
        ("calculation", "product_type_rate_id", "INTEGER NULL"),
        ("calculation", "materials_total", "DOUBLE PRECISION NOT NULL DEFAULT 0"),
        ("calculation", "kits_total", "DOUBLE PRECISION NOT NULL DEFAULT 0"),
        ("calculation", "base_total", "DOUBLE PRECISION NOT NULL DEFAULT 0"),
        ("calculation", "insured_total", "DOUBLE PRECISION NOT NULL DEFAULT 0"),
        ("calculation", "markup_total", "DOUBLE PRECISION NOT NULL DEFAULT 0"),
        ("calculation", "hours_total", "DOUBLE PRECISION NOT NULL DEFAULT 0"),
        ("calculation", "final_total", "DOUBLE PRECISION NOT NULL DEFAULT 0"),
        # 2026-08-27: quantity добавлено в модель Calculation ПОСЛЕ того,
        # как таблица calculation уже существует на Postgres — та же
        # ловушка, см. комментарии выше. DEFAULT 1 совпадает с default=
        # в модели Python (см. app/models/calculation.py) — существующие
        # калькуляции трактуются как "одно изделие", пока человек не
        # поправит вручную.
        ("calculation", "quantity", "DOUBLE PRECISION NOT NULL DEFAULT 1"),
    ]
    with engine.connect() as conn:
        for table, column, ddl_type in tables_columns:
            exists = conn.execute(
                text(
                    "SELECT 1 FROM information_schema.columns "
                    "WHERE table_name = :table AND column_name = :column"
                ),
                {"table": table, "column": column},
            ).first()
            if exists is None:
                conn.execute(
                    text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl_type}")
                )
                conn.commit()


def _drop_obsolete_columns() -> None:
    """
    Убирает колонки, которые остались в существующей Postgres-таблице
    физически, но были выведены из модели/кода в одной из прошлых
    версий (SQLModel.metadata.create_all не удаляет лишние колонки
    сам — только добавляет отсутствующие таблицы).

    Конкретный кейс (v34): material.vat_rate — колонка со времён до
    v28, когда ставка НДС хранилась в самом материале. С v28 ставка
    общая для всех и живёт только в справочнике constants (см.
    seed_constants), в модели Material поля vat_rate больше нет.
    Колонку в БД тогда не удалили — она осталась с NOT NULL, и
    любой INSERT через ORM (который про неё не знает и не передаёт
    значение) падал с NotNullViolation. Дропаем колонку явно.

    Идемпотентно: IF EXISTS — повторный вызов при следующих стартах
    ничего не делает, если колонка уже удалена.
    """
    if not DATABASE_URL.startswith("postgres"):
        return
    from sqlalchemy import text

    obsolete = [
        ("material", "vat_rate"),
    ]
    with engine.connect() as conn:
        for table, column in obsolete:
            conn.execute(text(f"ALTER TABLE {table} DROP COLUMN IF EXISTS {column}"))
            conn.commit()


def init_db() -> None:
    """Создаёт таблицы, если их ещё нет, и добавляет недостающие
    колонки к уже существующим таблицам. На старте приложения."""
    SQLModel.metadata.create_all(engine)
    _ensure_is_deleted_columns()
    _drop_obsolete_columns()


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
        ("calculation_name_template", "Сборка {client_name}", "Шаблон названия калькуляции по умолчанию"),
        # 2026-08-26, вкладка "Стоимость" калькуляции — дефолты для
        # markup_percent/insurance_markup на НОВОЙ калькуляции (см.
        # app/models/calculation.py). Значения на самой калькуляции
        # свободно редактируются вручную — эти константы влияют только
        # на то, что подставится при СОЗДАНИИ, изменение здесь не
        # затрагивает уже созданные калькуляции задним числом.
        ("markup_percent", "1.4", "Процент надбавки (способ расчёта стоимости «наценка»)"),
        ("insurance_markup", "1.1", "Страховочная наценка (применяется к обоим способам расчёта стоимости)"),
    ]
    with Session(engine) as session:
        for key, value, description in defaults:
            existing = session.exec(select(Constant).where(Constant.key == key)).first()
            if existing is None:
                session.add(Constant(key=key, value=value, description=description))
        session.commit()
