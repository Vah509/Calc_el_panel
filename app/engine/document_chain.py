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


# specification (2026-08-27) — родитель В ЦЕПОЧКЕ ДОКУМЕНТОВ это
# request, НЕ calculation, хотя по смыслу спецификация формируется
# ИЗ калькуляций — одна спецификация агрегирует НЕСКОЛЬКО калькуляций
# сразу (все активные калькуляции заявки с данным brand_slot), а
# ChainLink моделирует связь 1:N через один FK, что не подходит для
# N:1 "калькуляции -> спецификация". Вместо этого specification и
# calculation — ДВА СОСЕДНИХ дочерних уровня request одновременно
# (обе ссылки ниже имеют parent_key="request") — обход в
# document_chain_children()/build_chain() группирует их в один общий
# "уровень" BFS, что и нужно: в цепочке заявки видно калькуляции И
# спецификации рядом, каждая ссылается на свою заявку напрямую.
# Трассировка конкретных калькуляций внутри спецификации — через
# specification_item.calculation_id (см. app/models/specification.py),
# не через этот реестр документов.
#
# invoice (2026-08-29) реализован — см. ChainLink ниже.
# invoice (2026-08-29) — родитель В ЦЕПОЧКЕ ДОКУМЕНТОВ это request
# (тот же принцип, что и у specification выше, обоснование см. в
# app/models/invoice.py: request_id у Invoice ВСЕГДА заполнен и
# НИКОГДА не сбрасывается, даже когда specification_id отвязан
# кнопкой «Отвязать» — значит invoice должен продолжать быть виден
# в цепочке заявки независимо от текущего состояния привязки к
# спецификации). specification_id как отдельная связь СОЗНАТЕЛЬНО
# НЕ регистрируется здесь отдельным ChainLink — она nullable и
# может быть сброшена человеком, а обход цепочки документов должен
# оставаться стабильным независимо от этого практического решения
# (то же рассуждение, что у specification -> calculation:
# трассировка через конкретное поле модели, не через реестр
# документов).
CHAIN_LINKS: list[ChainLink] = [
    ChainLink(child_key="calculation", parent_key="request", fk_field="request_id"),
    ChainLink(child_key="specification", parent_key="request", fk_field="request_id"),
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
