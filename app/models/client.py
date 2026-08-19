# app/models/client.py
# ============================================================
# Client — справочник клиентов. Используется заявкой (request)
# дважды: как заказчик (client_id) и как получатель счёта
# (client_invoice_id) — эти два поля могут указывать на разные
# записи, если счёт выставляется не на того, кто оформил заявку.
#
# short_name — внутреннее название, по которому удобно искать
# (то, как клиента называют в разговоре). full_name — официальное
# название, фигурирует во всех выходных документах (счетах,
# спецификациях). Оба обязательны и оба ищутся текстовым поиском.
# ============================================================

from typing import Optional
from sqlmodel import SQLModel, Field


class Client(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    short_name: str = Field(index=True)
    full_name: str = Field(default="")
    egrpou_code: str = Field(default="")
    phone: str = Field(default="")
    contact_person_name: str = Field(default="")
    contact_person_phone: str = Field(default="")

    # is_deleted — визуальная пометка "к удалению" (soft-delete),
    # НЕ фильтрация — см. комментарий в app/models/material.py.
    is_deleted: bool = Field(default=False, index=True)
