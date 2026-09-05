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
# без ручного перечисления вручную здесь.
#
# Каскад по дочерним таблицам (2026-09-05, решение Вахтанга: "если
# документ удаляется, то все записи автоматически удаляются — шапка
# документа и все подчинённые, то есть начинка тоже"): перед
# удалением строки родительской таблицы обработчик находит все
# TableConfig, у которых Hierarchy.parent_key указывает на текущую
# таблицу (например invoice_item.hierarchy.parent_key == "invoice"),
# и удаляет ИХ строки с этим parent_id первыми — рекурсивно, на
# случай многоуровневой вложенности (kit_group -> kit_section ->
# kit). Работает даже если у дочерней записи не выставлен
# is_deleted=True — она удаляется как часть родителя, а не как
# самостоятельно помеченная запись (тот же принцип "начинка следует
# за шапкой"). Дочерние строки удаляются напрямую по FK-полю
# (Hierarchy.parent_field), без проверки их собственного
# is_deleted — если родитель помечен на удаление, дочерние строки
# удаляются вне зависимости от их пометки.
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


def _delete_children_recursive(session: Session, table_key: str, parent_ids: list) -> int:
    """Рекурсивно удаляет все дочерние строки (по Hierarchy.parent_key
    в app/engine/tables.py) для заданных id родительской таблицы
    table_key. Возвращает количество физически удалённых дочерних
    строк (на всех уровнях вложенности). Идёт вглубь ДО удаления
    строк текущего уровня — сначала внуки, потом дети, тот же
    порядок, что требует FK (нельзя удалить строку, пока на неё
    ссылается ещё не удалённая дочерняя)."""
    from app.engine.tables import ALL_TABLES

    if not parent_ids:
        return 0

    deleted_count = 0
    for child_table in ALL_TABLES:
        hierarchy = getattr(child_table, "hierarchy", None)
        if hierarchy is None or hierarchy.parent_key != table_key:
            continue

        child_model = child_table.model
        parent_field = getattr(child_model, hierarchy.parent_field)
        child_rows = session.exec(
            select(child_model).where(parent_field.in_(parent_ids))
        ).all()
        child_ids = [row.id for row in child_rows]

        # Сначала внуки (если у этой дочерней таблицы тоже есть свои дети).
        deleted_count += _delete_children_recursive(session, child_table.key, child_ids)

        for row in child_rows:
            session.delete(row)
        deleted_count += len(child_rows)

    return deleted_count


def _make_purge_processor(table_key: str, model: type, title: str) -> Processor:
    """Строит обработчик физического удаления для одной
    soft_delete-таблицы движка. Удаляет все строки с
    is_deleted=True ВМЕСТЕ со всеми их дочерними записями (см.
    _delete_children_recursive) — шапка документа и вся её начинка
    удаляются как единое целое. Без проверки зависимостей ВНЕ
    дерева иерархии (например, ссылается ли что-то постороннее на
    удаляемую запись) — это сознательно отложено на следующий шаг,
    когда появится реальная потребность."""

    def run(session: Session) -> ProcessorResult:
        rows = session.exec(select(model).where(model.is_deleted == True)).all()  # noqa: E712
        processed = len(rows)
        parent_ids = [row.id for row in rows]

        children_deleted = _delete_children_recursive(session, table_key, parent_ids)
        # flush ЗДЕСЬ обязателен (2026-09-05, исправление после ошибки
        # на проде): без него SQLAlchemy решает порядок DELETE внутри
        # unit-of-work сам, по своим правилам, а НЕ по порядку наших
        # вызовов session.delete() — и может отправить в Postgres
        # DELETE FROM invoice раньше DELETE FROM invoiceitem, что
        # ловит psycopg2.errors.ForeignKeyViolation, даже если в
        # коде дети удалены первыми. Явный flush фиксирует удаление
        # детей отдельной операцией ДО того, как мы добавим в сессию
        # удаление родителей.
        session.flush()

        for row in rows:
            session.delete(row)
        session.commit()

        message = f"Физически удалено {processed} записей из «{title}»."
        if children_deleted:
            message += f" Вместе с ними удалено {children_deleted} подчинённых записей."
        return ProcessorResult(
            processed=processed,
            updated=processed + children_deleted,
            message=message,
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
        if t.delete_mode == "soft"
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
