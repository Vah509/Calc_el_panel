# app/engine/tables.py
# ============================================================
# Декларативные описания таблиц для универсального движка.
# Обкатка движка: материалы (с computed_pair НДС и relation на
# бренд) и бренды (простой справочник без пересчёта и без связей).
#
# Новую таблицу добавляем сюда же — одним TableConfig, без
# написания нового роутера/шаблона вручную.
# ============================================================

from app.engine.config import TableConfig, FieldConfig, ComputedPair, Relation, FormRow, Hierarchy, ActionButton
from app.models.material import Material
from app.models.brand import Brand
from app.models.constant import Constant
from app.models.kit_group import KitGroup
from app.models.kit_section import KitSection
from app.models.kit import Kit
from app.models.kit_item import KitItem
from app.models.client import Client
from app.models.request import Request
from app.models.calculation import Calculation, DEFAULT_NAME_TEMPLATE
from app.models.document_counter import DocumentCounter  # noqa: F401 — не таблица
# движка (нет своего TableConfig/страницы), но должна быть импортирована
# здесь, чтобы SQLModel.metadata.create_all() увидела её при старте
# (см. app/database.py) — единственное место, куда стягиваются импорты
# всех моделей проекта.


brand_table = TableConfig(
    key="brand",
    model=Brand,
    title="Бренды",
    title_singular="бренд",
    search_placeholder="Поиск по названию…",
    delete_mode="soft",
    fields=[
        FieldConfig(name="name", label="Название", required=True, searchable=True),
        FieldConfig(name="rate_vb", label="Курс ВБ", widget="number",
                    is_numeric=True, list_width="100px"),
    ],
)


client_table = TableConfig(
    key="client",
    model=Client,
    title="Клиенты",
    title_singular="клиент",
    search_placeholder="Поиск по названию…",
    enable_search_toggles=True,
    delete_mode="soft",
    fields=[
        FieldConfig(name="short_name", label="Короткое название", required=True,
                    searchable=True, search_default=True, list_width="22%"),
        FieldConfig(name="full_name", label="Полное название",
                    searchable=True, search_default=False, list_width="28%"),
        FieldConfig(name="egrpou_code", label="Код ЕГРПОУ", list_width="110px"),
        FieldConfig(name="phone", label="Телефон", list_width="120px"),
        FieldConfig(name="contact_person_name", label="Контактное лицо", in_list=False),
        FieldConfig(name="contact_person_phone", label="Телефон контактного лица", in_list=False),
    ],
    form_rows=[
        FormRow(field_names=["contact_person_name", "contact_person_phone"]),
    ],
)


