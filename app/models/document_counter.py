# app/models/document_counter.py
# ============================================================
# DocumentCounter — по одной строке на каждый префикс документа
# (сейчас только "R" — заявка). Хранит last_number: последний
# ВЫДАННЫЙ автоматически или ПОДТЯНУТЫЙ вручную номер.
#
# Не таблица движка (не в ALL_TABLES, нет своей страницы/API) —
# читается и пишется только через app/engine/document_numbering.py,
# person её не редактирует напрямую.
#
# Правила (см. app/engine/document_numbering.py):
# - при создании документа без явного номера — берётся last_number+1,
#   счётчик увеличивается на 1
# - при сохранении с ЯВНО указанным номером (создание или правка) —
#   если число в номере больше текущего last_number, счётчик
#   подтягивается вверх до этого числа (не назад, только вверх)
# - дубликаты номеров МЕЖДУ документами не проверяются — сознательно,
#   по решению Вахтанга (2026-08-19): номер можно вписать любой
#   вручную, даже уже занятый
# ============================================================

from typing import Optional
from sqlmodel import SQLModel, Field


class DocumentCounter(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    prefix: str = Field(index=True, unique=True)
    last_number: int = Field(default=0)
