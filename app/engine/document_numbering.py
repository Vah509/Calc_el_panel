# app/engine/document_numbering.py
# ============================================================
# Общая логика номера документа "префикс-число" (например "R-101"),
# переиспользуемая любым будущим документом движка (заявка сейчас,
# калькуляция/спецификация/счёт-фактура — позже, каждый свой префикс).
#
# Правила (согласованы с Вахтангом 2026-08-19):
# - номер редактируется человеком вручную, дубликаты НЕ проверяются
# - при создании документа, если номер не передан (пусто) — сервер сам
#   генерирует "{prefix}-{last_number+1}" и продвигает счётчик на 1
# - при любом сохранении (создание ИЛИ правка) с номером, где число
#   после префикса БОЛЬШЕ текущего last_number счётчика — счётчик сам
#   подтягивается вверх до этого числа (следующий новый документ
#   продолжит от него). Если число меньше или равно — счётчик не
#   трогаем (не позволяем правке "утащить" его назад).
# - число не удалось распознать (человек стёр дефис, вписал произвольный
#   текст) — просто не двигаем счётчик, ничего не ломаем
#
# Счётчики хранятся в DocumentCounter (app/models/document_counter.py),
# по одной строке на префикс, отдельно от самих номеров документов —
# так правка одного документа не задевает нумерацию остальных, и не
# нужно каждый раз искать MAX(document_number) по всей таблице (что
# сломалось бы, если бы самый большой номер физически удалили).
# ============================================================

import re
from sqlmodel import Session, select

from app.models.document_counter import DocumentCounter

_NUMBER_RE = re.compile(r"(\d+)\s*$")


def _get_or_create_counter(session: Session, prefix: str) -> DocumentCounter:
    counter = session.exec(
        select(DocumentCounter).where(DocumentCounter.prefix == prefix)
    ).first()
    if counter is None:
        counter = DocumentCounter(prefix=prefix, last_number=0)
        session.add(counter)
        session.flush()
    return counter


def next_document_number(session: Session, prefix: str) -> str:
    """Продвигает счётчик префикса на 1 и возвращает готовый номер
    вида "{prefix}-{n}". Вызывается при создании документа, только
    если человек не ввёл номер сам."""
    counter = _get_or_create_counter(session, prefix)
    counter.last_number += 1
    session.add(counter)
    return f"{prefix}-{counter.last_number}"


def bump_counter_if_ahead(session: Session, prefix: str, document_number: str) -> None:
    """Если document_number содержит число больше текущего last_number
    счётчика — подтягивает счётчик вверх до этого числа. Вызывается
    при КАЖДОМ сохранении документа с непустым номером (создание с
    номером, вписанным вручную, или правка существующего номера)."""
    match = _NUMBER_RE.search(document_number or "")
    if not match:
        return
    parsed_number = int(match.group(1))
    counter = _get_or_create_counter(session, prefix)
    if parsed_number > counter.last_number:
        counter.last_number = parsed_number
        session.add(counter)
