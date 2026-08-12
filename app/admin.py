# app/admin.py
# ============================================================
# ЭКСПЕРИМЕНТ: sqladmin — готовая CRUD-админка "из коробки",
# для сравнения с самописной HTMX-версией и с версией на
# Alpine.js + JSON API.
#
# В отличие от materials_api.py / list_alpine.html, здесь мы НЕ
# пишем ни строчки HTML/JS — просто описываем, какие колонки
# показывать в списке и в форме, всё остальное (модалка... точнее
# отдельная страница редактирования, поиск, сортировка, пагинация,
# валидация, удаление) генерирует сама библиотека sqladmin.
# ============================================================

from sqladmin import Admin, ModelView

from app.database import engine
from app.models.material import Material
from app.models.brand import Brand


class MaterialAdmin(ModelView, model=Material):
    name = "Материал"
    name_plural = "Материалы"
    icon = "fa-solid fa-box"

    column_list = [
        Material.id,
        Material.short_name,
        Material.full_name,
        Material.brand_id,
        Material.sku_article,
        Material.price_excl_vat,
        Material.price_incl_vat,
        Material.vat_rate,
    ]
    column_searchable_list = [Material.short_name, Material.sku_article, Material.full_name]
    column_sortable_list = [Material.short_name, Material.price_excl_vat, Material.price_incl_vat]

    form_columns = [
        Material.short_name,
        Material.full_name,
        Material.brand_id,
        Material.sku_article,
        Material.price_excl_vat,
        Material.price_incl_vat,
        Material.vat_rate,
    ]

    can_create = True
    can_edit = True
    can_delete = True
    can_view_details = True

    page_size = 50


class BrandAdmin(ModelView, model=Brand):
    name = "Бренд"
    name_plural = "Бренды"
    icon = "fa-solid fa-tag"

    column_list = [Brand.id, Brand.name]
    column_searchable_list = [Brand.name]
    form_columns = [Brand.name]

    can_create = True
    can_edit = True
    can_delete = True


import os

def register_admin(app):
    """Подключает sqladmin к FastAPI-приложению. Путь: /materials1 (base_url).

    templates_dir указывает на app/admin_templates — там лежит только
    один override-файл (sqladmin/base.html), который подключает нашу
    тему admin-theme.css. Jinja ищет шаблон сначала в templates_dir,
    и только если не находит — берёт встроенный шаблон sqladmin.
    Поэтому переопределяется ТОЛЬКО head (стили), вся остальная
    разметка/логика (формы, модалка удаления, поиск) — родная sqladmin.
    """
    templates_dir = os.path.join(os.path.dirname(__file__), "admin_templates")
    admin = Admin(app, engine, base_url="/materials1", title="ЭлектроЩит — Админка", templates_dir=templates_dir)
    admin.add_view(MaterialAdmin)
    admin.add_view(BrandAdmin)
    return admin
