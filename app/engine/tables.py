# app/engine/tables.py
# ============================================================
# Декларативные описания таблиц для универсального движка.
# Обкатка движка: материалы (с computed_pair НДС и relation на
# бренд) и бренды (простой справочник без пересчёта и без связей).
#
# Новую таблицу добавляем сюда же — одним TableConfig, без
# написания нового роутера/шаблона вручную.
# ============================================================

from app.engine.config import TableConfig, FieldConfig, ComputedPair, Relation, FormRow, Hierarchy
from app.models.material import Material
from app.models.brand import Brand
from app.models.constant import Constant
from app.models.kit_group import KitGroup
from app.models.kit_section import KitSection
from app.models.kit import Kit
from app.models.kit_item import KitItem
from app.models.client import Client
from app.models.request import Request
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
request_table = TableConfig(
    key="request",
    model=Request,
    title="Заявки",
    title_singular="заявка",
    search_placeholder="Поиск по клиенту…",
    delete_mode="soft",
    document_number_field="document_number",
    document_prefix="R",
    fields=[
        FieldConfig(name="document_number", label="Номер", list_width="90px"),
        FieldConfig(name="document_date", label="Дата", widget="date", list_width="110px"),
        FieldConfig(name="client_id", label="Клиент (заказчик)", widget="select", required=True),
        FieldConfig(name="client_invoice_id", label="Клиент (для счёта)", widget="select"),
        FieldConfig(name="brand_slot_1_id", label="Вариант 1 — бренд", widget="select",
                    row_actions=["Спецификация", "Пересчитать"]),
        FieldConfig(name="brand_slot_2_id", label="Вариант 2 — бренд", widget="select",
                    row_actions=["Спецификация", "Пересчитать"]),
        FieldConfig(name="brand_slot_3_id", label="Вариант 3 — бренд", widget="select",
                    row_actions=["Спецификация", "Пересчитать"]),
    ],
    relations=[
        Relation(field="client_id", target_table="client", display_field="short_name", label="Клиент (заказчик)"),
        Relation(field="client_invoice_id", target_table="client", display_field="short_name", label="Клиент (для счёта)"),
        Relation(field="brand_slot_1_id", target_table="brand", display_field="name", label="Вариант 1 — бренд"),
        Relation(field="brand_slot_2_id", target_table="brand", display_field="name", label="Вариант 2 — бренд"),
        Relation(field="brand_slot_3_id", target_table="brand", display_field="name", label="Вариант 3 — бренд"),
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
]