# Заявка (request) — первый документ цепочки zayavka -> calculation ->
# specification -> invoice (docs/HANDOFF_kits_and_calculation.md, раздел 2).
# document_number/document_date — номер и дата документа, оба
# редактируются вручную; номер при создании автогенерируется по
# счётчику префикса "R" (document_prefix), если не введён явно —
# см. app/engine/document_numbering.py. Три слота бренда — три
# независимых варианта расчёта, всегда видны в форме, каждый может
# быть пустым. У каждого слота — своя пара кнопок «Спецификация»/
# «Пересчитать» рядом с выбором бренда (FieldConfig.row_actions), пока
# неактивные заглушки — реализуются вместе с calculation. Общей кнопки
# "Пересчитать всё" сознательно нет — по прямому решению Вахтанга
# (2026-08-19): пересчёт всегда по одному варианту, так проще уследить,
# что где пересчиталось.
#
# Поиск (v52, по фидбеку с реального устройства): у документа 5
# relation-полей (2 клиента + 3 бренда) — стандартный ряд чипов-фильтров
# "Все/АСКО/ABB/ETI" движка на КАЖДОЕ из них выглядел захламлённо и
# бесполезно на телефоне (5 рядов чипов над списком заявок). Все чипы
# отключены (show_filter_chips=False у каждого Relation) в пользу
# обычного текстового поиска — по короткому и полному названию клиента,
# ЧЕРЕЗ join/подзапрос на client (Relation.searchable_fields), с
# переключаемыми чекбоксами "заказчик"/"для счёта" (enable_search_toggles,
# тот же паттерн, что и у client_table для собственных текстовых полей).
request_table = TableConfig(
    key="request",
    model=Request,
    title="Заявки",
    title_singular="заявка",
    search_placeholder="Поиск по клиенту…",
    delete_mode="soft",
    enable_search_toggles=True,
    document_number_field="document_number",
    document_prefix="R",
    child_document_actions=["Создать документ на основании", "Показать подчинённые документы"],
    create_child_document_url="/calculation-v2",
    default_sort_field="document_date",
    default_sort_dir="desc",
    fields=[
        FieldConfig(name="document_number", label="Номер", list_width="90px"),
        FieldConfig(name="document_date", label="Дата", widget="date", list_width="110px"),
        FieldConfig(name="client_id", label="Клиент (заказчик)", widget="select", required=True, list_width="22%"),
        FieldConfig(name="client_invoice_id", label="Клиент (для счёта)", widget="select", list_width="22%"),
        # in_list=False у брендовых слотов (v56, по решению Вахтанга) —
        # список заявок должен быть компактным (номер/дата/оба клиента),
        # бренд варианта — деталь формы, не нужна для быстрого обзора
        # журнала. in_form не трогаем (default True) — в форме видны
        # как прежде, вместе со своими row_actions.
        FieldConfig(name="brand_slot_1_id", label="Вариант 1 — бренд", widget="select", in_list=False,
                    row_actions=["Спецификация", "Пересчитать"]),
        FieldConfig(name="brand_slot_2_id", label="Вариант 2 — бренд", widget="select", in_list=False,
                    row_actions=["Спецификация", "Пересчитать"]),
        FieldConfig(name="brand_slot_3_id", label="Вариант 3 — бренд", widget="select", in_list=False,
                    row_actions=["Спецификация", "Пересчитать"]),
        FieldConfig(name="note", label="Заметка", widget="textarea", in_list=False, placeholder="К чему относится эта заявка…"),
    ],
    relations=[
        Relation(field="client_id", target_table="client", display_field="short_name", label="Клиент (заказчик)",
                 show_filter_chips=False, searchable_fields=["short_name", "full_name"], search_default=True),
        Relation(field="client_invoice_id", target_table="client", display_field="short_name", label="Клиент (для счёта)",
                 show_filter_chips=False, searchable_fields=["short_name", "full_name"], search_default=False),
        Relation(field="brand_slot_1_id", target_table="brand", display_field="name", label="Вариант 1 — бренд",
                 show_filter_chips=False),
        Relation(field="brand_slot_2_id", target_table="brand", display_field="name", label="Вариант 2 — бренд",
                 show_filter_chips=False),
        Relation(field="brand_slot_3_id", target_table="brand", display_field="name", label="Вариант 3 — бренд",
                 show_filter_chips=False),
    ],
    form_rows=[
        FormRow(field_names=["document_number", "document_date"]),
    ],
    # Остальные поля не сгруппированы в form_rows намеренно — client_id/
    # client_invoice_id идут каждое отдельным рядом на всю ширину (клиенты
    # бывают с длинными названиями, в два столбца не помещались), брендовые
    # слоты тоже по одному в ряд, т.к. у каждого теперь своя пара кнопок
    # рядом (row_actions) — в общем ряду на троих было бы тесно.
)


