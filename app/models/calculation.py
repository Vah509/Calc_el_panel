# app/models/calculation.py
# ============================================================
# Calculation (калькуляция) — второй документ цепочки
# zayavka -> calculation -> specification -> invoice (см.
# docs/HANDOFF_kits_and_calculation.md, раздел 2). Считает
# стоимость по ОДНОМУ из трёх брендовых вариантов заявки.
# В этом шаге — только "шапка" документа, без состава
# (calculation_item — следующий шаг).
#
# request_id — FK на Request, NULLABLE. По умолчанию калькуляция
# всегда создаётся на основании заявки (кнопка "Создать документ
# на основании" у request), но nullable оставлен на случай редкого
# сценария калькуляции без заявки (по прямому решению Вахтанга,
# 2026-08-21).
#
# client_name / full_name / name_template — три текстовых поля
# вокруг названия калькуляции:
#   - client_name — "рабочее название", вводится человеком вручную
#     сразу (черновой рабочий заголовок, как в заявке client_name
#     концептуально НЕ то же самое, что client_id заявки — здесь
#     это просто текст, не ссылка на справочник client).
#   - name_template — шаблон полного названия, СВОЙ у каждой
#     калькуляции (не общая константа — Вахтанг явно попросил
#     возможность менять под конкретный случай), живёт на вкладке
#     "Настройки" формы. Поддерживает плейсхолдеры {client_name},
#     {brand_slot}, {request_number} — см.
#     app/engine/name_template.py::render_name_template().
#     Дефолт при создании новой калькуляции — см. DEFAULT_NAME_TEMPLATE
#     ниже.
#   - full_name — результат подстановки name_template, пересчитывается
#     НЕ автоматически при сохранении, а вручную по кнопке
#     "Пересчитать название" (решение Вахтанга — избежать неожиданной
#     перезаписи руками поправленного названия при каждом save).
#     Свободно редактируется и напрямую, если нужно поправить
#     результат подстановки точечно.
#
# brand_slot — номер варианта (1/2/3), тот же принцип, что и в
# request.brand_slot_N_id: группировка идёт по НОМЕРУ слота, не по
# самому brand_id (сам бренд смотрим через request по этому номеру).
#
# status — свободные переходы, без принудительного порядка (решение
# из HANDOFF_kits_and_calculation.md, раздел 2): draft/active/
# archived_pending/delete_pending. Пересчёт стоимости разрешён в
# любом статусе.
#
# document_number/document_date/document_time — тот же принцип
# нумерации, что и у request (см. app/engine/document_numbering.py),
# свой префикс "K". document_time — НОВОЕ отдельное поле (не было
# у request) — вместе с датой даёт точную хронологию создания для
# журнала подчинённых документов (Вахтанг: "часто работаю именно в
# журнале, важно видеть кто раньше кто позже"). Оба поля свободно
# редактируются вручную, как и дата у заявки; сортировка списка по
# умолчанию — сначала по document_date, потом по document_time,
# оба по убыванию (новые сверху).
#
# --- Вкладка "Стоимость" (2026-08-26) ---
# Считает итоговую цену изделия поверх суммы строк calculation_item
# (материалы + комплекты). Пересчёт — той же кнопкой "Пересчитать",
# что уже пересчитывает цены материалов/комплектов на вкладке
# "Материалы" (см. _recalc_material_prices_handler в
# app/engine/tables.py) — по прямому решению Вахтанга ЛЮБАЯ кнопка
# пересчёта внутри калькуляции пересчитывает её целиком.
#
# Порядок расчёта (согласовано 2026-08-26):
#   1. materials_total  = Σ price_excl_vat по CalculationItem, где
#      заполнен material_id
#   2. kits_total        = Σ price_excl_vat по CalculationItem, где
#      заполнен kit_id
#   3. base_total        = materials_total + kits_total
#   4. insured_total     = base_total * insurance_markup
#   5а. markup_total     = insured_total * markup_percent  (способ "наценка")
#   5б. hours_total      = insured_total + assembly_hours * (стоимость
#      часа из ProductTypeRate.hourly_rate по product_type_rate_id)
#      (способ "часы")
#   6. final_total       = markup_total ИЛИ hours_total, в зависимости
#      от cost_method — то, что попадает в базу при нажатии "Сохранить"
# Если calculation_item ещё нет ни одного — все суммы просто 0, без
# ошибки (пустая калькуляция — не invalid state).
#
# materials_total/kits_total/base_total/insured_total/markup_total/
# hours_total/final_total — СНЭПШОТЫ, как и цены самих CalculationItem:
# обновляются по кнопке "Пересчитать", между пересчётами не "плывут"
# сами по себе даже если что-то в справочниках изменилось.
#
# markup_percent/insurance_markup — редактируемые ЧИСЛА НА САМОЙ
# калькуляции (НЕ readonly-ссылка на константу), дефолт при создании
# берётся из констант "markup_percent"/"insurance_markup" (см.
# app/database.py::seed_constants) — тот же паттерн, что и
# name_template/DEFAULT_NAME_TEMPLATE выше, значение можно свободно
# поправить под конкретный случай на конкретной калькуляции.
#
# cost_method — переключатель способа расчёта ("markup"/"hours"),
# тот же принцип radio, что и brand_slot: ровно один активен.
# Определяет, какая из двух посчитанных сумм (markup_total/hours_total)
# идёт в final_total при сохранении. Оба блока (наценка и часы) в
# форме показываются ОДНОВРЕМЕННО — переключатель влияет только на
# то, что попадает в итог, не на видимость полей.
#
# assembly_hours/product_type_rate_id — используются только способом
# "часы", но существуют независимо от того, какой cost_method выбран
# сейчас (человек может прикинуть оба варианта и переключаться между
# ними). product_type_rate_id — FK на ProductTypeRate (справочник
# "Стоимость сборки": тип изделия -> стоимость часа), nullable — но
# форма подставляет изделие по умолчанию при создании новой
# калькуляции (см. DEFAULT_PRODUCT_TYPE_RATE_NAME ниже и
# _default_product_type_rate_id в app/engine/tables.py).
# ============================================================

