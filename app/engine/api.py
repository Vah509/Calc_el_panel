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
    relation_field_names = {r.field for r in config.relations}
    date_field_names = {f.name for f in config.fields if f.widget == "date"}
    time_field_names = {f.name for f in config.fields if f.widget == "time"}

    def _normalize_relation_fields(data: dict[str, Any]) -> dict[str, Any]:
        """Приводит пустую строку в relation-поле (select с ссылкой на
        другую таблицу, например brand_slot_1_id) к None.

        Фронт инициализирует ЛЮБОЕ незаполненное поле новой записи как
        '' (пустая строка) — единое правило для текста и чисел (см.
        openCreate() в page.py), а для relation-полей ни один вариант
        <select> не соответствует ''. Если ничего не выбрано, реально
        нужен null (nullable FK), не пустая строка. На SQLite это
        молча "проходит" (типы не проверяются), но на Postgres (прод)
        пустая строка в integer-колонке — ошибка на уровне БД, а не
        мягкая 422 с понятным текстом. Нормализуем здесь, а не чиним
        каждую хierarchy-таблицу по отдельности — общий случай для
        любого relation-поля движка."""
        for name in relation_field_names:
            if name in data and data[name] == "":
                data[name] = None
        return data

    def _normalize_date_fields(data: dict[str, Any]) -> dict[str, Any]:
        """Приводит date-поля (widget="date") к Python date.

        Убирает пустую строку из data ПОЛНОСТЬЮ (не в None) — date-поля
        модели, как правило, НЕ Optional (например Request.document_date),
        и именно отсутствие ключа даёт сработать default_factory=date.today
        модели. Непустую строку парсит в date явно: create/update_item
        строят модель через `model(**clean_data)` в обход Pydantic-схемы
        (payload — просто dict[str, Any]), поэтому автоматической
        коэрсии строка->date, которую даёт обычная FastAPI-схема, тут
        не происходит — без явного парсинга страдает SQLite сразу (см.
        историю бага), а на Postgres тоже упало бы на INSERT."""
        from datetime import date as date_cls
        for name in date_field_names:
            if name not in data:
                continue
            value = data[name]
            if value == "":
                del data[name]
            elif isinstance(value, str):
                data[name] = date_cls.fromisoformat(value)
        return data

    def _normalize_time_fields(data: dict[str, Any]) -> dict[str, Any]:
        """То же самое, что _normalize_date_fields, но для time-полей
        (widget="time", введено для Calculation.document_time, v57) —
        тот же класс проблемы (пустая строка не парсится Python'ом в
        time напрямую, а модель не через Pydantic-схему создаётся, см.
        комментарий у _normalize_date_fields), тот же приём: пустая
        строка убирается из data целиком (даёт сработать
        default_factory модели), непустая парсится через time.fromisoformat.
        HTML <input type="time"> отдаёт "HH:MM" (без секунд) — time.
        fromisoformat принимает такую строку начиная с Python 3.11,
        подстраховываемся вручную на случай более старой версии в
        окружении."""
        from datetime import time as time_cls
        for name in time_field_names:
            if name not in data:
                continue
            value = data[name]
            if value == "":
                del data[name]
            elif isinstance(value, str):
                parts = value.split(":")
                if len(parts) == 2:
                    value = value + ":00"
                data[name] = time_cls.fromisoformat(value)
        return data

    def _apply_document_numbering(data: dict[str, Any], session: Session) -> dict[str, Any]:
        """Для таблиц с document_prefix (см. TableConfig) — генерирует
        номер документа, если он не задан явно, и подтягивает счётчик
        префикса вверх, если задан вручную номер больше текущего
        счётчика. См. app/engine/document_numbering.py для полных
        правил. Для таблиц без document_prefix (обычные справочники) —
        не делает ничего."""
        if not config.document_prefix or not config.document_number_field:
            return data
        from app.engine.document_numbering import next_document_number, bump_counter_if_ahead

        field_name = config.document_number_field
        current_value = data.get(field_name)
        if not current_value:
            data[field_name] = next_document_number(session, config.document_prefix)
        else:
            bump_counter_if_ahead(session, config.document_prefix, current_value)
        return data

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
        if config.delete_mode == "soft":
            # is_deleted не объявляется как обычный FieldConfig (это
            # служебный флаг движка, а не бизнес-поле таблицы) —
            # сериализуем отдельно, чтобы фронт мог показать точку
            # статуса и подпись кнопки без ручного объявления поля
            # в каждой soft_delete-таблице в tables.py.
            data["is_deleted"] = getattr(instance, "is_deleted", False)
        return data

    if config.document_prefix and config.document_number_field:
        @router.get("/next-document-number")
        def peek_next_document_number(session: Session = Depends(get_engine_session)):
            """Только ПОКАЗЫВАЕТ, каким будет следующий номер — НЕ трогает
            счётчик (не то же самое, что next_document_number() из
            document_numbering.py, который его продвигает). Вызывается
            фронтом при открытии формы "Новая запись" (см. openCreate()
            в page.py), чтобы номер был виден человеку сразу, а не
            появлялся только после сохранения. Реальный номер всё равно
            присваивается на save — если между просмотром и сохранением
            кто-то ещё создаст документ (или проект открыт в двух
            вкладках), тут может быть небольшое расхождение — это
            подсказка, не резервирование."""
            from app.models.document_counter import DocumentCounter
            from app.engine.document_numbering import format_document_number
            counter = session.exec(
                select(DocumentCounter).where(DocumentCounter.prefix == config.document_prefix)
            ).first()
            next_number = (counter.last_number if counter else 0) + 1
            return {"document_number": format_document_number(config.document_prefix, next_number)}

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
        parent_id: Optional[int] = None, # для hierarchy-таблиц (drill-down): фильтрует
                                           # список по родителю — через FK-поле, заданное
                                           # в config.hierarchy.parent_field. Игнорируется
                                           # молча для таблиц без hierarchy или без
                                           # parent_field (корневой уровень дерева).
        sort_by: Optional[str] = None,   # имя поля для сортировки — только из field_names()
                                           # (проверяется ниже), иначе игнорируется молча,
                                           # чтобы нельзя было сортировать по произвольному
                                           # атрибуту модели через query-параметр
        sort_dir: str = "asc",           # "asc" | "desc"; любое другое значение — как "asc"
        sort_fields: Optional[str] = None,
                                           # JSON-строка [[field, dir], ...] — сортировка по
                                           # НЕСКОЛЬКИМ полям сразу (TableConfig.
                                           # default_sort_fields, например у calculation:
                                           # document_date desc, потом document_time desc).
                                           # Применяется ТОЛЬКО если sort_by не задан (клик
                                           # по заголовку колонки — однополейный sort_by/
                                           # sort_dir — всегда имеет приоритет). Поля вне
                                           # field_names молча пропускаются, как и у sort_by.
        page: int = 1,                   # 1-based; < 1 трактуется как 1
        page_size: Optional[int] = None, # если не передан — берём default_page_size из constants;
                                           # явное значение (например 1000 для relationOptions —
                                           # выпадающих списков/фильтров, которым нужен весь
                                           # справочник целиком, а не одна страница) — приоритетно
        exact_prefix: bool = False,      # False (по умолчанию) — ищем ПОДСТРОКУ в любом месте
                                           # поля ("ромашка" находит и "Ромашка", и "Крапивная
                                           # Ромашка ООО"), True — ищем ТОЛЬКО с начала поля
                                           # ("ромашка" находит "Ромашка ООО", но не "Крапивная
                                           # Ромашка"). Одна общая галочка на всю строку поиска
                                           # движка (не отдельная на поле) — переключает режим
                                           # сразу для ВСЕХ активных полей/relation-поисков сразу,
                                           # см. FilterBar в page.py. Работает одинаково что для
                                           # обычных text-полей, что для join/подзапросов по
                                           # relation (searchable_fields) — единая точка веток
                                           # ниже, чтобы оба класса условий не разъехались.
        session: Session = Depends(get_engine_session),
    ):
        def _text_match(column, value: str):
            value = value.lower()
            return func.lower(column).startswith(value) if exact_prefix else func.lower(column).contains(value)

        statement = select(model)
        all_searchable = config.searchable_fields()
        searchable_relations = config.searchable_relations()
        relation_by_field = {f"rel:{r.field}": r for r in searchable_relations}
        if search_fields is not None:
            active_fields = [f for f in search_fields if f in all_searchable]
            active_relations = [relation_by_field[f] for f in search_fields if f in relation_by_field]
        else:
            active_fields = all_searchable
            active_relations = searchable_relations
        if q:
            conditions = [_text_match(getattr(model, f), q) for f in active_fields]
            if active_relations:
                from app.engine.tables import ALL_TABLES  # локальный импорт — см. паттерн выше в файле
                for rel in active_relations:
                    # Поиск по текстовому полю СВЯЗАННОЙ таблицы (например
                    # request.client_id -> client.short_name/full_name) —
                    # через подзапрос id-шников связанной таблицы, у
                    # которых что-то из searchable_fields содержит q.
                    # Подзапрос (не JOIN) — чтобы не размножать строки
                    # текущей таблицы, если бы у relation было несколько
                    # совпадений (тут не может, id уникален, но подзапрос
                    # также проще комбинировать с остальными OR-условиями).
                    target_config = next(
                        (t for t in ALL_TABLES if t.key == rel.target_table), None
                    )
                    if not target_config:
                        continue
                    target_model = target_config.model
                    sub_conditions = [
                        _text_match(getattr(target_model, fname), q)
                        for fname in rel.searchable_fields
                        if fname in {f.name for f in target_config.fields}
                    ]
                    if not sub_conditions:
                        continue
                    sub_combined = sub_conditions[0]
                    for c in sub_conditions[1:]:
                        sub_combined = sub_combined | c
                    matching_ids = select(target_model.id).where(sub_combined)
                    conditions.append(getattr(model, rel.field).in_(matching_ids))
            if conditions:
                combined = conditions[0]
                for c in conditions[1:]:
                    combined = combined | c
                statement = statement.where(combined)
        if brand_id is not None and "brand_id" in field_names:
            statement = statement.where(getattr(model, "brand_id") == brand_id)
        if parent_id is not None and config.hierarchy and config.hierarchy.parent_field:
            statement = statement.where(
                getattr(model, config.hierarchy.parent_field) == parent_id
            )

        if sort_by and sort_by in field_names:
            column = getattr(model, sort_by)
            field_cfg = next((f for f in config.fields if f.name == sort_by), None)
            # Текстовые поля сортируем без учёта регистра (func.lower) —
            # иначе "Яблоко" и "яблоко" расходятся по разным местам
            # списка. Числовые/date/time поля — обычный ORDER BY по
            # значению (func.lower на date/time колонке в Postgres
            # падает — не строковый тип).
            use_lower = not (field_cfg and (field_cfg.is_numeric or field_cfg.widget in ("date", "time")))
            order_col = func.lower(column) if use_lower else column
            statement = statement.order_by(order_col.desc() if sort_dir == "desc" else order_col.asc())
        elif sort_fields:
            import json as _json
            try:
                parsed = _json.loads(sort_fields)
            except (ValueError, TypeError):
                parsed = []
            for name, direction in parsed:
                if name not in field_names:
                    continue
                column = getattr(model, name)
                field_cfg = next((f for f in config.fields if f.name == name), None)
                use_lower = not (field_cfg and (field_cfg.is_numeric or field_cfg.widget in ("date", "time")))
                order_col = func.lower(column) if use_lower else column
                statement = statement.order_by(order_col.desc() if direction == "desc" else order_col.asc())

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
        data = _normalize_relation_fields(data)
        data = _normalize_date_fields(data)
        data = _normalize_time_fields(data)
        data = _apply_document_numbering(data, session)
        _validate_required(data)
        data = _apply_computed_pairs(data, session)
        data = _round_numeric_fields(data)
        clean_data = {k: v for k, v in data.items() if k in field_names}
        instance = model(**clean_data)
        session.add(instance)
        session.commit()
        session.refresh(instance)
        return _serialize(instance)

    @router.get("/{item_id}")
    def get_item(item_id: int, session: Session = Depends(get_engine_session)):
        # Одиночная запись по id — понадобилось для ?open_id= (v74,
        # см. maybeOpenById() в page.py и app/documents_chain/):
        # запись, по которой кликнули на другой странице, может не
        # попасть в уже загруженную первую страницу списка
        # (сортировка/фильтры/пагинация), поэтому нужен точечный
        # запрос, а не поиск среди уже загруженных this.items.
        instance = session.get(model, item_id)
        if not instance:
            raise HTTPException(status_code=404, detail=f"{config.title_singular} не найдена")
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
        data = _normalize_relation_fields(data)
        data = _normalize_date_fields(data)
        data = _normalize_time_fields(data)
        data = _apply_document_numbering(data, session)
        _validate_required(data)
        data = _apply_computed_pairs(data, session)
        data = _round_numeric_fields(data)

        for name in field_names:
            if name in data:
                setattr(instance, name, data[name])

        if config.before_update_hook:
            config.before_update_hook(instance, session)

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

        if config.delete_mode == "soft":
            # Переключатель, не безусловная установка: повторный вызов
            # на уже помеченной записи снимает пометку ("Удалить"/
            # "Отменить" — одна и та же кнопка, см. engine/page.py).
            # Запись НЕ удаляется физически — только флаг is_deleted.
            instance.is_deleted = not instance.is_deleted
            session.add(instance)
            session.commit()
            return {"deleted": False, "is_deleted": instance.is_deleted, "id": item_id}

        if config.delete_mode == "simple":
            # Узел дерева (kit_group/kit_section и т.п.): физическое
            # удаление разрешено только если нет дочерних записей —
            # синхронная проверка count(), без processor. child_key
            # берётся из hierarchy этой же таблицы (kit_group.hierarchy.
            # child_key == "kit_section") — ищем дочернюю TableConfig
            # в ALL_TABLES по этому ключу, чтобы узнать её модель и
            # имя FK-поля, которым она ссылается на текущую запись.
            if config.hierarchy and config.hierarchy.child_key:
                from app.engine.tables import ALL_TABLES  # локальный импорт — см. паттерн выше в файле
                child_config = next(
                    (t for t in ALL_TABLES if t.key == config.hierarchy.child_key), None
                )
                if child_config and child_config.hierarchy and child_config.hierarchy.parent_field:
                    children_count = session.exec(
                        select(func.count()).select_from(child_config.model).where(
                            getattr(child_config.model, child_config.hierarchy.parent_field) == item_id
                        )
                    ).one()
                    if children_count > 0:
                        instance_name = getattr(instance, "name", None) or f"#{item_id}"
                        raise HTTPException(
                            status_code=422,
                            detail=(
                                f"Нельзя удалить «{instance_name}» — внутри есть "
                                f"{children_count} записей «{child_config.title}». "
                                f"Сначала удалите или перенесите их."
                            ),
                        )
            session.delete(instance)
            session.commit()
            return {"deleted": True, "id": item_id}

        # "hard" — прежнее поведение без soft_delete=True: удаляем
        # безусловно, сразу.
        session.delete(instance)
        session.commit()
        return {"deleted": True, "id": item_id}

    @router.post("/{item_id}/copy")
    def copy_item(item_id: int, session: Session = Depends(get_engine_session)):
        """Копирует запись со всем её составом (items_source_table_key)
        одной транзакцией — используется kit ("Копировать" в панели
        выделения drill-list). Только для таблиц с edit_mode=
        "items_modal": у них состав — не строка в самой записи, а
        отдельная дочерняя таблица (kit_item), которую нужно
        продублировать построчно вместе с родителем, иначе копия
        комплекта была бы пустой.
        Название и остальные поля копируются как есть (без "(копия)"
        и т.п.) — по прямому решению: пользователь сам переименует
        новую запись как обычную, сразу открыв её после копирования."""
        if config.edit_mode != "items_modal" or not config.items_source_table_key:
            raise HTTPException(
                status_code=422,
                detail=f"«{config.title}» не поддерживает копирование состава.",
            )
        instance = session.get(model, item_id)
        if not instance:
            raise HTTPException(status_code=404, detail=f"{config.title_singular} не найден(а)")

        from app.engine.tables import ALL_TABLES  # локальный импорт — см. паттерн выше в файле
        items_config = next((t for t in ALL_TABLES if t.key == config.items_source_table_key), None)
        if not items_config or not items_config.hierarchy or not items_config.hierarchy.parent_field:
            raise HTTPException(
                status_code=422,
                detail=f"Некорректная конфигурация состава для «{config.title}».",
            )

        # Копия родителя: все поля модели, кроме id, как есть.
        # is_deleted всегда сбрасывается в false — та же логика, что и
        # у обычного копирования строки в плоских таблицах (copySelected
        # на фронте): копия создаётся активной, даже если оригинал был
        # помечен на удаление.
        new_data = {name: getattr(instance, name) for name in field_names}
        new_instance = model(**new_data)
        if config.delete_mode == "soft":
            new_instance.is_deleted = False
        session.add(new_instance)
        session.flush()  # получаем new_instance.id ДО коммита, чтобы проставить его дочерним строкам

        items_field_names = items_config.field_names()
        items_parent_field = items_config.hierarchy.parent_field
        source_items = session.exec(
            select(items_config.model).where(
                getattr(items_config.model, items_parent_field) == item_id
            )
        ).all()
        for src_item in source_items:
            item_data = {name: getattr(src_item, name) for name in items_field_names if name != items_parent_field}
            item_data[items_parent_field] = new_instance.id
            session.add(items_config.model(**item_data))

        session.commit()
        session.refresh(new_instance)
        return _serialize(new_instance)

    @router.post("/{item_id}/actions/{action}")
    def run_action(item_id: int, action: str, session: Session = Depends(get_engine_session)):
        """Именованное действие с реальной логикой в теле формы (см.
        TableConfig.action_buttons/action_handlers в config.py и
        runAction() в engine/page.py) — например "Пересчитать название"
        у calculation. В отличие от extra_actions (просто disabled-
        заглушки без обработчика), здесь есть конкретная функция,
        зарегистрированная таблицей в action_handlers. Обработчик сам
        решает, что сохранять в БД; этот роут только диспетчеризует
        вызов и возвращает результат фронту для подмешивания в editing."""
        handler = config.action_handlers.get(action)
        if not handler:
            raise HTTPException(
                status_code=422,
                detail=f"«{config.title}» не поддерживает действие «{action}».",
            )
        instance = session.get(model, item_id)
        if not instance:
            raise HTTPException(status_code=404, detail=f"{config.title_singular} не найден(а)")
        return handler(instance, session)

    @router.put("/{item_id}/items")
    def replace_items(item_id: int, payload: dict[str, Any], session: Session = Depends(get_engine_session)):
        """Полная замена состава одной транзакцией — используется
        MaterialPicker (кнопка "Редактировать" в модалке kit, кнопка
        "Добавить" на вкладке "Материалы" calculation): человек правит
        черновик состава на отдельном полноэкранном шаге, а по
        финальному сохранению весь прежний состав удаляется и создаётся
        заново из присланного списка.

        Осознанно НЕ delta-сравнение ("что изменилось") — по прямому
        решению Вахтанга можно "смело переписывать всё", это заметно
        проще и на бэкенде, и на фронте (черновик просто отправляется
        целиком, не нужно отслеживать added/removed/changed построчно).

        payload = {"items": [{"material_id": 1, "quantity": 2.5}, ...]}
        Дубликаты material_id в списке допустимы и сохраняются как
        отдельные строки — намеренно, по прямому решению (см.
        HANDOFF_kits_and_calculation.md, раздел 2.9).

        Работает для ДВУХ разных механизмов состава:
        1. edit_mode="items_modal" (kit) — items_source_table_key,
           состав без цены (material_id + quantity).
        2. materials_item_table_key (calculation, 2026-08-23) — та же
           механика полной замены, НО каждая созданная строка
           дополнительно получает price_excl_vat = ТЕКУЩАЯ цена из
           справочника material.price_excl_vat на момент сохранения
           (решение Вахтанга: "цена берётся из material.price_excl_vat
           в момент каждого сохранения состава" — снэпшот сознательно
           обновляется при каждом "Сохранить состав", не только у новых
           строк, а у ВСЕХ, включая те что были и раньше: они всё равно
           удаляются и создаются заново, так что "старой" цены после
           replace физически не существует)."""
        items_source_key = config.items_source_table_key or config.materials_item_table_key
        if config.edit_mode != "items_modal" and not config.materials_item_table_key:
            raise HTTPException(
                status_code=422,
                detail=f"«{config.title}» не поддерживает замену состава.",
            )
        instance = session.get(model, item_id)
        if not instance:
            raise HTTPException(status_code=404, detail=f"{config.title_singular} не найден(а)")

        from app.engine.tables import ALL_TABLES  # локальный импорт — см. паттерн выше в файле
        items_config = next((t for t in ALL_TABLES if t.key == items_source_key), None)
        if not items_config or not items_config.hierarchy or not items_config.hierarchy.parent_field:
            raise HTTPException(
                status_code=422,
                detail=f"Некорректная конфигурация состава для «{config.title}».",
            )

        items_parent_field = items_config.hierarchy.parent_field
        new_items = payload.get("items") or []
        # Есть ли у дочерней модели поле цены-снэпшота — определяет,
        # нужно ли при создании строки проставлять price_excl_vat
        # (calculation_item) или нет (kit_item, у которого такого поля
        # просто не существует в модели).
        has_price_snapshot = "price_excl_vat" in items_config.field_names()

        # Валидация каждой строки: material_id обязателен и должен
        # существовать, quantity — положительное число. Проверяем ДО
        # удаления старого состава, чтобы при ошибке ничего не потерять
        # (вся функция — одна транзакция, но лучше не начинать удаление,
        # если черновик заведомо некорректен).
        from app.models.material import Material
        materials_by_id: dict[int, Material] = {}
        for row in new_items:
            material_id = row.get("material_id")
            if not material_id:
                raise HTTPException(status_code=422, detail="Не указан материал в одной из строк состава.")
            material = session.get(Material, material_id)
            if not material:
                raise HTTPException(status_code=422, detail=f"Материал id={material_id} не найден.")
            materials_by_id[material_id] = material
            quantity = row.get("quantity")
            if quantity is None or float(quantity) <= 0:
                raise HTTPException(status_code=422, detail="Количество должно быть больше нуля.")

        old_items = session.exec(
            select(items_config.model).where(
                getattr(items_config.model, items_parent_field) == item_id
            )
        ).all()
        for old in old_items:
            session.delete(old)

        for row in new_items:
            extra_fields: dict[str, Any] = {}
            if has_price_snapshot:
                extra_fields["price_excl_vat"] = materials_by_id[row["material_id"]].price_excl_vat
            session.add(items_config.model(
                **{items_parent_field: item_id},
                material_id=row["material_id"],
                quantity=round(float(row["quantity"]), 2),
                **extra_fields,
            ))

        session.commit()
        return {"replaced": len(new_items)}

    @router.put("/{item_id}/kit-items-replace")
    def replace_kit_items(item_id: int, payload: dict[str, Any], session: Session = Depends(get_engine_session)):
        """Полная замена состава ОТОБРАННЫХ КОМПЛЕКТОВ калькуляции одной
        транзакцией (2026-08-23, вкладка "Комплекты" — по прямой просьбе
        Вахтанга "экран подбора комплектов, а сохранение — как у
        материалов"). Параллельна replace_items() выше (тот же паттерн
        "черновик в памяти picker'а -> при 'Сохранить состав' старые
        строки удаляются, новые создаются заново"), но НЕ переиспользует
        replace_items() напрямую — там строки идентифицируются
        material_id и цена берётся из справочника material напрямую,
        здесь строки идентифицируются kit_id и цена — это СУММА СОСТАВА
        комплекта (Σ KitItem.quantity × Material.price_excl_vat по живому
        составу kit_item), у Kit нет собственного ценового поля (см.
        app/models/kit.py). Отдельный маленький эндпоинт вместо ветвления
        внутри replace_items() — читаемее, чем один метод, обрабатывающий
        два принципиально разных источника цены по флагу.

        payload = {"items": [{"kit_id": 1, "quantity": 2}, ...]}
        Дубликаты kit_id в списке допустимы и сохраняются как отдельные
        строки — та же логика, что и у replace_items() для material_id.

        ВАЖНО: заменяет ТОЛЬКО строки с kit_id IS NOT NULL — строки-
        материалы (material_id) той же калькуляции не трогает, они живут
        на отдельной вкладке "Материалы" со своей заменой через
        replace_items()."""
        if not config.kits_item_table_key:
            raise HTTPException(
                status_code=422,
                detail=f"«{config.title}» не поддерживает замену состава комплектов.",
            )
        instance = session.get(model, item_id)
        if not instance:
            raise HTTPException(status_code=404, detail=f"{config.title_singular} не найден(а)")

        from app.engine.tables import ALL_TABLES  # локальный импорт — см. паттерн выше в файле
        items_config = next((t for t in ALL_TABLES if t.key == config.kits_item_table_key), None)
        if not items_config or not items_config.hierarchy or not items_config.hierarchy.parent_field:
            raise HTTPException(
                status_code=422,
                detail=f"Некорректная конфигурация состава комплектов для «{config.title}».",
            )
        items_parent_field = items_config.hierarchy.parent_field

        new_items = payload.get("items") or []
        from app.models.kit import Kit
        from app.models.material import Material
        from app.models.kit_item import KitItem

        # Валидация ДО удаления старого состава — та же осторожность,
        # что и в replace_items(): если черновик некорректен, ничего не
        # трогаем.
        kits_by_id: dict[int, Kit] = {}
        for row in new_items:
            kit_id = row.get("kit_id")
            if not kit_id:
                raise HTTPException(status_code=422, detail="Не указан комплект в одной из строк состава.")
            kit = session.get(Kit, kit_id)
            if not kit:
                raise HTTPException(status_code=422, detail=f"Комплект id={kit_id} не найден.")
            kits_by_id[kit_id] = kit
            quantity = row.get("quantity")
            if quantity is None or float(quantity) <= 0:
                raise HTTPException(status_code=422, detail="Количество должно быть больше нуля.")

        # Старые строки-КОМПЛЕКТЫ этой калькуляции удаляются целиком
        # (kit_id IS NOT NULL) — строки-материалы (material_id) НЕ
        # трогаем, у них отдельная замена через replace_items().
        old_kit_items = session.exec(
            select(items_config.model).where(
                getattr(items_config.model, items_parent_field) == item_id,
                items_config.model.kit_id.is_not(None),
            )
        ).all()
        for old in old_kit_items:
            session.delete(old)

        # Кэш сумм состава по kit_id — если один и тот же комплект выбран
        # несколько раз (дубликаты разрешены), считаем его состав один
        # раз, не на каждую строку заново.
        kit_sum_cache: dict[int, float] = {}

        def kit_composition_sum(kit_id: int) -> float:
            if kit_id in kit_sum_cache:
                return kit_sum_cache[kit_id]
            kit_items = session.exec(select(KitItem).where(KitItem.kit_id == kit_id)).all()
            total = 0.0
            for kit_item in kit_items:
                material = session.get(Material, kit_item.material_id)
                if not material:
                    continue
                total += material.price_excl_vat * kit_item.quantity
            kit_sum_cache[kit_id] = total
            return total

        for row in new_items:
            kit_id = row["kit_id"]
            session.add(items_config.model(
                **{items_parent_field: item_id},
                kit_id=kit_id,
                quantity=round(float(row["quantity"]), 2),
                price_excl_vat=round(kit_composition_sum(kit_id), 2),
            ))

        session.commit()
        return {"replaced": len(new_items)}

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
        if config.delete_mode != "soft":
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