def _recalc_full_name_handler(instance: Calculation, session) -> dict:
    """Серверная версия сборки full_name — НЕ используется напрямую
    кнопкой формы (см. ActionButton(client_side=True) в
    calculation_table ниже — с 2026-08-22 кнопка «Сформировать
    название» считает результат в браузере, см. CLIENT_ACTIONS.
    recalc_full_name в app/engine/page.py, чтобы работать и для ещё не
    сохранённой записи). Оставлен зарегистрированным в
    action_handlers на случай будущей серверной надобности (например
    массовый пересчёт нескольких записей сразу) — сам по себе
    достижим через POST /api/calculation/{id}/actions/recalc_full_name
    для уже сохранённой записи, просто кнопка UI туда больше не
    ходит."""
    from app.engine.name_template import build_full_name_for_calculation
    instance.full_name = build_full_name_for_calculation(session, instance)
    session.add(instance)
    session.commit()
    session.refresh(instance)
    return {"full_name": instance.full_name}


def _brand_slot_labels_handler(instance: Calculation, session) -> dict:
    """Обработчик, вызываемый ПРИ ОТКРЫТИИ формы редактирования
    (openEdit() -> runAction() в page.py), а не по клику на кнопку —
    подтягивает реальные названия трёх брендов из СВЯЗАННОЙ заявки
    (Request.brand_slot_1/2/3_id), чтобы радиокнопки "Вариант (слот
    бренда)" показывали не голые цифры 1/2/3, а название бренда
    каждого варианта (решение Вахтанга 2026-08-21: калькуляция всегда
    создаётся на основании заявки, значит данные уже доступны).
    Возвращает {"1": "...", "2": "...", "3": "..."} — только для
    слотов, где бренд в заявке реально выбран; отсутствующий ключ
    даёт статичный fallback-label из FieldConfig.options на фронте
    (см. radio_labels_field). Пустой словарь, если заявка не привязана
    (request_id пуст) или бренд ни в одном слоте не выбран."""
    from app.models.request import Request
    from app.models.brand import Brand
    labels: dict[str, str] = {}
    if instance.request_id:
        req = session.get(Request, instance.request_id)
        if req:
            for slot, brand_id in (
                (1, req.brand_slot_1_id),
                (2, req.brand_slot_2_id),
                (3, req.brand_slot_3_id),
            ):
                if brand_id:
                    brand = session.get(Brand, brand_id)
                    if brand:
                        labels[str(slot)] = brand.name
    return {"brand_slot_labels": labels}


