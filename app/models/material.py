# app/models/material.py
# ============================================================
# Материал каталога. Два независимых поля цены (без НДС / с НДС)
# с взаимным авто-пересчётом через движок (см. app/engine/api.py,
# ComputedPair) — в модели они просто два поля, ничего "магического"
# на уровне БД не происходит.
#
# Ставки НДС в модели больше нет (была vat_rate, удалена v28) —
# ставка общая для всех материалов и хранится ТОЛЬКО в справочнике
# constants (ключ vat_rate). В карточке материала показывается как
# "живая ссылка": readonly, всегда актуальное значение из constants,
# используется при пересчёте price_excl_vat <-> price_incl_vat
# (см. tables.py, ComputedPair.rate_constant_key).
#
# short_name / full_name — два разных имени: короткое (для быстрого
# поиска и списков, по конвенции бренд-код + тип + параметры) и
# длинное (человекочитаемое полное название).
# ============================================================

from typing import Optional
from sqlmodel import SQLModel, Field


class Material(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)

    short_name: str = Field(index=True)
    full_name: str

    brand_id: Optional[int] = Field(default=None, foreign_key="brand.id")
    sku_article: Optional[str] = Field(default=None, index=True)

    # unit_id — единица измерения (шт/м/кг/услуга...), см. app/models/unit.py.
    # Nullable на уровне БД сознательно (2026-08-23) — чтобы не ломать
    # миграцию на уже существующих в проде материалах без единицы
    # измерения. В UI/API для новых/редактируемых записей поле обязательно
    # (валидация на уровне FieldConfig.required, не на уровне схемы).
    unit_id: Optional[int] = Field(default=None, foreign_key="unit.id")

    price_excl_vat: float = Field(default=0.0)
    price_incl_vat: float = Field(default=0.0)

    # price_vb_incl_vat — цена материала в валюте бренда-поставщика
    # (с НДС), независимый от price_incl_vat факт. Не пересчитывается
    # автоматически и не связана с rate_vb на уровне TMC — связь
    # (price_vb_incl_vat × Brand.rate_vb) считается "на лету" только
    # в калькуляции, когда пользователь явно выбирает источник цены
    # "по курсу поставщика" вместо обычной гривневой цены.
    price_vb_incl_vat: float = Field(default=0.0)

    # owner_id — задел под будущую многопользовательскую модель
    # (см. спецификацию: разграничение по owner_id, без ролей)
    owner_id: Optional[int] = Field(default=None, index=True)

    # is_deleted — визуальная пометка "к удалению" (soft-delete),
    # НЕ фильтрация. Помеченные записи остаются полностью рабочими
    # для всех обработчиков и документов до момента физического
    # удаления отдельным обработчиком (см. app/processors/registry.py).
    is_deleted: bool = Field(default=False, index=True)
