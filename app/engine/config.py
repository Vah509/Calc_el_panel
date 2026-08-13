# app/engine/config.py
# ============================================================
# УНИВЕРСАЛЬНЫЙ ДВИЖОК CRUD-ТАБЛИЦ — конфигурация.
#
# Идея: вместо того чтобы на каждую справочную таблицу (материалы,
# бренды, категории и т.д.) писать отдельный роутер + отдельный
# Alpine-шаблон вручную, мы один раз описываем таблицу декларативно
# через TableConfig — а движок (engine/api.py + engine/page.py) сам
# генерирует JSON API и HTML-страницу со списком+модалкой.
#
# Что покрывает движок:
#  - обычные поля (текст, число)
#  - computed_pairs — пара полей, взаимно пересчитываемых по формуле
#    (пример: price_excl_vat <-> price_incl_vat через vat_rate)
#  - relations — внешний ключ, отображаемый как выпадающий список
#    и как "живая ссылка" (имя связанной записи, а не голый ID)
#
# Чего движок НЕ покрывает (и не должен) — это осознанно:
#  - каскадные пересчёты между разными документами (продукт → спека
#    → заказ) — слишком специфичная бизнес-логика
#  - составные документы (заказ, инвойс) со своими правилами
#  - снапшоты (расчётные факты, которые не должны быть "живыми
#    ссылками") — для таких сценариев пишем отдельный код, движок
#    только для простых источников истины (справочников)
# ============================================================

from dataclasses import dataclass, field
from typing import Any, Literal, Optional
from sqlmodel import SQLModel


FieldWidget = Literal["text", "number", "select"]


@dataclass
class FieldConfig:
    """Одно поле формы/списка."""
    name: str                      # имя атрибута в модели, например "short_name"
    label: str                     # подпись на русском для формы/списка
    widget: FieldWidget = "text"
    required: bool = False
    placeholder: str = ""
    in_list: bool = True           # показывать в таблице списка
    list_width: Optional[str] = None   # например "26%" или "100px"
    searchable: bool = False       # участвует в текстовом поиске (q=...)
    search_toggle: bool = True     # если searchable=True и на таблице включены
                                    # enable_search_toggles — показывать ли для
                                    # этого поля отдельный чекбокс "искать по …"
                                    # (True) или включать его в поиск всегда,
                                    # без отдельного управления (False)
    search_default: bool = True    # если search_toggle=True — состояние чекбокса
                                    # при первой загрузке страницы (True — отмечен,
                                    # False — снят; человек может переключить вручную,
                                    # выбор держится, пока страница открыта)
    is_numeric: bool = False       # для выравнивания по правому краю и форматирования
    in_form: bool = True           # показывать в форме модалки (по умолчанию — да)
    form_width: Optional[str] = None   # фиксированная ширина поля в форме, например "140px";
                                        # если не задано — поле растягивается на всю доступную ширину ряда
    default: Any = None            # значение по умолчанию при создании новой записи
                                    # (если None — используется 0 для числовых, '' для текстовых)


@dataclass
class ComputedPair:
    """
    Пара полей, взаимно пересчитываемых друг из друга по формуле.
    Пример: цена без НДС <-> цена с НДС, через ставку НДС.

    formula="vat" — единственный встроенный тип пока. Формула:
        field_b = field_a * (1 + rate / 100)
        field_a = field_b / (1 + rate / 100)
    Новые формулы (наценка, скидка) добавляются в engine/formulas.py
    по мере реальной потребности — не заранее.
    """
    field_a: str
    field_b: str
    rate_field: str
    formula: Literal["vat"] = "vat"
    label_a: str = ""
    label_b: str = ""
    label_rate: str = ""


@dataclass
class Relation:
    """
    Связь с другой справочной таблицей — внешний ключ, показываемый
    как выпадающий список в форме и как имя (не ID) в списке.
    "Живая ссылка" в терминах проекта: показывается текущее имя
    связанной записи, обновляется само при переименовании.
    """
    field: str                     # например "brand_id"
    target_table: str              # ключ таблицы в TABLE_REGISTRY, например "brand"
    display_field: str = "name"    # какое поле связанной записи показывать
    label: str = ""


@dataclass
class FormRow:
    """
    Один визуальный ряд формы — список имён полей, которые должны
    отображаться рядом друг с другом (а не каждое на отдельной строке).

    Если в ряду 2+ поля — рендерится как flex-контейнер (.field-row
    для обычных полей или .price-pair, если хотя бы одно поле ряда
    входит в computed_pairs). Поля, не перечисленные ни в одном
    FormRow, идут каждое отдельным рядом — по порядку объявления в
    TableConfig.fields.
    """
    field_names: list[str] = field(default_factory=list)


@dataclass
class TableConfig:
    """Полное декларативное описание одной таблицы для движка."""
    key: str                       # уникальный ключ, например "material"
    model: type[SQLModel]
    title: str                     # заголовок страницы, например "Материалы"
    title_singular: str            # для модалки, например "материал"
    fields: list[FieldConfig] = field(default_factory=list)
    computed_pairs: list[ComputedPair] = field(default_factory=list)
    relations: list[Relation] = field(default_factory=list)
    form_rows: list[FormRow] = field(default_factory=list)
    search_placeholder: str = "Поиск…"
    enable_search_toggles: bool = False
    # Если True — на странице сверху под строкой поиска показываются
    # чекбоксы "искать по <label>" для каждого searchable-поля, и
    # пользователь может включать/выключать поля поиска по отдельности.
    # Общий принцип поиска (искать по всем searchable через ?q=) не
    # меняется — эта опция лишь добавляет фильтр по конкретным полям
    # поверх него, через ?q=...&search_fields=name1&search_fields=name2.

    def field_names(self) -> list[str]:
        return [f.name for f in self.fields]

    def searchable_fields(self) -> list[str]:
        return [f.name for f in self.fields if f.searchable]

    def toggleable_search_fields(self) -> list[FieldConfig]:
        """Поля, для которых показывается отдельный чекбокс поиска
        (searchable=True и search_toggle=True)."""
        return [f for f in self.fields if f.searchable and f.search_toggle]

    def always_searched_fields(self) -> list[str]:
        """Searchable-поля, которые ищутся всегда, независимо от
        состояния чекбоксов (searchable=True, но search_toggle=False)."""
        return [f.name for f in self.fields if f.searchable and not f.search_toggle]