# Калькуляция (calculation) — второй документ цепочки zayavka ->
# calculation -> specification -> invoice. Этот шаг — только "шапка"
# документа, без состава (calculation_item — следующий шаг). См.
# подробный комментарий в app/models/calculation.py.
#
# form_tabs=["Основное", "Настройки"] — первая таблица движка с
# вкладками формы (см. TableConfig.form_tabs в config.py, введено
# специально под эту потребность, но переиспользуемо для любой
# будущей таблицы). На "Настройки" — только name_template и кнопка
# "Пересчитать название" на этом шаге; сюда же позже лягут настройки
# формулы расчёта стоимости (см. HANDOFF).
#
# full_name НЕ пересчитывается автоматически при сохранении формы —
# только по кнопке (решение Вахтанга 2026-08-21: не терять руками
# поправленное название при каждом save). full_name остаётся обычным
# редактируемым текстовым полем (не readonly) — можно поправить
# результат подстановки точечно, не трогая сам шаблон.
calculation_table = TableConfig(
    key="calculation",
    model=Calculation,
    title="Калькуляции",
    title_singular="калькуляция",
    search_placeholder="Поиск по названию…",
    delete_mode="soft",
    document_number_field="document_number",
    document_prefix="K",
    default_sort_fields=[("document_date", "desc"), ("document_time", "desc")],
    form_tabs=["Основное", "Настройки"],
    needs_constants=True,
    extra_lookups=["brand"],
    action_buttons=[
        ActionButton(action="recalc_full_name", label="Сформировать название", tab="Основное",
                     client_side=True),
        # brand_slot_labels — НЕ показывается как кнопка (нет ActionButton
        # с этим action в списке выше нарочно): вызывается автоматически
        # при открытии формы (см. openEdit() в page.py), а не по клику
        # человека. Регистрация только в action_handlers ниже достаточна
        # для работы POST /api/calculation/{id}/actions/brand_slot_labels.
    ],
    action_handlers={
        "recalc_full_name": _recalc_full_name_handler,
        "brand_slot_labels": _brand_slot_labels_handler,
    },
    fields=[
        FieldConfig(name="document_number", label="Номер", list_width="90px", tab="Основное",
                    form_width="120px"),
        FieldConfig(name="document_date", label="Дата", widget="date", list_width="110px", tab="Основное",
                    form_width="140px"),
        FieldConfig(name="document_time", label="Время", widget="time", list_width="90px", tab="Основное",
                    form_width="110px"),
        FieldConfig(name="request_id", label="Заявка", widget="select", list_width="18%", tab="Основное",
                    form_width="140px", on_change_action="brand_slot_labels"),
        FieldConfig(name="client_name", label="Рабочее название", required=True, searchable=True,
                    search_default=True, list_width="22%", tab="Основное"),
        FieldConfig(name="full_name", label="Полное название", in_list=False, tab="Основное",
                    inline_action="recalc_full_name"),
        FieldConfig(name="brand_slot", label="Вариант (слот бренда)", widget="radio",
                    list_width="90px", tab="Основное",
                    radio_labels_field="brand_slot_labels", radio_labels_action="brand_slot_labels",
                    options=[("1", "Вариант 1"), ("2", "Вариант 2"), ("3", "Вариант 3")]),
        FieldConfig(name="status", label="Статус", widget="select", list_width="46px", tab="Основное",
                    in_form=False, list_as_dot=True,
                    options=[
                        ("draft", "Черновик"),
                        ("active", "Активна"),
                        ("archived_pending", "К архивации"),
                        ("delete_pending", "К удалению"),
                    ],
                    dot_colors={
                        "draft": "#9c9c94",
                        "active": "#3f7d4f",
                        "archived_pending": "#b8862f",
                        "delete_pending": "#9c3b2e",
                    }),
        FieldConfig(name="name_template", label="Шаблон полного названия", widget="textarea",
                    in_list=False, tab="Настройки", default=DEFAULT_NAME_TEMPLATE,
                    default_from_constant="calculation_name_template",
                    placeholder="Сборка {client_name}",
                    hint="Доступные вставки: {client_name} — рабочее название, "
                         "{brand_slot} — номер варианта (1/2/3), {request_number} — "
                         "номер связанной заявки. Например: Сборка {client_name}"),
    ],
    relations=[
        Relation(field="request_id", target_table="request", display_field="document_number", label="Заявка",
                 show_filter_chips=False),
    ],
    form_rows=[
        FormRow(field_names=["document_number", "document_date", "document_time"]),
    ],
)


