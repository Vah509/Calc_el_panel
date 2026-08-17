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
    # ВРЕМЕННО (v39): child_key НЕ указывает на "kit" — хотя
    # концептуально kit_section является родителем kit в дереве
    # (kit_group -> kit_section -> kit), сам kit пока заведён как
    # ОБЫЧНАЯ ПЛОСКАЯ таблица старого движка (см. kit_table ниже и
    # app/models/kit.py) — вручную заносим пробные записи перед тем
    # как проектировать полноценный подбор материалов внутри карточки.
    # Если здесь проставить child_key="kit", _build_hierarchy_levels
    # (page.py) молча включит kit в цепочку уровней дерева как узел
    # БЕЗ hierarchy (AttributeError/некорректный JSON) — child_key
    # вернётся, когда kit станет настоящим drill-down уровнем
    # (hierarchy=Hierarchy(parent_field=..., parent_key="kit_section")).
    hierarchy=Hierarchy(parent_field="kit_group_id", parent_key="kit_group"),
    fields=[
        FieldConfig(name="name", label="Название", required=True, searchable=True),
        FieldConfig(name="kit_group_id", label="Группа", widget="select", required=True, in_list=False, in_form=False),
        FieldConfig(name="sort_order", label="Порядок", widget="number",
                    is_numeric=True, list_width="100px", default=0, in_list=False),
    ],
)


# kit / kit_item — ВРЕМЕННО (v39) обычные плоские таблицы старого
# движка, не часть drill-down дерева (см. развёрнутое обоснование в
# app/models/kit.py и app/models/kit_item.py). Позволяют вручную
# занести пробные записи, пока полноценный подбор материалов внутри
# карточки kit не спроектирован. kit_section_id/kit_id/material_id —
# простые select без поиска, по образцу material_table.brand_id.
kit_table = TableConfig(
    key="kit",
    model=Kit,
    title="Комплекты (временный список)",
    title_singular="комплект",
    search_placeholder="Поиск по названию…",
    delete_mode="soft",
    fields=[
        FieldConfig(name="name", label="Название", required=True, searchable=True),
        FieldConfig(name="kit_section_id", label="Раздел", widget="select", required=True),
        FieldConfig(name="sort_order", label="Порядок", widget="number",
                    is_numeric=True, list_width="100px", default=0),
    ],
    relations=[
        Relation(field="kit_section_id", target_table="kit_section", display_field="name", label="Раздел"),
    ],
    form_rows=[
        FormRow(field_names=["kit_section_id", "sort_order"]),
    ],
)


kit_item_table = TableConfig(
    key="kit_item",
    model=KitItem,
    title="Состав комплектов (временный список)",
    title_singular="позиция состава",
    search_placeholder="Поиск…",
    # delete_mode не указан -> дефолт "hard": на KitItem ничего не
    # ссылается (см. обоснование в app/models/kit_item.py), удаление
    # позиции состава всегда безусловное и немедленное, без пометки.
    fields=[
        FieldConfig(name="kit_id", label="Комплект", widget="select", required=True),
        FieldConfig(name="material_id", label="Материал", widget="select", required=True),
        FieldConfig(name="quantity", label="Количество", widget="number",
                    is_numeric=True, list_width="100px", default=1),
    ],
    relations=[
        Relation(field="kit_id", target_table="kit", display_field="name", label="Комплект"),
        Relation(field="material_id", target_table="material", display_field="short_name", label="Материал"),
    ],
    form_rows=[
        FormRow(field_names=["kit_id", "material_id"]),
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
    kit_table, kit_item_table, constant_table,
]
