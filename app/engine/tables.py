# app/engine/tables.py
# ============================================================
# Декларативные описания таблиц для универсального движка.
# Обкатка движка: материалы (с computed_pair НДС и relation на
# бренд) и бренды (простой справочник без пересчёта и без связей).
#
# Новую таблицу добавляем сюда же — одним TableConfig, без
# написания нового роутера/шаблона вручную.
# ============================================================

from app.engine.config import TableConfig, FieldConfig, ComputedPair, Relation, FormRow
from app.models.material import Material
from app.models.brand import Brand
from app.models.constant import Constant
from app.models.kit_group import KitGroup


brand_table = TableConfig(
    key="brand",
    model=Brand,
    title="Бренды",
    title_singular="бренд",
    search_placeholder="Поиск по названию…",
    soft_delete=True,
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
    soft_delete=True,
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


kit_group_table = TableConfig(
    key="kit_group",
    model=KitGroup,
    title="Группы комплектов",
    title_singular="группа комплектов",
    search_placeholder="Поиск по названию…",
    soft_delete=True,
    fields=[
        FieldConfig(name="name", label="Название", required=True, searchable=True),
        FieldConfig(name="sort_order", label="Порядок", widget="number",
                    is_numeric=True, list_width="100px", default=0),
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


ALL_TABLES = [brand_table, material_table, kit_group_table, constant_table]
