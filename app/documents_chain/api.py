# app/documents_chain/api.py
# ============================================================
# GET /api/documents-chain/{request_id} — собирает "цепочку"
# документов одной заявки: саму заявку + все документы, дочерние
# по реестру app/engine/document_chain.py (сейчас — только
# calculation; specification/invoice подключатся сами, когда
# появятся в CHAIN_LINKS, без изменений в этом файле).
#
# Обход — BFS вниз от заявки по CHAIN_LINKS: для каждого уже
# найденного уровня документов ищем все связи, где он parent_key,
# и подтягиваем дочерние записи, чьё fk_field указывает на любой id
# из текущего уровня. Результат — список групп в порядке уровней
# (первая группа всегда сама заявка, единственный элемент).
#
# Ответ отдаёт СЫРЫЕ данные записей (через _serialize того же вида,
# что и engine/api.py, но по-простому — dict(instance) без relation-
# декорирования) — фронт цепочки сам решает, какие поля показать,
# опираясь на table_config каждой группы (title/fields), которые
# отдаются рядом.
# ============================================================

from fastapi import APIRouter, HTTPException
from fastapi.params import Depends
from sqlmodel import Session, select

from app.database import get_session
from app.engine.document_chain import ROOT_KEY, children_of
from app.engine.tables import ALL_TABLES

router = APIRouter(tags=["documents-chain-api"])

_TABLE_BY_KEY = {t.key: t for t in ALL_TABLES}


def _serialize_row(instance) -> dict:
    """Плоская сериализация без служебных SQLAlchemy-полей — тот же
    минимальный принцип, что и engine/api.py::_serialize, но без
    зависимости от приватной функции того модуля (нет причин
    завязываться на internals другого роутера ради одной утилиты)."""
    data = instance.model_dump()
    return data


def _group_meta(table_config) -> dict:
    """Общая часть описания группы (заголовок, relations, список
    колонок in_list) — одинаковая что для корня (заявка), что для
    любого дочернего уровня, вынесена, чтобы не дублировать словарь
    в двух местах ниже.

    create_child_document_url прокидывается как есть из TableConfig
    (у request сейчас "/calculation-v2", у остальных — None) — фронт
    цепочки использует его, чтобы показать кнопку "Создать документ
    на основании" в selection-bar, когда выделен ровно один документ
    из САМОЙ ПЕРВОЙ группы ответа (группы идут по уровням от корня,
    см. get_documents_chain ниже — первая группа это всегда root_key).
    Тот же принцип, что и кнопка в обычном журнале движка
    (engine/page.py::createChildDocument()), просто здесь источник
    URL — не текущая страница таблицы, а метаданные группы."""
    return {
        "key": table_config.key,
        "title": table_config.title,
        "title_singular": table_config.title_singular,
        "document_number_field": table_config.document_number_field,
        "delete_mode": table_config.delete_mode,
        "own_page_url": table_config.own_page_url,
        "create_child_document_url": table_config.create_child_document_url,
        "relations": [
            {"field": r.field, "target_table": r.target_table, "display_field": r.display_field}
            for r in table_config.relations
        ],
        "fields": [
            {"name": f.name, "label": f.label, "widget": f.widget}
            for f in table_config.fields
            if f.in_list
        ],
    }


@router.get("/api/documents-chain/{request_id}")
def get_documents_chain(request_id: int, session: Session = Depends(get_session)):
    root_config = _TABLE_BY_KEY.get(ROOT_KEY)
    if root_config is None:
        raise HTTPException(status_code=500, detail="Корневая таблица цепочки не зарегистрирована.")

    root_instance = session.get(root_config.model, request_id)
    if not root_instance:
        raise HTTPException(status_code=404, detail=f"{root_config.title_singular} не найдена")

    groups: list[dict] = [
        {**_group_meta(root_config), "items": [_serialize_row(root_instance)]}
    ]

    # BFS вниз по CHAIN_LINKS: текущий уровень id-шников -> следующий.
    current_level_key = root_config.key
    current_level_ids = [request_id]
    # Очередь ещё не обработанных веток BFS — нужна с тех пор, как
    # один parent_key может иметь НЕСКОЛЬКО дочерних связей сразу (см.
    # комментарий ниже) и обе ветки нужно обойти дальше вниз, а не
    # только последнюю найденную.
    pending_levels: list[tuple[str, list[int]]] = []

    while True:
        links = children_of(current_level_key)
        if not links:
            if not pending_levels:
                break
            current_level_key, current_level_ids = pending_levels.pop(0)
            continue
        # С 2026-08-27 (specification) в реестре УЖЕ ЕСТЬ несколько
        # связей на один parent_key одновременно (calculation И
        # specification — оба дети request, см.
        # app/engine/document_chain.py) — поэтому next-уровень собирается
        # ПО КАЖДОЙ дочерней таблице отдельно (не смешивая id разных
        # таблиц под одним ключом, как было бы при наивном общем
        # next_level_ids): следующая итерация BFS обходит children_of()
        # для КАЖДОЙ из них по очереди, продолжая только те ветки, где
        # реально нашлись строки.
        next_levels: list[tuple[str, list[int]]] = []
        for link in links:
            child_config = _TABLE_BY_KEY.get(link.child_key)
            if child_config is None:
                continue  # таблица объявлена в реестре, но ещё не в ALL_TABLES — пропускаем молча
            fk_column = getattr(child_config.model, link.fk_field, None)
            if fk_column is None:
                continue
            rows = session.exec(
                select(child_config.model).where(fk_column.in_(current_level_ids))
            ).all()
            groups.append({**_group_meta(child_config), "items": [_serialize_row(r) for r in rows]})
            if rows:
                next_levels.append((link.child_key, [r.id for r in rows]))

        if not next_levels:
            if not pending_levels:
                break
            current_level_key, current_level_ids = pending_levels.pop(0)
            continue
        # BFS продолжается со ВСЕХ веток сразу, не только с последней —
        # очередь (child_key, ids) обрабатывается по одной ветке за
        # проход внешнего while, остальные остаются в pending_levels.
        current_level_key, current_level_ids = next_levels[0]
        pending_levels.extend(next_levels[1:])

    return {"request_id": request_id, "groups": groups}
