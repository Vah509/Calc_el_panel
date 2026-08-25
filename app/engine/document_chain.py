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


# Текущее состояние цепочки: только request -> calculation реально
# существует в коде. specification/invoice ЕЩЁ НЕ реализованы —
# специально НЕ добавляем сюда строки-заглушки под несуществующие
# таблицы (ключа "specification"/"invoice" пока нет в ALL_TABLES, и
# добавление ссылки на несуществующий TableConfig только создало бы
# рассинхрон, который придётся отлавливать защитным кодом). Когда
# появится specification: добавить
#   ChainLink(child_key="specification", parent_key="calculation", fk_field="calculation_id"),
# и всё — обход в document_chain_children()/build_chain() подхватит
# новый уровень автоматически, страница/API менять не придётся.
CHAIN_LINKS: list[ChainLink] = [
    ChainLink(child_key="calculation", parent_key="request", fk_field="request_id"),
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