material_table = TableConfig(
    key="material",
    model=Material,
    title="Материалы",
    title_singular="материал",
    search_placeholder="Поиск по названию или артикулу…",
    enable_search_toggles=True,
    delete_mode="soft",
    fields=[
        FieldConfig(name="short_name", label="Short name", required=True,
                    placeholder="ABB S203 C16", searchable=True, search_default=True, list_width="22%"),
        FieldConfig(name="full_name", label="Full name", required=True,
                    placeholder="Автоматический выключатель 3P C16 6kA", searchable=True, search_default=False, list_width="22%"),
        FieldConfig(name="brand_id", label="Бренд", widget="select"),
        FieldConfig(name="sku_article", label="Артикул производителя",
                    placeholder="2CDS253001R0164", searchable=True, search_default=False, list_width="110px"),
        FieldConfig(name="price_excl_vat", label="Цена без НДС", widget="number",
                    is_numeric=True, list_width="100px"),
        FieldConfig(name="price_incl_vat", label="Цена с НДС", widget="number",
                    is_numeric=True, list_width="100px"),
        FieldConfig(name="price_vb_incl_vat", label="Цена с НДС ВБ", widget="number",
                    is_numeric=True, in_list=False),
        # in_form=False: ставка НДС больше не отдельное поле формы —
        # с v34 её значение показывается прямо в лейбле "Цена с НДС"
        # (см. price-pair-label в page.py, читает constants.vat_rate
        # напрямую). Поле остаётся virtual/source_constant_key, чтобы
        # ComputedPair.rate_constant_key="vat_rate" продолжал работать
        # без изменений — оно просто больше не рендерится как input.
        FieldConfig(name="vat_rate", label="Ставка НДС", list_width="60px",
                    virtual=True, source_constant_key="vat_rate", in_form=False),
    ],
    computed_pairs=[
        ComputedPair(
            field_a="price_excl_vat",
            field_b="price_incl_vat",
            rate_field="vat_rate",
            rate_constant_key="vat_rate",
            formula="vat",
            label_a="Цена без НДС",
            label_b="Цена с НДС",
            label_rate="Ставка НДС",
        ),
    ],
    relations=[
        Relation(field="brand_id", target_table="brand", display_field="name", label="Бренд"),
    ],
    form_rows=[
        FormRow(field_names=["brand_id", "sku_article"]),
        FormRow(field_names=["price_excl_vat", "price_incl_vat", "price_vb_incl_vat"]),
    ],
)


# kit_group / kit_section — верхние два уровня дерева drill-down
# комплектов (kit_group -> kit_section -> kit). Раньше (v36/v37) это
# были обычные плоские таблицы движка с фильтром-чипом по группе —
# временный воркэраунд, теперь заменён на настоящий drill-down с
# "простым" удалением (физическое, но только если нет детей).
# kit_group_id остаётся обычным полем модели/FK — используется здесь
# как hierarchy.parent_field, отдельного relation/select в форме
# больше не нужно (группа выбирается переходом по дереву, не в форме).
kit_group_table = TableConfig(
    key="kit_group",
    model=KitGroup,
    title="Группы комплектов",
    title_singular="группа комплектов",
    search_placeholder="Поиск по названию…",
    delete_mode="simple",
    hierarchy=Hierarchy(child_key="kit_section", root_label="Группы"),
    fields=[
        FieldConfig(name="name", label="Название", required=True, searchable=True),
        FieldConfig(name="sort_order", label="Порядок", widget="number",
                    is_numeric=True, list_width="100px", default=0, in_list=False),
    ],
)


kit_section_table = TableConfig(
    key="kit_section",
    model=KitSection,
    title="Подразделы комплектов",
    title_singular="подраздел комплектов",
    search_placeholder="Поиск по названию…",
    delete_mode="simple",
    hierarchy=Hierarchy(parent_field="kit_group_id", parent_key="kit_group", child_key="kit"),
    fields=[
        FieldConfig(name="name", label="Название", required=True, searchable=True),
        FieldConfig(name="kit_group_id", label="Группа", widget="select", required=True, in_list=False, in_form=False),
        FieldConfig(name="sort_order", label="Порядок", widget="number",
                    is_numeric=True, list_width="100px", default=0, in_list=False),
    ],
)


