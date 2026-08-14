# app/processors/registry.py
# ============================================================
# Универсальный реестр обработчиков ("Обработки" в меню).
# Идея: пользователь выбирает таблицу + одну функцию пересчёта
# из списка, жмёт "Выполнить" — обработчик прогоняет функцию по
# всем строкам таблицы и возвращает короткий отчёт (сколько
# записей обработано/изменено).
#
# Каждый Processor — простая функция (session) -> ProcessorResult,
# добавляется в PROCESSORS по мере реальной потребности (по
# аналогии с formulas.py — не заранее, только когда нужна
# конкретная функция).
#
# Первая функция: recalc_material_vat — пересчёт price_incl_vat
# для ВСЕХ материалов по текущей ставке НДС из constants.
# Пересчитываются все позиции наравне, включая помеченные на
# удаление — соблюдается принцип "нет разницы между помеченными
# и обычными позициями с точки зрения обработчиков" (см. HANDOFF).
#
# purge_soft_deleted — простой обработчик физического удаления:
# для каждой soft_delete-таблицы движка (app/engine/tables.py)
# генерируется свой Processor с ключом "purge_<table_key>" —
# без ручного перечисления вручную здесь. Пока БЕЗ проверки
# зависимостей (на что позиция ссылается) — это сознательно
# отложено на следующий шаг; сейчас просто DELETE всех строк
# с is_deleted=True в выбранной таблице.
# ============================================================

from dataclasses import dataclass
from sqlmodel import Session, select

from app.engine.formulas import apply_formula


@dataclass
class ProcessorResult:
    processed: int          # сколько записей просмотрено
    updated: int             # сколько реально изменилось (было другое значение)
    message: str              # короткое резюме для UI


@dataclass
class Processor:
    key: str                 # уникальный ключ, например "recalc_material_vat"
    table_key: str            # к какой таблице движка относится, например "material"
    label: str                 # подпись для радио-кнопки в UI
    run: "callable"             # session -> ProcessorResult


def recalc_material_vat(session: Session) -> ProcessorResult:
    """Пересчитывает price_incl_vat для всех материалов по текущей
    ставке НДС из constants (живая ссылка, см. app/engine/tables.py
    ComputedPair.rate_constant_key). price_excl_vat не трогаем —
    считаем его источником истины, price_incl_vat выводим из него."""
    # Импорты внутри функции — чтобы processors/ не тянул за собой
    # engine/models на уровне модуля без необходимости (тот же
    # паттерн, что и в engine/api.py _get_constant_value).
    from app.models.material import Material
    from app.models.constant import Constant

    rate_row = session.exec(select(Constant).where(Constant.key == "vat_rate")).first()
    if rate_row is None or not rate_row.value:
        return ProcessorResult(processed=0, updated=0, message="Ставка НДС не найдена в справочнике констант — пересчёт не выполнен.")
    rate = float(rate_row.value)
    if rate == 0:
        return ProcessorResult(processed=0, updated=0, message="Ставка НДС в справочнике констант равна 0 — пересчёт не выполнен.")

    materials = session.exec(select(Material)).all()
    processed = 0
    updated = 0
    for m in materials:
        processed += 1
        new_incl = apply_formula("vat", "price_excl_vat", "price_excl_vat", "price_incl_vat",
                                  m.price_excl_vat, m.price_incl_vat, rate)[1]
        if new_incl != m.price_incl_vat:
            m.price_incl_vat = new_incl
            session.add(m)
            updated += 1
    session.commit()
    return ProcessorResult(
        processed=processed,
        updated=updated,
        message=f"Пересчитано {processed} материалов, изменено {updated}, ставка НДС {rate}%.",
    )


def _make_purge_processor(table_key: str, model: type, title: str) -> Processor:
    """Строит простой обработчик физического удаления для одной
    soft_delete-таблицы движка. Без проверки зависимостей — просто
    удаляет все строки с is_deleted=True. Более сложную проверку
    (на что позиция ссылается перед физическим удалением) допишем
    отдельным шагом, когда появится реальная потребность."""

    def run(session: Session) -> ProcessorResult:
        rows = session.exec(select(model).where(model.is_deleted == True)).all()  # noqa: E712
        processed = len(rows)
        for row in rows:
            session.delete(row)
        session.commit()
        return ProcessorResult(
            processed=processed,
            updated=processed,
            message=f"Физически удалено {processed} записей из «{title}».",
        )

    return Processor(
        key=f"purge_{table_key}",
        table_key=table_key,
        label=f"Физически удалить помеченные ({title})",
        run=run,
    )


def _build_purge_processors() -> list[Processor]:
    # Импорт внутри функции — тот же паттерн, что и в
    # recalc_material_vat, чтобы не тянуть engine/tables на уровне
    # модуля без необходимости.
    from app.engine.tables import ALL_TABLES

    return [
        _make_purge_processor(t.key, t.model, t.title)
        for t in ALL_TABLES
        if t.soft_delete
    ]


PROCESSORS: list[Processor] = [
    Processor(
        key="recalc_material_vat",
        table_key="material",
        label="Пересчитать НДС (price_incl_vat по текущей ставке из constants)",
        run=recalc_material_vat,
    ),
    *_build_purge_processors(),
]


def get_processor(key: str) -> "Processor | None":
    for p in PROCESSORS:
        if p.key == key:
            return p
    return None
