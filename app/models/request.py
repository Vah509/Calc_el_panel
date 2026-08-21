# app/models/request.py
# ============================================================
# Request (заявка) — первый документ цепочки zayavka -> calculation
# -> specification -> invoice (см. docs/HANDOFF_kits_and_calculation.md,
# раздел 2). Заводится при получении заявки от клиента; дальше на
# её основе создаются калькуляции (calculation, ещё не реализовано).
#
# client_id / client_invoice_id — оба FK на Client (справочник
# клиентов). Разделены, т.к. счёт может выставляться не на того,
# кто оформил заявку. client_invoice_id nullable — если не задан,
# UI/логика в будущем будет считать получателем счёта того же
# client_id (правило "по умолчанию" — на уровне UI/API, не в модели).
#
# brand_slot_1/2/3_id — FK на Brand, по одному на каждый из трёх
# независимых вариантов расчёта заявки. Все три слота ВСЕГДА видны
# в форме (не динамический список) — бренд может быть не выбран.
# Группировка калькуляций по варианту происходит по номеру слота
# (1/2/3), не по самому brand_id — см. calculation.brand_slot в
# HANDOFF_kits_and_calculation.md, раздел 2.3.
#
# document_number / document_date — номер и дата документа (v51).
# Оба редактируются вручную человеком. При создании, если не заданы
# явно — сервер сам подставляет: номер по счётчику префикса "R" (см.
# app/models/document_counter.py), дату — сегодняшнюю. Дубликаты
# номера НЕ проверяются (по решению Вахтанга — вручную можно вписать
# любой номер, даже уже занятый другим документом). Подробности
# генерации/подтяжки счётчика — см. app/engine/document_numbering.py.
#
# Кнопки "Спецификация"/"Пересчитать" у каждого варианта — в этом шаге
# НЕ реализуются (нет ещё calculation, ссылаться не на что), появляются
# в UI как неактивные заглушки. Архивация — отдельный будущий
# обработчик, здесь не реализована.
#
# note — свободная текстовая заметка (v55), к чему относится заявка.
# НЕ показывается в списке/поиске (in_list=False, не searchable) —
# только в форме открытой записи, многострочное поле (widget="textarea").
# ============================================================

from datetime import date
from typing import Optional
from sqlmodel import SQLModel, Field


class Request(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    document_number: str = Field(default="")
    document_date: date = Field(default_factory=date.today)
    client_id: Optional[int] = Field(default=None, foreign_key="client.id")
    client_invoice_id: Optional[int] = Field(default=None, foreign_key="client.id")
    brand_slot_1_id: Optional[int] = Field(default=None, foreign_key="brand.id")
    brand_slot_2_id: Optional[int] = Field(default=None, foreign_key="brand.id")
    brand_slot_3_id: Optional[int] = Field(default=None, foreign_key="brand.id")
    note: str = Field(default="")

    # is_deleted — визуальная пометка "к удалению" (soft-delete),
    # НЕ фильтрация — см. комментарий в app/models/material.py.
    is_deleted: bool = Field(default=False, index=True)
