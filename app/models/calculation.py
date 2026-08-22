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

    # is_deleted — визуальная пометка "к удалению" (soft-delete),
    # НЕ фильтрация — см. комментарий в app/models/material.py.
    is_deleted: bool = Field(default=False, index=True)
