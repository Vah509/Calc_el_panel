# app/models/firm.py
# ============================================================
# Firm — справочник СВОИХ юрлиц-продавцов (не путать с Client —
# тот справочник ПОКУПАТЕЛЕЙ). Нужен для шапки счёта-фактуры
# (invoice): "Постачальник" в печатной форме — см. образец
# СФ-0000040, обсуждение 2026-08-29.
#
# Сейчас предполагается ОДНА фирма, но справочник заведён отдельной
# таблицей (не константы), потому что Вахтанг допускает появление
# второй/третьей фирмы в будущем — тогда счёт должен уметь выбирать
# продавца, а не иметь его хардкодом.
#
# is_default — ровно одна фирма может быть "по умолчанию": именно
# она подставляется в новый Invoice автоматически (запрос
# Firm.is_default == True прямо в _build_invoice_handler, см.
# app/engine/tables.py). Переключается кнопкой "Сделать по
# умолчанию" (_set_default_firm_handler в tables.py) — НЕ обычным
# FieldConfig на форме: движок не умеет корректно приводить
# "true"/"false" из <select>/<radio> к настоящему bool перед INSERT
# (проверено на практике, попытка с widget="radio" сохраняла
# строку, а не bool, и упала бы на Postgres) — тот же обходной путь,
# что и у is_deleted (переключается отдельным action/эндпоинтом, не
# формой). _set_default_firm_handler сам гарантирует, что is_default
# стоит ровно у одной фирмы (снимает у всех остальных перед
# установкой) — простая инвариантная проверка в коде, без
# constraint в БД (тот же принцип, что и остальные бизнес-правила в
# этом проекте).
#
# Поля реквизитов — по образцу СФ-0000040 (см. HANDOFF/обсуждение):
# полное название, ЄДРПОУ, ІПН, номер свідоцтва платника ПДВ,
# банковские реквизиты (р/р, банк, МФО), телефон, адрес.
# ============================================================

from typing import Optional
from sqlmodel import SQLModel, Field


class Firm(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    full_name: str = Field(default="")
    is_default: bool = Field(default=False, index=True)

    egrpou_code: str = Field(default="")           # ЄДРПОУ
    tax_id: str = Field(default="")                 # ІПН
    vat_certificate_number: str = Field(default="")  # № свідоцтва платника ПДВ

    bank_account: str = Field(default="")           # Р/р (IBAN)
    bank_name: str = Field(default="")               # Банк
    bank_mfo: str = Field(default="")                # МФО

    phone: str = Field(default="")
    address: str = Field(default="")

    # is_deleted — визуальная пометка "к удалению" (soft-delete),
    # НЕ фильтрация — см. комментарий в app/models/material.py.
    is_deleted: bool = Field(default=False, index=True)
