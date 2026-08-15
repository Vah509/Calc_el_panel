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


def _get_constant_value(session: Session, key: str) -> Optional[str]:
    """Читает value константы по ключу из справочника constants.
    Импорт Constant внутри функции — чтобы избежать циклического
    импорта на уровне модуля (engine/api.py используется и для
    самой таблицы constant тоже)."""
    from app.models.constant import Constant
    row = session.exec(select(Constant).where(Constant.key == key)).first()
    return row.value if row else None


def build_api_router(config: TableConfig, get_engine_session=get_session) -> APIRouter:
    router = APIRouter(prefix=f"/api/{config.key}", tags=[f"{config.key}-api"])
    model = config.model
    field_names = config.field_names()
    readonly_field_names = {f.name for f in config.fields if f.readonly}

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

    numeric_field_names = {f.name for f in config.fields if f.is_numeric}

    def _round_numeric_fields(data: dict[str, Any]) -> dict[str, Any]:
        """Округляет все числовые (is_numeric) поля до 2 знаков после
        запятой перед сохранением — это денежные суммы (цены), для
        которых 2 знака (копейки) технически достаточно и избавляет
        от плавающих "хвостов" (26.399999999) при повторных пересчётах.
        computed_pairs уже округляют field_a/field_b сами (см. formulas.py),
        но остальные numeric-поля (например price_vb_incl_vat, которое
        не входит ни в один computed_pair) без этого не округлялись бы."""
        for name in numeric_field_names:
            if name in data and data[name] is not None:
                data[name] = round(float(data[name]), 2)
        return data

    def _apply_computed_pairs(data: dict[str, Any], session: Session) -> dict[str, Any]:
        """Пересчитывает все computed_pairs таблицы на основе поля
        price_source (какое поле пользователь менял последним).
        Ставка берётся из rate_field записи ИЛИ, если у пары задан
        rate_constant_key, из справочника constants (живая ссылка —
        общая для всех записей, не хранится в самой записи).
        Если ставка не найдена или равна нулю — пересчитать нельзя
        (деление/умножение на 0 даёт бессмысленный результат) —
        кидаем понятную ошибку вместо тихого неверного расчёта."""
        changed_field = data.get("_changed_field")
        for pair in config.computed_pairs:
            if pair.rate_constant_key:
                raw_rate = _get_constant_value(session, pair.rate_constant_key)
                rate = float(raw_rate) if raw_rate is not None else None
            else:
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
        data = {name: getattr(instance, name) for name in field_names} | {"id": instance.id}
        if config.soft_delete:
            # is_deleted не объявляется как обычный FieldConfig (это
            # служебный флаг движка, а не бизнес-поле таблицы) —
            # сериализуем отдельно, чтобы фронт мог показать точку
            # статуса и подпись кнопки без ручного объявления поля
            # в каждой soft_delete-таблице в tables.py.
            data["is_deleted"] = getattr(instance, "is_deleted", False)
        return data

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
        sort_by: Optional[str] = None,   # имя поля для сортировки — только из field_names()
                                           # (проверяется ниже), иначе игнорируется молча,
                                           # чтобы нельзя было сортировать по произвольному
                                           # атрибуту модели через query-параметр
        sort_dir: str = "asc",           # "asc" | "desc"; любое другое значение — как "asc"
        page: int = 1,                   # 1-based; < 1 трактуется как 1
        page_size: Optional[int] = None, # если не передан — берём default_page_size из constants;
                                           # явное значение (например 1000 для relationOptions —
                                           # выпадающих списков/фильтров, которым нужен весь
                                           # справочник целиком, а не одна страница) — приоритетно
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

        if sort_by and sort_by in field_names:
            column = getattr(model, sort_by)
            field_cfg = next((f for f in config.fields if f.name == sort_by), None)
            # Текстовые поля сортируем без учёта регистра (func.lower) —
            # иначе "Яблоко" и "яблоко" расходятся по разным местам
            # списка. Числовые поля — обычный ORDER BY по значению.
            order_col = column if (field_cfg and field_cfg.is_numeric) else func.lower(column)
            statement = statement.order_by(order_col.desc() if sort_dir == "desc" else order_col.asc())

        # total считается ДО применения LIMIT/OFFSET — по тому же
        # statement (с учётом поиска/фильтра), иначе "Стр. X из Y"
        # будет врать при активном поиске.
        total = len(session.exec(statement).all())

        effective_page_size = page_size
        if effective_page_size is None:
            raw = _get_constant_value(session, "default_page_size")
            try:
                effective_page_size = int(raw) if raw else 100
            except ValueError:
                effective_page_size = 100
        effective_page_size = max(1, effective_page_size)

        effective_page = max(1, page)
        total_pages = max(1, (total + effective_page_size - 1) // effective_page_size)
        effective_page = min(effective_page, total_pages)

        offset = (effective_page - 1) * effective_page_size
        statement = statement.offset(offset).limit(effective_page_size)

        items = session.exec(statement).all()
        return {
            "items": [_serialize(i) for i in items],
            "total": total,
            "page": effective_page,
            "page_size": effective_page_size,
            "total_pages": total_pages,
        }

    @router.post("")
    def create_item(payload: dict[str, Any], session: Session = Depends(get_engine_session)):
        if not config.allow_create:
            raise HTTPException(
                status_code=422,
                detail=f"Создание новых записей в «{config.title}» через интерфейс отключено.",
            )
        data = {k: v for k, v in payload.items() if k in field_names or k == "_changed_field"}
        _validate_required(data)
        data = _apply_computed_pairs(data, session)
        data = _round_numeric_fields(data)
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

        data = {
            k: v for k, v in payload.items()
            if (k in field_names and k not in readonly_field_names) or k == "_changed_field"
        }
        _validate_required(data)
        data = _apply_computed_pairs(data, session)
        data = _round_numeric_fields(data)

        for name in field_names:
            if name in data:
                setattr(instance, name, data[name])

        session.add(instance)
        session.commit()
        session.refresh(instance)
        return _serialize(instance)

    @router.delete("/{item_id}")
    def delete_item(item_id: int, session: Session = Depends(get_engine_session)):
        if not config.allow_delete:
            raise HTTPException(
                status_code=422,
                detail=f"Удаление записей в «{config.title}» через интерфейс отключено.",
            )
        instance = session.get(model, item_id)
        if not instance:
            raise HTTPException(status_code=404, detail=f"{config.title_singular} не найден(а)")

        if config.soft_delete:
            # Переключатель, не безусловная установка: повторный вызов
            # на уже помеченной записи снимает пометку ("Удалить"/
            # "Отменить" — одна и та же кнопка, см. engine/page.py).
            # Запись НЕ удаляется физически — только флаг is_deleted.
            instance.is_deleted = not instance.is_deleted
            session.add(instance)
            session.commit()
            return {"deleted": False, "is_deleted": instance.is_deleted, "id": item_id}

        session.delete(instance)
        session.commit()
        return {"deleted": True, "id": item_id}

    @router.post("/bulk-mark-delete")
    def bulk_mark_delete(payload: dict[str, Any], session: Session = Depends(get_engine_session)):
        """Групповая пометка/снятие пометки на удаление. В отличие
        от одиночного DELETE (переключатель, toggle), здесь статус
        задаётся БЕЗУСЛОВНО значением payload["value"] для каждой
        записи из payload["ids"] — так группа ведёт себя предсказуемо:
        если среди выделенных уже есть помеченная позиция, при
        "Пометить на удаление" она остаётся помеченной (просто
        перезаписывается тем же значением), а не переключается
        обратно. То же для "Снять пометку"."""
        if not config.soft_delete:
            raise HTTPException(
                status_code=422,
                detail=f"«{config.title}» не поддерживает пометку на удаление.",
            )
        ids = payload.get("ids") or []
        value = bool(payload.get("value"))
        if not ids:
            raise HTTPException(status_code=422, detail="Не выбрано ни одной записи.")

        instances = session.exec(select(model).where(model.id.in_(ids))).all()
        for instance in instances:
            instance.is_deleted = value
            session.add(instance)
        session.commit()
        return {"updated": len(instances), "is_deleted": value}

    return router
