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
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select, func

from app.database import get_session
from app.engine.config import TableConfig
from app.engine.formulas import apply_formula


def build_api_router(config: TableConfig, get_engine_session=get_session) -> APIRouter:
    router = APIRouter(prefix=f"/api/{config.key}", tags=[f"{config.key}-api"])
    model = config.model
    field_names = config.field_names()

    def _validate_required(data: dict[str, Any]) -> None:
        """Проверяет все обязательные поля таблицы. Если что-то не
        заполнено — кидает понятную 422-ошибку со списком меток полей,
        вместо того чтобы падать на попытке создать модель или молча
        сохранять пустые значения."""
        missing = []
        for f in config.fields:
            if not f.required:
                continue
            value = data.get(f.name)
            if value is None or (isinstance(value, str) and value.strip() == ""):
                missing.append(f.label)
        if missing:
            raise HTTPException(
                status_code=422,
                detail="Не заполнено обязательное поле: " + ", ".join(missing),
            )

    def _apply_computed_pairs(data: dict[str, Any]) -> dict[str, Any]:
        """Пересчитывает все computed_pairs таблицы на основе поля
        price_source (какое поле пользователь менял последним).
        Если ставка (rate_field) не заполнена или равна нулю —
        пересчитать нельзя (деление/умножение на 0 даёт бессмысленный
        результат) — кидаем понятную ошибку вместо тихого неверного
        расчёта."""
        changed_field = data.get("_changed_field")
        for pair in config.computed_pairs:
            rate = data.get(pair.rate_field)
            if rate is None or rate == 0:
                raise HTTPException(
                    status_code=422,
                    detail=(
                        f"Не заполнено поле «{pair.label_rate}» — без него нельзя "
                        f"пересчитать «{pair.label_a}» / «{pair.label_b}»."
                    ),
                )
            value_a = data.get(pair.field_a, 0.0)
            value_b = data.get(pair.field_b, 0.0)
            new_a, new_b = apply_formula(
                pair.formula, changed_field or pair.field_a,
                pair.field_a, pair.field_b, value_a, value_b, rate
            )
            data[pair.field_a] = new_a
            data[pair.field_b] = new_b
        return data

    def _serialize(instance) -> dict[str, Any]:
        return {name: getattr(instance, name) for name in field_names} | {"id": instance.id}

    @router.get("")
    def list_items(
        q: Optional[str] = None,
        search_fields: Optional[list[str]] = Query(default=None),
        # Если передан — ищем ТОЛЬКО по перечисленным полям (пересечённым
        # с config.searchable_fields() из соображений безопасности —
        # нельзя искать по произвольному полю модели через query-параметр).
        # Если не передан — обратная совместимость: ищем по всем
        # searchable-полям таблицы, как было раньше.
        brand_id: Optional[int] = None,  # временно явный параметр под текущий кейс материалов;
                                           # при появлении других relation-фильтров обобщим до query-строки
        session: Session = Depends(get_engine_session),
    ):
        statement = select(model)
        all_searchable = config.searchable_fields()
        if search_fields is not None:
            active_fields = [f for f in search_fields if f in all_searchable]
        else:
            active_fields = all_searchable
        if q and active_fields:
            conditions = [func.lower(getattr(model, f)).contains(q.lower()) for f in active_fields]
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
        _validate_required(data)
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
        _validate_required(data)
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