from datetime import date, time, datetime
from typing import Optional
from sqlmodel import SQLModel, Field


def _now_time() -> time:
    return datetime.now().time().replace(microsecond=0)


# Дефолтный шаблон полного названия, подставляемый при создании новой
# калькуляции (человек может тут же поправить под конкретный случай —
# см. комментарий у name_template выше). Согласовано 2026-08-21:
# "Сборка " + рабочее название (client_name), без brand_slot/
# request_number по умолчанию — их можно добавить вручную при
# необходимости, полный список плейсхолдеров см. в подсказке под
# полем "Шаблон полного названия" в форме (FieldConfig.hint,
# app/engine/tables.py) и в app/engine/name_template.py.
DEFAULT_NAME_TEMPLATE = "Сборка {client_name}"

# Название записи ProductTypeRate, подставляемой по умолчанию как
# product_type_rate_id при создании новой калькуляции (см.
# _default_product_type_rate_id в app/engine/tables.py). Если записи
# с таким name ещё нет в справочнике "Стоимость сборки" — поле просто
# остаётся пустым, ничего не падает.
DEFAULT_PRODUCT_TYPE_RATE_NAME = "Стандартное изделие"


class Calculation(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    document_number: str = Field(default="")
    document_date: date = Field(default_factory=date.today)
    document_time: time = Field(default_factory=_now_time)
    request_id: Optional[int] = Field(default=None, foreign_key="request.id")
    client_name: str = Field(default="")
    full_name: str = Field(default="")
    name_template: str = Field(default=DEFAULT_NAME_TEMPLATE)
    brand_slot: Optional[int] = Field(default=None)
    status: str = Field(default="draft")

    # --- Стоимость (см. комментарий блока выше) ---
    cost_method: str = Field(default="markup")
    markup_percent: float = Field(default=1.4)
    insurance_markup: float = Field(default=1.1)
    assembly_hours: float = Field(default=0.0)
    product_type_rate_id: Optional[int] = Field(default=None, foreign_key="producttyperate.id")
    materials_total: float = Field(default=0.0)
    kits_total: float = Field(default=0.0)
    base_total: float = Field(default=0.0)
    insured_total: float = Field(default=0.0)
    markup_total: float = Field(default=0.0)
    hours_total: float = Field(default=0.0)
    final_total: float = Field(default=0.0)

    # is_deleted — визуальная пометка "к удалению" (soft-delete),
    # НЕ фильтрация — см. комментарий в app/models/material.py.
    is_deleted: bool = Field(default=False, index=True)
