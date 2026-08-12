# app/engine/api.py
# ============================================================
# Фабрика JSON API роутера по TableConfig. Один вызов
# build_api_router(config) заменяет собой то, что раньше
# писалось руками в materials_api.py / brands_api.py.
#
# Генерирует:
#   GET    /api/{key}            — список (с поиском ?q=, фильтром
#                                    по любому relation-полю)
#   POST   /api/{key}            — создать
#   PUT    /api/{key}/{id}       — обновить
#   DELETE /api/{key}/{id}       — удалить
#
# Пересчёт computed_pairs выполняется на бэкенде при create/update —
# это финальный источник истины (фронт пересчитывает на лету для
# отзывчивости UI, но сервер всегда пересчитывает независимо и
# именно его результат сохраняется).
# ============================================================

from typing import Any, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select, func

from app.database import get_session
from app.engine.config import TableConfig
from app.engine.formulas import apply_formula


def build_api_router(config: TableConfig, get_engine_session=get_session) -> APIRouter:
    router = APIRouter(prefix=f"/api/{config.key}", tags=[f"{config.key}-api"])
    model = config.model
    field_names = config.field_names()

    def _apply_computed_pairs(data: dict[str, Any]) -> dict[str, Any]:
        """Пересчитывает все computed_pairs таблицы на основе поля
        price_source (какое поле пользователь менял последним)."""
        changed_field = data.get("_changed_field")
        for pair in config.computed_pairs:
            value_a = data.get(pair.field_a, 0.0)
            value_b = data.get(pair.field_b, 0.0)
            rate = data.get(pair.rate_field, 0.0)
            new_a, new_b = apply_formula(
                pair.formula, changed_field or pair.field_a,
                pair.field_a, pair.field_b, value_a, value_b, rate
            )
            data[pair.field_a] = new_a
            data[pair.field_b] = new_b
        return data

    def _serialize(instance) -> dict[str, Any]:
        return {name: getattr(instance, name) for name in field_names} | {"id": instance.id}

    relation_fields = [r.field for r in config.relations]

    @router.get("")
    def list_items(
        q: Optional[str] = None,
        brand_id: Optional[int] = None,  # временно явный параметр под текущий кейс материалов;
                                           # при появлении других relation-фильтров обобщим до query-строки
        session: Session = Depends(get_engine_session),
    ):
        statement = select(model)
        searchable = config.searchable_fields()
        if q and searchable:
            conditions = [func.lower(getattr(model, f)).contains(q.lower()) for f in searchable]
            combined = conditions[0]
            for c in conditions[1:]:
                combined = combined | c
            statement = statement.where(combined)
        if brand_id is not None and "brand_id" in field_names:
            statement = statement.where(getattr(model, "brand_id") == brand_id)
        items = session.exec(statement).all()
        return [_serialize(i) for i in items]

    @router.post("")
    def create_item(payload: dict[str, Any], session: Session = Depends(get_engine_session)):
        data = {k: v for k, v in payload.items() if k in field_names or k == "_changed_field"}
        data = _apply_computed_pairs(data)
        clean_data = {k: v for k, v in data.items() if k in field_names}
        instance = model(**clean_data)
        session.add(instance)
        session.commit()
        session.refresh(instance)
        return _serialize(instance)

    @router.put("/{item_id}")
    def update_item(item_id: int, payload: dict[str, Any], session: Session = Depends(get_engine_session)):
        instance = session.get(model, item_id)
        if not instance:
            raise HTTPException(status_code=404, detail=f"{config.title_singular} не найден(а)")

        data = {k: v for k, v in payload.items() if k in field_names or k == "_changed_field"}
        data = _apply_computed_pairs(data)

        for name in field_names:
            if name in data:
                setattr(instance, name, data[name])

        session.add(instance)
        session.commit()
        session.refresh(instance)
        return _serialize(instance)

    @router.delete("/{item_id}")
    def delete_item(item_id: int, session: Session = Depends(get_engine_session)):
        instance = session.get(model, item_id)
        if not instance:
            raise HTTPException(status_code=404, detail=f"{config.title_singular} не найден(а)")
        session.delete(instance)
        session.commit()
        return {"deleted": True, "id": item_id}

    return router
