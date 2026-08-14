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
# удаление (soft-delete ещё не внедрён на момент написания, но
# принцип уже зафиксирован в HANDOFF — когда появится is_deleted,
# этот обработчик его не должен фильтровать).
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


PROCESSORS: list[Processor] = [
    Processor(
        key="recalc_material_vat",
        table_key="material",
        label="Пересчитать НДС (price_incl_vat по текущей ставке из constants)",
        run=recalc_material_vat,
    ),
]


def get_processor(key: str) -> "Processor | None":
    for p in PROCESSORS:
        if p.key == key:
            return p
    return None
