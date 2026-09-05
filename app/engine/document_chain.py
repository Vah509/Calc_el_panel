# app/engine/document_chain.py
# ============================================================
# Реестр связей между типами ДОКУМЕНТОВ (не путать с
# app/engine/config.py::Hierarchy — та штука для drill-down
# СПРАВОЧНИКОВ вроде kit_group -> kit_section -> kit, где родитель
# один и тот же экран дерева; здесь же — про самостоятельные
# документы zayavka -> calculation -> specification -> invoice,
# каждый ЖИВЁТ на своей странице движка (см. tables.py), просто
# ссылается FK-полем на родителя).
#
# Декларативный список: для каждого дочернего типа документа
# указываем родителя (по ключу TableConfig.key из ALL_TABLES) и имя
# FK-поля в модели дочернего типа, указывающего на этого родителя.
#
# Собранный по реестру граф используется ОДНИМ местом —
# app/documents_chain (страница + API "Показать подчинённые
# документы"), обходит его рекурсивно вниз от заявки, поэтому
# добавление specification/invoice в будущем — это ОДНА новая
# строка в CHAIN_LINKS, без изменения кода страницы/API цепочки.
#
# root_key — корень всей цепочки документов (request). Кнопка
# "Показать цепочку" сейчас видна только у request (см.
# child_document_actions в tables.py), но сам реестр не привязан
# жёстко к request как единственно возможному корню — obход
# работает от любого узла, на случай если в будущем понадобится
# смотреть цепочку не только "сверху".
# ============================================================

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class ChainLink:
    """Один FK-переход от дочернего документа к родительскому.

    child_key: ключ дочерней таблицы в ALL_TABLES (например "calculation").
    parent_key: ключ родительской таблицы в ALL_TABLES (например "request").
    fk_field: имя поля в МОДЕЛИ дочерней таблицы, хранящего FK на
        родителя (например "request_id" у Calculation).
    """
    child_key: str
    parent_key: str
    fk_field: str


# specification — УБРАНО из реестра (2026-09-05, план "Перепроведение",
# первый проход зачистки UI/движка после сессии 6). Specification/
# SpecificationItem как модели и таблицы БД ПОКА остаются нетронутыми
# (см. HANDOFF_specification_cleanup.md — второй проход, отдельная
# сессия) — здесь убрана только видимость в цепочке документов,
# поэтому /documents-chain больше не показывает уровень "Спецификации"
# у заявки. Если понадобится восстановить это конкретное место —
# верните строку ChainLink(child_key="specification",
# parent_key="request", fk_field="request_id").
#
# invoice (2026-08-29) — родитель В ЦЕПОЧКЕ ДОКУМЕНТОВ это request
# (обоснование см. в app/models/invoice.py: request_id у Invoice
# ВСЕГДА заполнен и НИКОГДА не сбрасывается). specification_id как
# отдельная связь СОЗНАТЕЛЬНО НЕ регистрируется здесь отдельным
# ChainLink — она nullable, и для новых счетов (новая цепочка,
# минующая спецификацию) всегда NULL.
CHAIN_LINKS: list[ChainLink] = [
    ChainLink(child_key="calculation", parent_key="request", fk_field="request_id"),
    ChainLink(child_key="invoice", parent_key="request", fk_field="request_id"),
]

# Корень цепочки документов — заявка. Единственное место, откуда
# сейчас можно попасть в журнал цепочки (кнопка "Показать цепочку" у
# request, см. tables.py::child_document_actions).
ROOT_KEY = "request"


def children_of(parent_key: str) -> list[ChainLink]:
    """Все прямые дочерние связи для данного родительского ключа
    (обычно 0 или 1 — дерево документов сейчас линейное, но
    возвращаем список на случай будущего документа с несколькими
    типами детей сразу)."""
    return [link for link in CHAIN_LINKS if link.parent_key == parent_key]


def parent_of(child_key: str) -> Optional[ChainLink]:
    """Связь на родителя для данного дочернего ключа, если она
    зарегистрирована (None — у этого типа документа сейчас нет
    родителя в реестре, либо это сам корень)."""
    for link in CHAIN_LINKS:
        if link.child_key == child_key:
            return link
    return None