# kit — 3-й, нижний уровень дерева drill-down (kit_group -> kit_section
# -> kit). До этого шага (v39/v39.1) был временной плоской таблицей
# старого движка — теперь подключён к дереву. hierarchy БЕЗ child_key
# (это последний уровень — заходить вглубь больше некуда, kit_items
# не отдельный уровень дерева, а СОСТАВ, показывается внутри модалки
# этого узла, см. edit_mode ниже).
#
# edit_mode="items_modal" (см. app/engine/config.py и page.py): вместо
# обычной формы редактирования (название+поля) модалка показывает
# состав комплекта (список KitItem — материал + количество) и кнопку
# "Редактировать". Клик по ней открывает MaterialPicker — отдельный
# полноэкранный экран (bottom sheet: "Отобрано" + поиск материалов),
# где человек правит черновик состава (добавляет/меняет количество/
# удаляет), а финальное сохранение полностью заменяет состав на
# сервере (PUT /api/kit/{id}/items, см. app/engine/api.py). Дубликаты
# material_id в составе допустимы. Переименование самого комплекта —
# отдельная иконка ✎ в drill-list (не через эту модалку).
kit_table = TableConfig(
    key="kit",
    model=Kit,
    title="Комплекты",
    title_singular="комплект",
    search_placeholder="Поиск по названию…",
    delete_mode="soft",
    edit_mode="items_modal",
    items_source_table_key="kit_item",
    hierarchy=Hierarchy(parent_field="kit_section_id", parent_key="kit_section"),
    fields=[
        FieldConfig(name="name", label="Название", required=True, searchable=True),
        FieldConfig(name="kit_section_id", label="Раздел", widget="select", required=True, in_list=False, in_form=False),
        FieldConfig(name="sort_order", label="Порядок", widget="number",
                    is_numeric=True, list_width="100px", default=0, in_list=False),
    ],
)


# kit_item — состав комплектов (материал + количество). НЕ отдельный
# уровень дерева (kit.hierarchy не указывает на него через child_key —
# он последний уровень) — но hierarchy здесь всё равно нужен, ЧИСТО
# ради parent_field: это даёт GET /api/kit_item?parent_id={kit_id}
# бесплатно через уже существующий универсальный механизм движка
# (см. app/engine/api.py list_items, реализовано в v38 для дерева
# групп/разделов) — используется модалкой состава (edit_mode=
# "items_modal" у kit) для загрузки строк текущего комплекта, а не
# как самостоятельная страница списка (страница /kit_item-v2 и пункт
# меню убраны в этой сессии — состав теперь виден только изнутри
# модалки конкретного комплекта).
kit_item_table = TableConfig(
    key="kit_item",
    model=KitItem,
    title="Состав комплекта",
    title_singular="позиция состава",
    search_placeholder="Поиск…",
    hierarchy=Hierarchy(parent_field="kit_id", parent_key="kit"),
    # delete_mode не указан -> дефолт "hard": на KitItem ничего не
    # ссылается (см. обоснование в app/models/kit_item.py), удаление
    # позиции состава всегда безусловное и немедленное, без пометки.
    fields=[
        FieldConfig(name="kit_id", label="Комплект", widget="select", required=True, in_list=False, in_form=False),
        FieldConfig(name="material_id", label="Материал", widget="select", required=True),
        FieldConfig(name="quantity", label="Количество", widget="number",
                    is_numeric=True, list_width="100px", default=1, form_width="110px"),
    ],
    relations=[
        Relation(field="kit_id", target_table="kit", display_field="name", label="Комплект"),
        Relation(field="material_id", target_table="material", display_field="short_name", label="Материал"),
    ],
)


constant_table = TableConfig(
    key="constant",
    model=Constant,
    title="Константы",
    title_singular="константа",
    search_placeholder="Поиск по названию…",
    # Набор ключей фиксирован и задаётся один раз seed_constants()
    # при старте (см. app/database.py) — через UI создавать/удалять
    # записи нельзя, только менять value уже существующих.
    allow_create=False,
    allow_delete=False,
    fields=[
        FieldConfig(name="key", label="Ключ", readonly=True, searchable=True, list_width="26%"),
        FieldConfig(name="value", label="Значение", list_width="18%"),
        FieldConfig(name="description", label="Описание", readonly=True, in_form=False),
    ],
)


ALL_TABLES = [
    brand_table, material_table, kit_group_table, kit_section_table,
    kit_table, kit_item_table, constant_table, client_table, request_table,
    calculation_table,
]
