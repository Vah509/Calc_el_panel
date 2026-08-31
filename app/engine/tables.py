# app/engine/tables.py
# ============================================================
# Декларативные описания таблиц для универсального движка.
# Обкатка движка: материалы (с computed_pair НДС и relation на
# бренд) и бренды (простой справочник без пересчёта и без связей).
#
# Новую таблицу добавляем сюда же — одним TableConfig, без
# написания нового роутера/шаблона вручную.
# ============================================================

from sqlmodel import select
from fastapi import HTTPException
from app.engine.config import TableConfig, FieldConfig, ComputedPair, Relation, FormRow, Hierarchy, ActionButton
from app.models.material import Material
from app.models.brand import Brand
from app.models.unit import Unit
from app.models.constant import Constant
from app.models.kit_group import KitGroup
from app.models.kit_section import KitSection
from app.models.kit import Kit
from app.models.kit_item import KitItem
from app.models.client import Client
from app.models.request import Request
from app.models.calculation import Calculation, DEFAULT_NAME_TEMPLATE, DEFAULT_CALCULATION_UNIT_NAME
from app.models.calculation_item import CalculationItem
from app.models.product_type_rate import ProductTypeRate
from app.models.specification import Specification
from app.models.specification_item import SpecificationItem
from app.models.firm import Firm
from app.models.invoice import Invoice
from app.models.invoice_item import InvoiceItem
from app.models.document_counter import DocumentCounter  # noqa: F401 — не таблица
# движка (нет своего TableConfig/страницы), но должна быть импортирована
# здесь, чтобы SQLModel.metadata.create_all() увидела её при старте
# (см. app/database.py) — единственное место, куда стягиваются импорты
# всех моделей проекта.


brand_table = TableConfig(
    key="brand",
    model=Brand,
    title="Бренды",
    title_singular="бренд",
    search_placeholder="Поиск по названию…",
    delete_mode="soft",
    fields=[
        FieldConfig(name="name", label="Название", required=True, searchable=True),
        FieldConfig(name="rate_vb", label="Курс ВБ", widget="number",
                    is_numeric=True, list_width="100px"),
    ],
)


# Единица измерения (шт/м/кг/услуга...) — плоский справочник, тот же
# паттерн, что kit_group/kit_section (delete_mode="simple": физическое
# удаление, только через модалку ✎, без чекбоксов/групповых операций).
# БЕЗ hierarchy — это не узел дерева, самостоятельная плоская таблица,
# delete_mode="simple" здесь просто означает "нет soft-delete, удаление
# сразу физическое" (без hierarchy проверка на дочерние записи не
# применяется, см. delete_item в api.py).
unit_table = TableConfig(
    key="unit",
    model=Unit,
    title="Единицы измерения",
    title_singular="единица измерения",
    search_placeholder="Поиск по названию…",
    delete_mode="simple",
    fields=[
        FieldConfig(name="name", label="Название", required=True, searchable=True,
                    placeholder="шт"),
        FieldConfig(name="sort_order", label="Порядок", widget="number",
                    is_numeric=True, list_width="100px", default=0, in_list=False),
    ],
)


# Стоимость сборки (2026-08-26) — справочник для способа расчёта
# стоимости калькуляции "по часам" (см. вкладка "Стоимость" в
# calculation_table ниже, Calculation.product_type_rate_id). Бывают
# более сложные и более простые изделия — стоимость часа сборки по
# ним может отличаться, отсюда отдельный справочник, а не одна общая
# константа "стоимость часа". Обычный плоский справочник, без
# hierarchy — см. app/models/product_type_rate.py.
product_type_rate_table = TableConfig(
    key="product_type_rate",
    model=ProductTypeRate,
    title="Стоимость сборки",
    title_singular="тип изделия",
    search_placeholder="Поиск по названию…",
    delete_mode="soft",
    fields=[
        FieldConfig(name="name", label="Название", required=True, searchable=True,
                    search_default=True, list_width="60%"),
        FieldConfig(name="hourly_rate", label="Стоимость часа", widget="number",
                    is_numeric=True, list_width="140px", default=0),
    ],
)


client_table = TableConfig(
    key="client",
    model=Client,
    title="Клиенты",
    title_singular="клиент",
    search_placeholder="Поиск по названию…",
    enable_search_toggles=True,
    delete_mode="soft",
    fields=[
        FieldConfig(name="short_name", label="Короткое название", required=True,
                    searchable=True, search_default=True, list_width="22%"),
        FieldConfig(name="full_name", label="Полное название",
                    searchable=True, search_default=False, list_width="28%"),
        FieldConfig(name="egrpou_code", label="Код ЕГРПОУ", list_width="110px"),
        FieldConfig(name="phone", label="Телефон", list_width="120px"),
        FieldConfig(name="contact_person_name", label="Контактное лицо", in_list=False),
        FieldConfig(name="contact_person_phone", label="Телефон контактного лица", in_list=False),
    ],
    form_rows=[
        FormRow(field_names=["contact_person_name", "contact_person_phone"]),
    ],
)


# Заявка (request) — первый документ цепочки zayavka -> calculation ->
# specification -> invoice (docs/HANDOFF_kits_and_calculation.md, раздел 2).
# document_number/document_date — номер и дата документа, оба
# редактируются вручную; номер при создании автогенерируется по
# счётчику префикса "R" (document_prefix), если не введён явно —
# см. app/engine/document_numbering.py. Три слота бренда — три
# независимых варианта расчёта, всегда видны в форме, каждый может
# быть пустым. У каждого слота — своя пара кнопок «Спецификация»/
# «Пересчитать» рядом с выбором бренда (FieldConfig.row_actions).
# «Спецификация» (2026-08-27) — реальный обработчик, см.
# _build_specification_handler ниже, по одному на слот
# (build_specification_1/2/3 в action_handlers, номер слота зашит в
# имени action). «Пересчитать» — по-прежнему заглушка (row_action_names
# на этой позиции = None), своей логики ещё нет. Общей кнопки
# "Пересчитать всё" сознательно нет — по прямому решению Вахтанга
# (2026-08-19): пересчёт всегда по одному варианту, так проще уследить,
# что где пересчиталось.
#
# Поиск (v52, по фидбеку с реального устройства): у документа 5
# relation-полей (2 клиента + 3 бренда) — стандартный ряд чипов-фильтров
# "Все/АСКО/ABB/ETI" движка на КАЖДОЕ из них выглядел захламлённо и
# бесполезно на телефоне (5 рядов чипов над списком заявок). Все чипы
# отключены (show_filter_chips=False у каждого Relation) в пользу
# обычного текстового поиска — по короткому и полному названию клиента,
# ЧЕРЕЗ join/подзапрос на client (Relation.searchable_fields), с
# переключаемыми чекбоксами "заказчик"/"для счёта" (enable_search_toggles,
# тот же паттерн, что и у client_table для собственных текстовых полей).
def _build_specification_handler(brand_slot: int):
    """Фабрика обработчика кнопки «Спецификация» слота brand_slot
    (1/2/3) — один обработчик на слот, а НЕ один параметризованный
    action на все три: action_handlers — плоский словарь по имени
    action (см. TableConfig.action_handlers), и текущий движок
    (runAction()/POST /api/{key}/{id}/actions/{action}) не передаёт
    никаких доп. параметров кроме имени действия — значит номер слота
    должен быть зашит в САМО имя action ("build_specification_1" и
    т.д.), а не передаваться отдельно. Фабрика просто убирает
    дублирование тела функции между тремя слотами.

    Механика (переработано 2026-08-30 — решение Вахтанга: подчинённый
    документ при повторном формировании ОБНОВЛЯЕТСЯ НА МЕСТЕ, а не
    удаляется и создаётся заново — то же поведение, что уже было у
    счёта, теперь и у спецификации):
      1. Собрать активные (status="active") калькуляции этой заявки
         с данным brand_slot.
      2. Если для (request_id, brand_slot) уже есть Specification —
         ОБНОВИТЬ ЕЁ НА МЕСТЕ: id и document_number (номер) НЕ
         меняются, привязки (в т.ч. уже созданный из неё Invoice —
         через specification_id) НЕ рвутся; document_date/
         document_time выставляются на текущий момент (проще и
         единообразнее, чем оставлять исходную дату — решение
         Вахтанга: "думаю для реализации это будет проще"). Позиции
         (SpecificationItem) при этом всё равно полностью
         пересобираются (delete+create) — сами строки меняют id,
         поэтому ссылка InvoiceItem.specification_item_id (трассировка)
         обнуляется у уже существующих строк счёта перед удалением
         старых SpecificationItem (см. комментарий у orphaned_invoice_
         items ниже) — это НЕ отвязка счёта, Invoice.specification_id
         остаётся как был.
      2а. ВАЖНО: если для этой спецификации уже есть привязанный
          (specification_id заполнен) Invoice — он должен быть
          обновлён СРАЗУ ЖЕ следом (тот самый "следующий документ",
          который тоже нужно обновить, по прямому указанию Вахтанга)
          — вызывается тот же код, что и у кнопки «Обновить» на
          счёте (_sync_invoice_items_from_specification +
          _recalculate_invoice_totals), а не оставляется до
          следующего ручного нажатия человеком.
      3. Если Specification для этого слота ещё не было — создаём
         новую (client_id = request.client_id, номер по счётчику
         префикса "S"), как и раньше.
      4. По одной SpecificationItem на калькуляцию (БЕЗ схлопывания
         повторяющихся названий — каждая калькуляция своя строка),
         line_total = final_total * quantity.
      5. total_amount = Σ line_total.
    НЕ пересчитывает сами калькуляции перед сборкой — берёт
    final_total как есть на момент нажатия (решение Вахтанга:
    "кнопка только собирает и показывает спеку").

    Возвращает {"redirect_url": "/specification-v2/{id}"} — НЕ патч
    полей текущей заявки (в отличие от большинства action_handlers):
    кнопка создаёт (или обновляет) ДРУГОЙ документ, а не правит
    instance, поэтому фронт (runAction() в page.py) при виде
    redirect_url переходит на страницу спецификации вместо
    подмешивания результата в открытую форму заявки.
    """

    def handler(instance: Request, session) -> dict:
        from app.engine.document_numbering import next_document_number
        from datetime import date as _date, datetime as _datetime

        calculations = session.exec(
            select(Calculation).where(
                Calculation.request_id == instance.id,
                Calculation.brand_slot == brand_slot,
                Calculation.status == "active",
            )
        ).all()

        existing = session.exec(
            select(Specification).where(
                Specification.request_id == instance.id,
                Specification.brand_slot == brand_slot,
            )
        ).first()

        if existing is not None:
            # ОБНОВЛЕНИЕ НА МЕСТЕ (2026-08-30) — id/document_number
            # сохраняются, дата/время формирования обновляются на
            # текущие. Позиции (SpecificationItem) всё равно
            # полностью пересобираются ниже (проще, чем построчно
            # сверять состав калькуляций), поэтому их СОБСТВЕННЫЕ id
            # всё равно меняются — отсюда необходимость обнулить
            # трассировочную ссылку у InvoiceItem (см. ниже), даже
            # притом что сама Specification и сам Invoice.
            # specification_id теперь остаются нетронутыми.
            existing.document_date = _date.today()
            existing.document_time = _datetime.now().time().replace(microsecond=0)
            session.add(existing)
            session.flush()
            spec = existing

            # ForeignKeyViolation на Postgres (обнаружено 2026-08-28
            # для самих Specification/SpecificationItem, повторно
            # 2026-08-30 через InvoiceItem): SpecificationItem всё
            # равно удаляются и пересоздаются при каждом формировании
            # (позиции могли измениться — калькуляции добавили/убрали/
            # поменяли), а у InvoiceItem есть FK specification_item_id
            # -> specificationitem.id (см. app/models/invoice_item.py —
            # намеренно ТОЛЬКО для трассировки, "снэпшот", НЕ для
            # live-обновления). Обнуляем эту ссылку у уже существующих
            # строк счёта ПЕРЕД удалением старых SpecificationItem —
            # сам InvoiceItem и его данные (цена/скидка/сумма) не
            # трогаем, только снимаем ссылку на исчезающую строку.
            # Specification/Invoice.specification_id при этом НЕ
            # трогаются вообще — счёт остаётся привязан к этой же
            # спецификации, просто трассировка до конкретной старой
            # строки прерывается.
            old_items = session.exec(
                select(SpecificationItem).where(SpecificationItem.specification_id == existing.id)
            ).all()
            old_item_ids = [item.id for item in old_items]
            if old_item_ids:
                orphaned_invoice_items = session.exec(
                    select(InvoiceItem).where(InvoiceItem.specification_item_id.in_(old_item_ids))
                ).all()
                for inv_item in orphaned_invoice_items:
                    inv_item.specification_item_id = None
                    session.add(inv_item)
                session.flush()

            for item in old_items:
                session.delete(item)
            session.flush()
        else:
            spec = Specification(
                request_id=instance.id,
                brand_slot=brand_slot,
                client_id=instance.client_id,
                document_number=next_document_number(session, "S"),
            )
            session.add(spec)
            session.flush()

        total_amount = 0.0
        for calc in calculations:
            line_total = (calc.final_total or 0.0) * (calc.quantity or 0.0)
            total_amount += line_total
            session.add(SpecificationItem(
                specification_id=spec.id,
                calculation_id=calc.id,
                product_name=calc.full_name,
                unit_price=calc.final_total,
                quantity=calc.quantity,
                line_total=line_total,
            ))

        spec.total_amount = total_amount
        session.add(spec)
        session.flush()

        # "Следующий документ тоже нужно обновить" (прямое указание
        # Вахтанга, 2026-08-30): если из ЭТОЙ спецификации уже собран
        # привязанный (specification_id ещё указывает сюда) Invoice —
        # обновляем и его сразу же, тем же кодом, что и ручная кнопка
        # «Обновить» на счёте, а не оставляем рассинхрон до следующего
        # захода человека на карточку счёта.
        linked_invoice = session.exec(
            select(Invoice).where(Invoice.specification_id == spec.id)
        ).first()
        if linked_invoice is not None:
            _sync_invoice_items_from_specification(linked_invoice, spec, session)
            _recalculate_invoice_totals(linked_invoice, session)

        session.commit()
        session.refresh(spec)

        return {"redirect_url": f"/specification-v2/{spec.id}"}

    return handler


request_table = TableConfig(
    key="request",
    model=Request,
    title="Заявки",
    title_singular="заявка",
    search_placeholder="Поиск по клиенту…",
    delete_mode="soft",
    enable_search_toggles=True,
    document_number_field="document_number",
    document_prefix="R",
    child_document_actions=["Создать документ на основании", "Показать подчинённые документы"],
    create_child_document_url="/calculation-v2",
    documents_chain_url="/documents-chain",
    own_page_url="/request-v2",
    default_sort_field="document_date",
    default_sort_dir="desc",
    action_handlers={
        # build_specification_1/2/3 (2026-08-27) — один обработчик на
        # слот (см. обоснование в _build_specification_handler выше:
        # action_handlers — плоский словарь по имени action, номер
        # слота зашит в самом имени). Подключены к кнопке
        # "Спецификация" через FieldConfig.row_action_names у
        # соответствующего brand_slot_N_id ниже. НЕ через
        # TableConfig.action_buttons — кнопка рендерится рядом с полем
        # (row_actions), не отдельным блоком под вкладкой формы, и
        # у request сейчас вообще нет вкладок формы (form_tabs пуст).
        "build_specification_1": _build_specification_handler(1),
        "build_specification_2": _build_specification_handler(2),
        "build_specification_3": _build_specification_handler(3),
    },
    fields=[
        FieldConfig(name="document_number", label="Номер", list_width="90px"),
        FieldConfig(name="document_date", label="Дата", widget="date", list_width="110px"),
        FieldConfig(name="client_id", label="Клиент (заказчик)", widget="select", required=True, list_width="22%"),
        FieldConfig(name="client_invoice_id", label="Клиент (для счёта)", widget="select", list_width="22%"),
        # in_list=False у брендовых слотов (v56, по решению Вахтанга) —
        # список заявок должен быть компактным (номер/дата/оба клиента),
        # бренд варианта — деталь формы, не нужна для быстрого обзора
        # журнала. in_form не трогаем (default True) — в форме видны
        # как прежде, вместе со своими row_actions.
        FieldConfig(name="brand_slot_1_id", label="Вариант 1 — бренд", widget="select", in_list=False,
                    row_actions=["Спецификация", "Пересчитать"],
                    row_action_names=["build_specification_1", None]),
        FieldConfig(name="brand_slot_2_id", label="Вариант 2 — бренд", widget="select", in_list=False,
                    row_actions=["Спецификация", "Пересчитать"],
                    row_action_names=["build_specification_2", None]),
        FieldConfig(name="brand_slot_3_id", label="Вариант 3 — бренд", widget="select", in_list=False,
                    row_actions=["Спецификация", "Пересчитать"],
                    row_action_names=["build_specification_3", None]),
        FieldConfig(name="note", label="Заметка", widget="textarea", in_list=False, placeholder="К чему относится эта заявка…"),
    ],
    relations=[
        Relation(field="client_id", target_table="client", display_field="short_name", label="Клиент (заказчик)",
                 show_filter_chips=False, searchable_fields=["short_name", "full_name"], search_default=True),
        Relation(field="client_invoice_id", target_table="client", display_field="short_name", label="Клиент (для счёта)",
                 show_filter_chips=False, searchable_fields=["short_name", "full_name"], search_default=False),
        Relation(field="brand_slot_1_id", target_table="brand", display_field="name", label="Вариант 1 — бренд",
                 show_filter_chips=False),
        Relation(field="brand_slot_2_id", target_table="brand", display_field="name", label="Вариант 2 — бренд",
                 show_filter_chips=False),
        Relation(field="brand_slot_3_id", target_table="brand", display_field="name", label="Вариант 3 — бренд",
                 show_filter_chips=False),
    ],
    form_rows=[
        FormRow(field_names=["document_number", "document_date"]),
    ],
    # Остальные поля не сгруппированы в form_rows намеренно — client_id/
    # client_invoice_id идут каждое отдельным рядом на всю ширину (клиенты
    # бывают с длинными названиями, в два столбца не помещались), брендовые
    # слоты тоже по одному в ряд, т.к. у каждого теперь своя пара кнопок
    # рядом (row_actions) — в общем ряду на троих было бы тесно.
)


def _recalc_full_name_handler(instance: Calculation, session) -> dict:
    """Серверная версия сборки full_name — НЕ используется напрямую
    кнопкой формы (см. ActionButton(client_side=True) в
    calculation_table ниже — с 2026-08-22 кнопка «Сформировать
    название» считает результат в браузере, см. CLIENT_ACTIONS.
    recalc_full_name в app/engine/page.py, чтобы работать и для ещё не
    сохранённой записи). Оставлен зарегистрированным в
    action_handlers на случай будущей серверной надобности (например
    массовый пересчёт нескольких записей сразу) — сам по себе
    достижим через POST /api/calculation/{id}/actions/recalc_full_name
    для уже сохранённой записи, просто кнопка UI туда больше не
    ходит."""
    from app.engine.name_template import build_full_name_for_calculation
    instance.full_name = build_full_name_for_calculation(session, instance)
    session.add(instance)
    session.commit()
    session.refresh(instance)
    return {"full_name": instance.full_name}


def _refresh_cost_totals_handler(instance: Calculation, session) -> dict:
    """Вызывается АВТОМАТИЧЕСКИ при открытии формы редактирования
    (openEdit() -> runAction() в page.py, по аналогии с
    brand_slot_labels ниже), а не по клику на кнопку "Пересчитать".

    В отличие от _recalc_material_prices_handler, здесь НЕ трогаются
    цены самих строк calculation_item (не ходим в справочник материалов) —
    только пересчитываются итоговые суммы вкладки "Стоимость" из уже
    сохранённых снэпшот-цен строк. Нужно, чтобы человек, открывший
    калькуляцию, сразу видел актуальную стоимость того, что реально
    сохранено в базе — без обязательного клика "Пересчитать" (решение
    Вахтанга 2026-08-27: "цифры по стоимости комплекта должны
    подтягиваться сразу"). "Пересчитать" остаётся отдельным действием
    ИМЕННО для синхронизации цен со справочником материалов — это два
    разных смысла, разведённых по разным обработчикам."""
    return _recalc_cost_totals(instance, session)


def _sync_final_total_before_save(instance: Calculation, session) -> None:
    """TableConfig.before_update_hook калькуляции (2026-08-27) — вызывается
    ВНУТРИ update_item (engine/api.py) сразу после применения полей из
    PUT-payload, до commit.

    final_total помечен readonly=True (человек не может прислать его
    напрямую через PUT — см. readonly_field_names в api.py), поэтому
    единственный способ поддерживать его синхронным с cost_method —
    пересчитать здесь же, СРАЗУ после того, как cost_method применён
    к instance из этого же payload.

    Нужно из-за клиентского CLIENT_ACTIONS.pick_final_total (page.py):
    переключение radio "Наценка"/"По часам" на форме мгновенно меняет
    editing.final_total на клиенте (без похода на сервер — иначе
    переключатель не давал бы видимого эффекта, ровно тот баг, который
    сообщил Вахтанг 2026-08-27), но САМО СОХРАНЕНИЕ (кнопка
    "Сохранить") идёт через обычный PUT, где final_total как readonly
    поле отбрасывается движком — без этого хука в базе осталось бы
    старое значение final_total, снова рассинхронизированное с
    cost_method сразу после сохранения (до следующего клика
    "Пересчитать").

    НЕ трогает materials_total/kits_total/base_total/insured_total/
    markup_total/hours_total — это была бы уже другая задача
    (актуализация цен из справочника), для неё есть отдельная кнопка
    "Пересчитать" (recalc_material_prices). Здесь только выбор ГОТОВОГО
    markup_total либо hours_total под актуальный cost_method — та же
    логика, что и в _recalc_cost_totals ниже, но без пересчёта самих
    сумм."""
    instance.final_total = (
        instance.hours_total if instance.cost_method == "hours" else instance.markup_total
    )


def _recalc_material_prices_handler(instance: Calculation, session) -> dict:
    """Кнопка "Пересчитать", показанная И на вкладке "Материалы", И на
    вкладке "Комплекты" (2026-08-23) — по прямой просьбе Вахтанга
    ЛЮБАЯ кнопка пересчёта внутри калькуляции пересчитывает калькуляцию
    ЦЕЛИКОМ, материалы и комплекты разом, не только позиции своей
    вкладки. Поэтому один обработчик, а не два отдельных под каждую
    вкладку.

    Для позиции-материала (material_id заполнен): переписывает
    price_excl_vat текущим Material.price_excl_vat из справочника.
    Материал, удалённый из справочника после того как попал в
    калькуляцию, — пропускается (позиция сохраняет прежнюю цену),
    не роняет весь пересчёт.

    Для позиции-комплекта (kit_id заполнен): price_excl_vat — это
    снэпшот СУММЫ СОСТАВА комплекта (Σ KitItem.quantity ×
    Material.price_excl_vat по живому составу kit_item на текущий
    момент), не цена самого комплекта (Kit ценового поля не имеет,
    см. app/models/kit.py). Комплект, у которого состав пуст или
    удалён из справочника, — сумма пересчитывается в 0, позиция не
    падает и не пропускается.

    Между двумя нажатиями цена в обеих категориях — "замороженный"
    снэпшот (см. обоснование в app/models/calculation_item.py), даже
    если материал/состав комплекта изменился за это время.

    С 2026-08-26 та же кнопка ЕЩЁ И пересчитывает вкладку "Стоимость"
    (см. _recalc_cost_totals ниже) — сначала обновляются цены строк
    (это), потом на их основе — итоговая стоимость изделия. Один
    обработчик на оба действия, по тому же принципу "одна кнопка
    пересчитывает калькуляцию целиком"."""
    from app.models.material import Material
    from app.models.kit_item import KitItem
    items = session.exec(
        select(CalculationItem).where(CalculationItem.calculation_id == instance.id)
    ).all()
    updated = 0
    for item in items:
        if item.material_id:
            material = session.get(Material, item.material_id)
            if not material:
                continue
            item.price_excl_vat = material.price_excl_vat
            session.add(item)
            updated += 1
        elif item.kit_id:
            kit_items = session.exec(
                select(KitItem).where(KitItem.kit_id == item.kit_id)
            ).all()
            kit_total = 0.0
            for kit_item in kit_items:
                material = session.get(Material, kit_item.material_id)
                if not material:
                    continue
                kit_total += material.price_excl_vat * kit_item.quantity
            item.price_excl_vat = round(kit_total, 2)
            session.add(item)
            updated += 1
    session.commit()
    session.refresh(instance)
    cost_fields = _recalc_cost_totals(instance, session)
    return {"recalculated": updated, **cost_fields}


def _recalc_cost_totals(instance: Calculation, session) -> dict:
    """Пересчёт вкладки "Стоимость" (2026-08-26) — вызывается ИЗ
    _recalc_material_prices_handler после того, как обновлены цены
    самих строк calculation_item, поэтому здесь просто суммирует уже
    актуальные price_excl_vat, не трогая справочники материалов сам.

    Порядок (согласовано с Вахтангом, см. подробный комментарий в
    app/models/calculation.py):
      materials_total  = Σ price_excl_vat по строкам с material_id
      kits_total       = Σ price_excl_vat по строкам с kit_id
      base_total       = materials_total + kits_total
      insured_total    = base_total * instance.insurance_markup
      markup_total     = insured_total * instance.markup_percent
      hours_total      = insured_total + assembly_hours * hourly_rate
                          (hourly_rate из ProductTypeRate,
                          product_type_rate_id может быть не задан —
                          тогда просто 0, не ошибка)
      final_total      = markup_total, если cost_method == "markup",
                          иначе hours_total

    Если у калькуляции вообще нет строк — все суммы получаются 0 без
    исключений (пустой список -> sum([]) == 0), это ожидаемое
    поведение, не invalid state (см. обсуждение с Вахтангом
    2026-08-26)."""
    from app.models.product_type_rate import ProductTypeRate

    items = session.exec(
        select(CalculationItem).where(CalculationItem.calculation_id == instance.id)
    ).all()
    # ВАЖНО: price_excl_vat строки — это цена/сумма за ОДНУ единицу
    # (для материала — цена за единицу материала, для комплекта — сумма
    # состава комплекта за один комплект, см. app/models/calculation_item.py),
    # а не сумма строки. Сумма строки = price_excl_vat × quantity, ТА ЖЕ
    # формула, что уже используется на вкладках "Материалы"/"Комплекты"
    # во фронте (materialsTotal/kitsTotal в page.py) и в списке позиций
    # (materials-row-sum). Раньше здесь суммировался голый price_excl_vat
    # без учёта quantity — при quantity > 1 "Материалы, итого"/"Комплекты,
    # итого" на вкладке "Стоимость" оказывались заметно меньше реальной
    # суммы строк (обнаружено Вахтангом на реальных данных 2026-08-27).
    materials_total = round(
        sum(item.price_excl_vat * item.quantity for item in items if item.material_id), 2
    )
    kits_total = round(
        sum(item.price_excl_vat * item.quantity for item in items if item.kit_id), 2
    )
    base_total = round(materials_total + kits_total, 2)
    insured_total = round(base_total * instance.insurance_markup, 2)
    markup_total = round(insured_total * instance.markup_percent, 2)

    hourly_rate = 0.0
    if instance.product_type_rate_id:
        rate = session.get(ProductTypeRate, instance.product_type_rate_id)
        if rate:
            hourly_rate = rate.hourly_rate
    hours_total = round(insured_total + instance.assembly_hours * hourly_rate, 2)

    final_total = markup_total if instance.cost_method == "markup" else hours_total

    instance.materials_total = materials_total
    instance.kits_total = kits_total
    instance.base_total = base_total
    instance.insured_total = insured_total
    instance.markup_total = markup_total
    instance.hours_total = hours_total
    instance.final_total = final_total
    session.add(instance)
    session.commit()
    session.refresh(instance)

    return {
        "materials_total": instance.materials_total,
        "kits_total": instance.kits_total,
        "base_total": instance.base_total,
        "insured_total": instance.insured_total,
        "markup_total": instance.markup_total,
        "hours_total": instance.hours_total,
        "final_total": instance.final_total,
    }


def _brand_slot_labels_handler(instance: Calculation, session) -> dict:
    """Обработчик, вызываемый ПРИ ОТКРЫТИИ формы редактирования
    (openEdit() -> runAction() в page.py), а не по клику на кнопку —
    подтягивает реальные названия трёх брендов из СВЯЗАННОЙ заявки
    (Request.brand_slot_1/2/3_id), чтобы радиокнопки "Вариант (слот
    бренда)" показывали не голые цифры 1/2/3, а название бренда
    каждого варианта (решение Вахтанга 2026-08-21: калькуляция всегда
    создаётся на основании заявки, значит данные уже доступны).
    Возвращает {"1": "...", "2": "...", "3": "..."} — только для
    слотов, где бренд в заявке реально выбран; отсутствующий ключ
    даёт статичный fallback-label из FieldConfig.options на фронте
    (см. radio_labels_field). Пустой словарь, если заявка не привязана
    (request_id пуст) или бренд ни в одном слоте не выбран."""
    from app.models.request import Request
    from app.models.brand import Brand
    labels: dict[str, str] = {}
    if instance.request_id:
        req = session.get(Request, instance.request_id)
        if req:
            for slot, brand_id in (
                (1, req.brand_slot_1_id),
                (2, req.brand_slot_2_id),
                (3, req.brand_slot_3_id),
            ):
                if brand_id:
                    brand = session.get(Brand, brand_id)
                    if brand:
                        labels[str(slot)] = brand.name
    return {"brand_slot_labels": labels}


# Калькуляция (calculation) — второй документ цепочки zayavka ->
# calculation -> specification -> invoice. Этот шаг — только "шапка"
# документа, без состава (calculation_item — следующий шаг). См.
# подробный комментарий в app/models/calculation.py.
#
# form_tabs=["Основное", "Настройки"] — первая таблица движка с
# вкладками формы (см. TableConfig.form_tabs в config.py, введено
# специально под эту потребность, но переиспользуемо для любой
# будущей таблицы). На "Настройки" — только name_template и кнопка
# "Пересчитать название" на этом шаге; сюда же позже лягут настройки
# формулы расчёта стоимости (см. HANDOFF).
#
# full_name НЕ пересчитывается автоматически при сохранении формы —
# только по кнопке (решение Вахтанга 2026-08-21: не терять руками
# поправленное название при каждом save). full_name остаётся обычным
# редактируемым текстовым полем (не readonly) — можно поправить
# результат подстановки точечно, не трогая сам шаблон.


def _default_calculation_unit_id(data: dict, session) -> dict:
    """before_create_hook калькуляции (2026-08-31): если unit_id не
    передан явно при создании — подставляет id записи Unit с
    name=DEFAULT_CALCULATION_UNIT_NAME ("послуга"), см. комментарий
    у DEFAULT_CALCULATION_UNIT_NAME в app/models/calculation.py.
    Если такой записи в справочнике ещё нет (свежая БД без ручного
    заполнения справочника Unit) — молча оставляет unit_id пустым,
    ничего не падает, поле просто редактируется вручную."""
    if not data.get("unit_id"):
        default_unit = session.exec(
            select(Unit).where(Unit.name == DEFAULT_CALCULATION_UNIT_NAME)
        ).first()
        if default_unit:
            data["unit_id"] = default_unit.id
    return data


calculation_table = TableConfig(
    key="calculation",
    model=Calculation,
    title="Калькуляции",
    title_singular="калькуляция",
    search_placeholder="Поиск по названию…",
    delete_mode="soft",
    document_number_field="document_number",
    own_page_url="/calculation-v2",
    document_prefix="K",
    default_sort_fields=[("document_date", "desc"), ("document_time", "desc")],
    form_tabs=["Основное", "Настройки", "Материалы", "Комплекты", "Стоимость"],
    needs_constants=True,
    extra_lookups=["brand"],
    materials_tab="Материалы",
    materials_item_table_key="calculation_item",
    materials_recalc_action="recalc_material_prices",
    kits_tab="Комплекты",
    kits_item_table_key="calculation_item",
    open_edit_action="refresh_cost_totals",
    before_update_hook=_sync_final_total_before_save,
    before_create_hook=_default_calculation_unit_id,
    action_buttons=[
        ActionButton(action="recalc_full_name", label="Сформировать название", tab="Основное",
                     client_side=True),
        # brand_slot_labels — НЕ показывается как кнопка (нет ActionButton
        # с этим action в списке выше нарочно): вызывается автоматически
        # при открытии формы (см. openEdit() в page.py), а не по клику
        # человека. Регистрация только в action_handlers ниже достаточна
        # для работы POST /api/calculation/{id}/actions/brand_slot_labels.
        # recalc_material_prices — тоже НЕ через ActionButton (кнопка
        # рендерится отдельно самим виджетом вкладки "Материалы", не
        # универсальным render_action_buttons) — регистрации в
        # action_handlers ниже достаточно для работы
        # POST /api/calculation/{id}/actions/recalc_material_prices.
    ],
    action_handlers={
        "recalc_full_name": _recalc_full_name_handler,
        "brand_slot_labels": _brand_slot_labels_handler,
        "recalc_material_prices": _recalc_material_prices_handler,
        # refresh_cost_totals — НЕ через ActionButton (нет собственной
        # кнопки, вызывается автоматически при открытии формы, см.
        # openEdit() в page.py, по аналогии с brand_slot_labels выше) —
        # регистрации здесь достаточно для работы
        # POST /api/calculation/{id}/actions/refresh_cost_totals.
        "refresh_cost_totals": _refresh_cost_totals_handler,
    },
    fields=[
        FieldConfig(name="document_number", label="Номер", list_width="90px", tab="Основное",
                    form_width="120px"),
        FieldConfig(name="document_date", label="Дата", widget="date", list_width="110px", tab="Основное",
                    form_width="140px"),
        FieldConfig(name="document_time", label="Время", widget="time", list_width="90px", tab="Основное",
                    form_width="110px"),
        FieldConfig(name="request_id", label="Заявка", widget="select", list_width="18%", tab="Основное",
                    form_width="140px", on_change_action="brand_slot_labels"),
        FieldConfig(name="client_name", label="Рабочее название", required=True, searchable=True,
                    search_default=True, list_width="22%", tab="Основное"),
        # quantity (2026-08-27) — количество ИЗДЕЛИЙ этого типа, нужно
        # спецификации (см. подробный комментарий в
        # app/models/calculation.py) — сама вкладка "Стоимость"
        # по-прежнему считает цену ОДНОГО изделия, это поле её не
        # трогает. Рядом с "Рабочее название" по прямой просьбе
        # Вахтанга ("нужно сделать её это поле количество на первой
        # вкладке возле поля где мы вводим рабочее название").
        FieldConfig(name="quantity", label="Количество изделий", widget="number",
                    is_numeric=True, list_width="90px", form_width="120px", tab="Основное",
                    default=1),
        FieldConfig(name="full_name", label="Полное название", in_list=False, tab="Основное",
                    inline_action="recalc_full_name"),
        # unit_id (2026-08-31) — единица измерения ИЗДЕЛИЯ целиком (см.
        # подробный комментарий у DEFAULT_CALCULATION_UNIT_NAME в
        # app/models/calculation.py). По умолчанию подставляется
        # "послуга" через before_create_hook=_default_calculation_unit_id
        # выше. Рядом с "Полное название" по просьбе Вахтанга
        # ("нужно добавить отдельное поле возле наименования").
        FieldConfig(name="unit_id", label="Ед. измерения", widget="select",
                    in_list=False, tab="Основное"),
        FieldConfig(name="brand_slot", label="Вариант (слот бренда)", widget="radio",
                    list_width="90px", tab="Основное",
                    radio_labels_field="brand_slot_labels", radio_labels_action="brand_slot_labels",
                    options=[("1", "Вариант 1"), ("2", "Вариант 2"), ("3", "Вариант 3")]),
        FieldConfig(name="status", label="Статус", widget="select", list_width="46px", tab="Основное",
                    list_as_dot=True,
                    # 2026-08-27: статус "draft" (черновик) и
                    # "archived_pending" (к архивации) УБРАНЫ из
                    # вариантов по решению Вахтанга — черновик как
                    # промежуточное состояние оказался не нужен
                    # (сохранил — значит сразу активна), а архив будет
                    # сделан отдельно позже, когда до него дойдёт
                    # очередь по дорожной карте. in_form теперь True
                    # (было False) — статус стал видимым и РУЧНЫМ полем
                    # выбора на форме, а не только точкой-индикатором в
                    # списке: раньше сменить статус можно было только
                    # через код/дефолт, теперь Вахтанг сам ставит
                    # "Активна"/"К удалению" вручную.
                    options=[
                        ("active", "Активна"),
                        ("delete_pending", "К удалению"),
                    ],
                    dot_colors={
                        "active": "#3f7d4f",
                        "delete_pending": "#9c3b2e",
                    }),
        FieldConfig(name="name_template", label="Шаблон полного названия", widget="textarea",
                    in_list=False, tab="Настройки", default=DEFAULT_NAME_TEMPLATE,
                    default_from_constant="calculation_name_template",
                    placeholder="Сборка {client_name}",
                    hint="Доступные вставки: {client_name} — рабочее название, "
                         "{brand_slot} — номер варианта (1/2/3), {request_number} — "
                         "номер связанной заявки. Например: Сборка {client_name}"),

        # --- Вкладка "Стоимость" (2026-08-26) --- см. подробный
        # комментарий порядка расчёта в app/models/calculation.py и в
        # _recalc_cost_totals (app/engine/tables.py). Пересчёт — той
        # же кнопкой "Пересчитать", что и на вкладке "Материалы"
        # (materials_recalc_action="recalc_material_prices" ниже).
        FieldConfig(name="materials_total", label="Материалы, итого", widget="number",
                    is_numeric=True, in_list=False, tab="Стоимость", readonly=True),
        FieldConfig(name="kits_total", label="Комплекты, итого", widget="number",
                    is_numeric=True, in_list=False, tab="Стоимость", readonly=True),
        FieldConfig(name="base_total", label="База (материалы + комплекты)", widget="number",
                    is_numeric=True, in_list=False, tab="Стоимость", readonly=True),
        FieldConfig(name="insurance_markup", label="Страховочная наценка", widget="number",
                    is_numeric=True, in_list=False, tab="Стоимость", default=1.1,
                    default_from_constant="insurance_markup",
                    hint="Применяется к обоим способам расчёта: база умножается на "
                         "эту наценку до дальнейшего расчёта. Можно поправить вручную "
                         "для конкретной калькуляции — дефолт берётся из справочника "
                         "констант и на уже созданные калькуляции не влияет."),
        FieldConfig(name="insured_total", label="База со страховкой", widget="number",
                    is_numeric=True, in_list=False, tab="Стоимость", readonly=True),
        FieldConfig(name="markup_percent", label="Процент надбавки", widget="number",
                    is_numeric=True, in_list=False, tab="Стоимость", default=1.4,
                    default_from_constant="markup_percent",
                    hint="Способ \"Наценка\": база со страховкой умножается на эту "
                         "величину. Можно поправить вручную для конкретной калькуляции."),
        FieldConfig(name="markup_total", label="Сумма (способ \"Наценка\")", widget="number",
                    is_numeric=True, in_list=False, tab="Стоимость", readonly=True),
        FieldConfig(name="assembly_hours", label="Часы на сборку", widget="number",
                    is_numeric=True, in_list=False, tab="Стоимость", default=0,
                    hint="Способ \"По часам\": количество часов, умножается на "
                         "стоимость часа выбранного ниже типа изделия."),
        FieldConfig(name="product_type_rate_id", label="Тип изделия (стоимость часа)",
                    widget="select", is_numeric=False, in_list=False, tab="Стоимость",
                    default_first_option=True),
        FieldConfig(name="hours_total", label="Сумма (способ \"По часам\")", widget="number",
                    is_numeric=True, in_list=False, tab="Стоимость", readonly=True),
        FieldConfig(name="cost_method", label="Способ расчёта стоимости", widget="radio",
                    in_list=False, tab="Стоимость", default="markup",
                    options=[("markup", "Наценка"), ("hours", "По часам")],
                    on_change_action="pick_final_total"),
        FieldConfig(name="final_total", label="Итоговая стоимость", widget="number",
                    is_numeric=True, in_list=False, tab="Стоимость", readonly=True),
    ],
    relations=[
        Relation(field="request_id", target_table="request", display_field="document_number", label="Заявка",
                 show_filter_chips=False),
        Relation(field="product_type_rate_id", target_table="product_type_rate", display_field="name",
                 label="Тип изделия", show_filter_chips=False),
        Relation(field="unit_id", target_table="unit", display_field="name",
                 label="Ед. измерения", show_filter_chips=False),
    ],
    form_rows=[
        FormRow(field_names=["document_number", "document_date", "document_time"]),
        FormRow(field_names=["client_name", "quantity", "status"]),
        FormRow(field_names=["full_name", "unit_id"]),
        FormRow(field_names=["materials_total", "kits_total", "base_total"]),
        FormRow(field_names=["insurance_markup", "insured_total"]),
        FormRow(field_names=["markup_percent", "markup_total"]),
        FormRow(field_names=["assembly_hours", "product_type_rate_id", "hours_total"]),
    ],
)


material_table = TableConfig(
    key="material",
    model=Material,
    title="Материалы",
    title_singular="материал",
    search_placeholder="Поиск по названию или артикулу…",
    enable_search_toggles=True,
    delete_mode="soft",
    fields=[
        FieldConfig(name="short_name", label="Short name", required=True,
                    placeholder="ABB S203 C16", searchable=True, search_default=True, list_width="22%"),
        FieldConfig(name="full_name", label="Full name", required=True,
                    placeholder="Автоматический выключатель 3P C16 6kA", searchable=True, search_default=False, list_width="22%"),
        FieldConfig(name="brand_id", label="Бренд", widget="select"),
        FieldConfig(name="unit_id", label="Ед. измерения", widget="select",
                    required=True, list_width="90px"),
        FieldConfig(name="sku_article", label="Артикул производителя",
                    placeholder="2CDS253001R0164", searchable=True, search_default=False, list_width="110px"),
        FieldConfig(name="price_excl_vat", label="Цена без НДС", widget="number",
                    is_numeric=True, list_width="100px"),
        FieldConfig(name="price_incl_vat", label="Цена с НДС", widget="number",
                    is_numeric=True, list_width="100px"),
        FieldConfig(name="price_vb_incl_vat", label="Цена с НДС ВБ", widget="number",
                    is_numeric=True, in_list=False),
        # in_form=False: ставка НДС больше не отдельное поле формы —
        # с v34 её значение показывается прямо в лейбле "Цена с НДС"
        # (см. price-pair-label в page.py, читает constants.vat_rate
        # напрямую). Поле остаётся virtual/source_constant_key, чтобы
        # ComputedPair.rate_constant_key="vat_rate" продолжал работать
        # без изменений — оно просто больше не рендерится как input.
        FieldConfig(name="vat_rate", label="Ставка НДС", list_width="60px",
                    virtual=True, source_constant_key="vat_rate", in_form=False),
    ],
    computed_pairs=[
        ComputedPair(
            field_a="price_excl_vat",
            field_b="price_incl_vat",
            rate_field="vat_rate",
            rate_constant_key="vat_rate",
            formula="vat",
            label_a="Цена без НДС",
            label_b="Цена с НДС",
            label_rate="Ставка НДС",
        ),
    ],
    relations=[
        Relation(field="brand_id", target_table="brand", display_field="name", label="Бренд"),
        Relation(field="unit_id", target_table="unit", display_field="name", label="Ед. измерения"),
    ],
    form_rows=[
        FormRow(field_names=["brand_id", "unit_id", "sku_article"]),
        FormRow(field_names=["price_excl_vat", "price_incl_vat", "price_vb_incl_vat"]),
    ],
)


# kit_group / kit_section — верхние два уровня дерева drill-down
# комплектов (kit_group -> kit_section -> kit). Раньше (v36/v37) это
# были обычные плоские таблицы движка с фильтром-чипом по группе —
# временный воркэраунд, теперь заменён на настоящий drill-down с
# "простым" удалением (физическое, но только если нет детей).
# kit_group_id остаётся обычным полем модели/FK — используется здесь
# как hierarchy.parent_field, отдельного relation/select в форме
# больше не нужно (группа выбирается переходом по дереву, не в форме).
kit_group_table = TableConfig(
    key="kit_group",
    model=KitGroup,
    title="Группы комплектов",
    title_singular="группа комплектов",
    search_placeholder="Поиск по названию…",
    delete_mode="simple",
    hierarchy=Hierarchy(child_key="kit_section", root_label="Группы"),
    fields=[
        FieldConfig(name="name", label="Название", required=True, searchable=True),
        FieldConfig(name="sort_order", label="Порядок", widget="number",
                    is_numeric=True, list_width="100px", default=0, in_list=False),
    ],
)


kit_section_table = TableConfig(
    key="kit_section",
    model=KitSection,
    title="Подразделы комплектов",
    title_singular="подраздел комплектов",
    search_placeholder="Поиск по названию…",
    delete_mode="simple",
    hierarchy=Hierarchy(parent_field="kit_group_id", parent_key="kit_group", child_key="kit"),
    fields=[
        FieldConfig(name="name", label="Название", required=True, searchable=True),
        FieldConfig(name="kit_group_id", label="Группа", widget="select", required=True, in_list=False, in_form=False),
        FieldConfig(name="sort_order", label="Порядок", widget="number",
                    is_numeric=True, list_width="100px", default=0, in_list=False),
    ],
)


# kit — 3-й, нижний уровень дерева drill-down (kit_group -> kit_section
# -> kit). До этого шага (v39/v39.1) был временной плоской таблицей
# старого движка — теперь подключён к дереву. hierarchy БЕЗ child_key
# (это последний уровень — заходить вглубь больше некуда, kit_items
# не отдельный уровень дерева, а СОСТАВ, показывается внутри модалки
# этого узла, см. edit_mode ниже).
#
# edit_mode="items_modal" (см. app/engine/config.py и page.py): вместо
# обычной формы редактирования (название+поля) модалка показывает
# состав комплекта (список KitItem — материал + количество) и кнопку
# "Редактировать". Клик по ней открывает MaterialPicker — отдельный
# полноэкранный экран (bottom sheet: "Отобрано" + поиск материалов),
# где человек правит черновик состава (добавляет/меняет количество/
# удаляет), а финальное сохранение полностью заменяет состав на
# сервере (PUT /api/kit/{id}/items, см. app/engine/api.py). Дубликаты
# material_id в составе допустимы. Переименование самого комплекта —
# отдельная иконка ✎ в drill-list (не через эту модалку).
kit_table = TableConfig(
    key="kit",
    model=Kit,
    title="Комплекты",
    title_singular="комплект",
    search_placeholder="Поиск по названию…",
    delete_mode="soft",
    edit_mode="items_modal",
    items_source_table_key="kit_item",
    hierarchy=Hierarchy(parent_field="kit_section_id", parent_key="kit_section"),
    fields=[
        FieldConfig(name="name", label="Название", required=True, searchable=True),
        FieldConfig(name="kit_section_id", label="Раздел", widget="select", required=True, in_list=False, in_form=False),
        FieldConfig(name="sort_order", label="Порядок", widget="number",
                    is_numeric=True, list_width="100px", default=0, in_list=False),
    ],
)


# kit_item — состав комплектов (материал + количество). НЕ отдельный
# уровень дерева (kit.hierarchy не указывает на него через child_key —
# он последний уровень) — но hierarchy здесь всё равно нужен, ЧИСТО
# ради parent_field: это даёт GET /api/kit_item?parent_id={kit_id}
# бесплатно через уже существующий универсальный механизм движка
# (см. app/engine/api.py list_items, реализовано в v38 для дерева
# групп/разделов) — используется модалкой состава (edit_mode=
# "items_modal" у kit) для загрузки строк текущего комплекта, а не
# как самостоятельная страница списка (страница /kit_item-v2 и пункт
# меню убраны в этой сессии — состав теперь виден только изнутри
# модалки конкретного комплекта).
kit_item_table = TableConfig(
    key="kit_item",
    model=KitItem,
    title="Состав комплекта",
    title_singular="позиция состава",
    search_placeholder="Поиск…",
    hierarchy=Hierarchy(parent_field="kit_id", parent_key="kit"),
    # delete_mode не указан -> дефолт "hard": на KitItem ничего не
    # ссылается (см. обоснование в app/models/kit_item.py), удаление
    # позиции состава всегда безусловное и немедленное, без пометки.
    fields=[
        FieldConfig(name="kit_id", label="Комплект", widget="select", required=True, in_list=False, in_form=False),
        FieldConfig(name="material_id", label="Материал", widget="select", required=True),
        FieldConfig(name="quantity", label="Количество", widget="number",
                    is_numeric=True, list_width="100px", default=1, form_width="110px"),
    ],
    relations=[
        Relation(field="kit_id", target_table="kit", display_field="name", label="Комплект"),
        Relation(field="material_id", target_table="material", display_field="short_name", label="Материал"),
    ],
)


# calculation_item — позиции материалов калькуляции (вкладка
# "Материалы" формы calculation). hierarchy здесь, как и у kit_item,
# ЧИСТО ради parent_field: даёт GET /api/calculation_item?parent_id=
# {calculation_id} бесплатно через универсальный механизм движка.
# Не отдельная страница списка/пункт меню — виден только внутри
# вкладки "Материалы" конкретной калькуляции (см. TableConfig.
# materials_tab у calculation_table и виджет в page.py).
#
# Отличие от kit_item — есть своё поле price_excl_vat (СНЭПШОТ, не
# живая ссылка на material.price_excl_vat, см. подробное обоснование
# в app/models/calculation_item.py) — движок читает и пишет его как
# обычное поле формы движка (in_form/in_list), хотя сама форма
# добавления позиции здесь не используется движком напрямую (виджон
# вкладки "Материалы" — специальный код, не универсальная модалка) —
# TableConfig всё равно нужен целиком, т.к. отсюда берутся relations
# (material_id -> short_name) и field_names() для API-эндпоинтов.
calculation_item_table = TableConfig(
    key="calculation_item",
    model=CalculationItem,
    title="Материалы калькуляции",
    title_singular="позиция материала",
    search_placeholder="Поиск…",
    hierarchy=Hierarchy(parent_field="calculation_id", parent_key="calculation"),
    # delete_mode не указан -> дефолт "hard": ничто не ссылается на
    # конкретный CalculationItem напрямую (см. обоснование в модели),
    # удаление позиции — всегда безусловное физическое удаление сразу.
    fields=[
        FieldConfig(name="calculation_id", label="Калькуляция", widget="select", required=True,
                    in_list=False, in_form=False),
        FieldConfig(name="material_id", label="Материал", widget="select"),
        # kit_id (2026-08-23, вкладка "Комплекты") — НЕ required=True, в
        # отличие от material_id: строка заполняет РОВНО одно из двух
        # полей (см. обоснование в app/models/calculation_item.py), делать
        # оба обязательными на уровне движка сломало бы создание строк
        # другого типа. Разделение material_id vs kit_id IS NOT NULL —
        # только на фронте (см. materialsTab/kitsTab виджеты в page.py).
        FieldConfig(name="kit_id", label="Комплект", widget="select"),
        FieldConfig(name="quantity", label="Количество", widget="number",
                    is_numeric=True, list_width="100px", default=1, form_width="110px"),
        FieldConfig(name="price_excl_vat", label="Цена без НДС", widget="number",
                    is_numeric=True, list_width="120px", default=0, form_width="120px"),
    ],
    relations=[
        Relation(field="calculation_id", target_table="calculation", display_field="full_name", label="Калькуляция"),
        Relation(field="material_id", target_table="material", display_field="short_name", label="Материал"),
        Relation(field="kit_id", target_table="kit", display_field="name", label="Комплект"),
    ],
)


# Спецификация (specification) — третий документ цепочки zayavka ->
# calculation -> specification -> invoice. Формируется НЕ через
# обычную кнопку "+ Добавить" (allow_create=False — создание идёт
# ТОЛЬКО через кнопку "Спецификация" у нужного брендового слота
# заявки, см. _build_specification_handler/request_table выше),
# редактирование строк тоже недоступно человеку напрямую
# (allow_delete=False — вся запись целиком удаляется и создаётся
# заново кнопкой "Спецификация", отдельное ручное удаление
# бессмысленно и могло бы рассинхронизировать total_amount).
# Единственное действие человека над уже созданной спецификацией в
# этом шаге — просмотр (список -> клик по строке -> карточка с
# шапкой; сами позиции — см. specification_item_table ниже, отдельный
# список, отфильтрованный по specification_id).
#
# own_page_url — та же логика, что у request/calculation: кнопка
# "Спецификация" делает redirect на "/specification-v2/{id}" (см.
# _build_specification_handler), открывая карточку сразу.
# Счёт (invoice) — четвёртый документ цепочки zayavka -> calculation
# -> specification -> invoice (обсуждение 2026-08-29, см. подробный
# комментарий механики в app/models/invoice.py). Кнопка "Создать
# счёт" живёт на СПЕЦИФИКАЦИИ (не на заявке — в отличие от
# "Спецификация" у request), потому что счёт создаётся ИЗ конкретной
# уже сформированной спецификации, а не из заявки напрямую.
#
# Механика (согласовано с Вахтангом 2026-08-29):
#   1. Ищем уже существующий Invoice с specification_id == этой
#      спецификации (ещё НЕ отвязанный от неё). Если нашли — это
#      "Обновить": перечитываем позиции заново (см.
#      _sync_invoice_items_from_specification ниже), шапку не
#      трогаем (firm_id/client_invoice_id и т.д. остаются как
#      человек их поправил).
#   2. Не нашли (либо потому что счёта ещё не было, либо потому что
#      единственный существовавший счёт уже ОТВЯЗАН — specification_id
#      сброшен в NULL) — создаём НОВЫЙ Invoice: request_id из
#      спецификации, client_id/client_invoice_id — снэпшот из Request
#      (client_invoice_id пуст -> берём client_id, "плательщик по
#      умолчанию = заказчик"), firm_id — дефолтная Firm
#      (is_default=True), номер по счётчику префикса "I".
#   3. В обоих случаях — построчная синхронизация позиций из
#      SpecificationItem (см. _sync_invoice_items_from_specification):
#      полная перезапись (delete-all+create-all), discount_percent
#      каждой НОВОЙ строки = 0 (Вахтанг: "новая строка без скидки"),
#      т.к. пересоздание строк не может сохранить прежние построчные
#      скидки один-в-один при простом delete-all — это ожидаемое
#      поведение только для явного повторного нажатия "Обновить" на
#      ещё привязанном счёте (человек видит, что произошло, и может
#      заново применить скидку кнопкой "Дать скидку").
#   4. Пересчитываем итоги шапки (см. _recalculate_invoice_totals).
#
# НЕ пересчитывает саму спецификацию/калькуляции перед сборкой —
# берёт SpecificationItem как есть на момент нажатия (тот же принцип,
# что у _build_specification_handler).
#
# Каскад (добавлено 2026-08-30, прямое указание Вахтанга: "следующий
# документ тоже надо обновить"): с тех пор как спецификация
# обновляется НА МЕСТЕ (id/номер не меняются, см.
# _build_specification_handler), при каждом повторном формировании
# спецификации ЭТИ ЖЕ ДВЕ ФУНКЦИИ (_sync_invoice_items_from_
# specification + _recalculate_invoice_totals) вызываются автоматически
# для уже привязанного к ней Invoice — человеку не нужно отдельно
# заходить на карточку счёта и жать «Обновить» после пересборки
# спецификации.
def _sync_invoice_items_from_specification(invoice: Invoice, spec: Specification, session) -> None:
    """Полная перезапись InvoiceItem по текущим SpecificationItem —
    используется и при первом создании счёта, и при "Обновить" на
    ещё привязанном счёте. delete-all+create-all — та же логика, что
    у _build_specification_handler при повторном формировании
    спецификации (см. комментарий там про два раздельных flush(),
    чтобы не словить ForeignKeyViolation на Postgres)."""
    old_items = session.exec(
        select(InvoiceItem).where(InvoiceItem.invoice_id == invoice.id)
    ).all()
    for item in old_items:
        session.delete(item)
    session.flush()

    spec_items = session.exec(
        select(SpecificationItem).where(SpecificationItem.specification_id == spec.id)
    ).all()
    for spec_item in spec_items:
        session.add(InvoiceItem(
            invoice_id=invoice.id,
            specification_item_id=spec_item.id,
            product_name=spec_item.product_name,
            quantity=spec_item.quantity,
            unit_price=spec_item.unit_price,
            discount_percent=0.0,
            unit_price_after_discount=spec_item.unit_price,
            line_total=spec_item.unit_price * spec_item.quantity,
        ))
    session.flush()


def _recalculate_invoice_totals(invoice: Invoice, session) -> None:
    """Пересчитывает total_excl_vat/vat_amount/total_incl_vat по
    текущим InvoiceItem.line_total (уже с учётом построчной скидки —
    см. app/models/invoice_item.py) и ставке НДС из справочника
    constants (тот же constants['vat_rate'], что использует
    material/calculation — единая ставка на весь проект, не своя на
    документ)."""
    items = session.exec(
        select(InvoiceItem).where(InvoiceItem.invoice_id == invoice.id)
    ).all()
    total_excl_vat = sum((item.line_total or 0.0) for item in items)

    vat_rate_row = session.exec(select(Constant).where(Constant.key == "vat_rate")).first()
    try:
        vat_rate = float(vat_rate_row.value) if vat_rate_row else 20.0
    except (TypeError, ValueError):
        vat_rate = 20.0

    vat_amount = total_excl_vat * vat_rate / 100.0
    invoice.total_excl_vat = round(total_excl_vat, 2)
    invoice.vat_amount = round(vat_amount, 2)
    invoice.total_incl_vat = round(total_excl_vat + vat_amount, 2)
    session.add(invoice)


def _build_invoice_handler(instance: Specification, session) -> dict:
    """Обработчик кнопки «Создать счёт» на спецификации (см.
    обоснование механики выше). instance здесь — Specification (не
    Request), т.к. кнопка зарегистрирована в action_handlers
    specification_table, не request_table."""
    from app.engine.document_numbering import next_document_number

    request = session.get(Request, instance.request_id)

    existing = session.exec(
        select(Invoice).where(Invoice.specification_id == instance.id)
    ).first()

    if existing is not None:
        invoice = existing
        # (2026-08-30) — если у уже существующего счёта firm_id пуст
        # (например, счёт создавался ДО того, как в справочнике
        # появилась хоть одна фирма/фирма с is_default=True), при
        # каждом повторном "обновлении на месте" пробуем подставить
        # дефолтную фирму заново — человек не должен обязательно лезть
        # в форму счёта вручную только потому, что фирму завели уже
        # ПОСЛЕ первого создания счёта. Если firm_id уже заполнен
        # (человек либо оставил дефолтный выбор, либо поменял вручную)
        # — НЕ трогаем, это уже осознанный выбор на конкретном
        # документе, а не пустое место.
        if not invoice.firm_id:
            firm = session.exec(select(Firm).where(Firm.is_default == True)).first()  # noqa: E712
            if firm:
                invoice.firm_id = firm.id
                session.add(invoice)
    else:
        client_invoice_id = (request.client_invoice_id if request else None) or (
            request.client_id if request else None
        )
        firm = session.exec(select(Firm).where(Firm.is_default == True)).first()  # noqa: E712
        invoice = Invoice(
            request_id=instance.request_id,
            specification_id=instance.id,
            firm_id=firm.id if firm else None,
            client_id=request.client_id if request else None,
            client_invoice_id=client_invoice_id,
            document_number=next_document_number(session, "I"),
        )
        session.add(invoice)
        session.flush()

    _sync_invoice_items_from_specification(invoice, instance, session)
    _recalculate_invoice_totals(invoice, session)
    session.commit()
    session.refresh(invoice)

    return {"redirect_url": f"/invoice-v2/{invoice.id}"}


def _unlink_invoice_handler(instance: Invoice, session) -> dict:
    """Кнопка «Отвязать» на счёте (2026-08-29) — сбрасывает ТОЛЬКО
    specification_id в NULL, request_id и все позиции/поля счёта
    остаются как есть (решение Вахтанга: "счёт остаётся как есть,
    всё редактируется, просто мы не обновляем его"). После этого
    повторное «Создать счёт» с ТОЙ ЖЕ спецификации ищет Invoice с
    specification_id == этой спецификации, не находит (он уже NULL)
    и создаёт НОВЫЙ документ — см. _build_invoice_handler выше."""
    instance.specification_id = None
    session.add(instance)
    session.commit()
    session.refresh(instance)
    return {"specification_id": None}


def _refresh_invoice_items_handler(instance: Invoice, session) -> dict:
    """Кнопка «Обновить» на счёте, пока он ЕЩЁ привязан к
    спецификации (specification_id заполнен) — перечитывает позиции
    заново (см. _sync_invoice_items_from_specification), скидки
    построчно сбрасываются в 0 (та же оговорка, что в комментарии
    у _build_invoice_handler). Если specification_id уже NULL
    (счёт отвязан) — ничего не делает, кнопка на фронте в этом
    состоянии должна быть скрыта/неактивна, но обработчик всё равно
    защищается на случай прямого вызова API."""
    if not instance.specification_id:
        return {}
    spec = session.get(Specification, instance.specification_id)
    if not spec:
        return {}
    _sync_invoice_items_from_specification(instance, spec, session)
    _recalculate_invoice_totals(instance, session)
    session.commit()
    session.refresh(instance)
    return {
        "total_excl_vat": instance.total_excl_vat,
        "vat_amount": instance.vat_amount,
        "total_incl_vat": instance.total_incl_vat,
    }


def _apply_bulk_discount_handler(instance: Invoice, session, payload: dict) -> dict:
    """Обработчик кнопки «Дать скидку» (2026-08-29) — ЕДИНСТВЕННЫЙ
    action_handler во всём проекте, принимающий payload от человека
    (см. обоснование в TableConfig.invoice_items_bulk_discount_action
    и роут run_action в engine/api.py). payload = {"discount_percent":
    число}, введённое через window.prompt() на фронте.

    Перезаписывает discount_percent ВСЕХ строк счёта одинаковым
    значением, ВКЛЮЧАЯ те, где уже стояло своё построчное значение
    (прямое решение Вахтанга 2026-08-29: "модалка перезаписывает все
    строчные значения одинаково") — не пропускает уже изменённые
    вручную строки."""
    try:
        discount_percent = float(payload.get("discount_percent"))
    except (TypeError, ValueError):
        raise HTTPException(status_code=422, detail="Скидка должна быть числом (например -10 или 5).")

    items = session.exec(
        select(InvoiceItem).where(InvoiceItem.invoice_id == instance.id)
    ).all()
    for item in items:
        item.discount_percent = discount_percent
        item.unit_price_after_discount = round(item.unit_price * (1 + discount_percent / 100.0), 2)
        item.line_total = round(item.unit_price_after_discount * item.quantity, 2)
        session.add(item)
    session.flush()

    _recalculate_invoice_totals(instance, session)
    session.commit()
    session.refresh(instance)
    return {
        "total_excl_vat": instance.total_excl_vat,
        "vat_amount": instance.vat_amount,
        "total_incl_vat": instance.total_incl_vat,
    }


def _recalc_invoice_item_before_update(instance: InvoiceItem, session) -> None:
    """before_update_hook (универсальный примитив движка, см.
    app/engine/config.py) — вызывается СРАЗУ после применения полей
    из PUT-запроса к instance, ДО commit. Пересчитывает
    unit_price_after_discount/line_total из ТОЛЬКО ЧТО сохранённого
    discount_percent (тот же принцип, что у
    _sync_final_total_before_save для calculation) — используется,
    когда человек редактирует скидку прямо в таблице строк счёта
    (см. invoice_items_tab в config.py), сервер — финальный источник
    истины для расчётных полей, а не фронт.

    Дополнительно (2026-08-29, исправление) пересчитывает итоги
    ШАПКИ счёта (total_excl_vat/vat_amount/total_incl_vat) прямо
    здесь — ИНАЧЕ построчное редактирование скидки через обычный
    PUT /api/invoice_item/{id} обновит саму строку, но "Разом без
    ПДВ" на карточке счёта останется устаревшим, пока не нажата
    "Дать скидку"/"Обновить" (те два handler'а зовут
    _recalculate_invoice_totals сами, а обычный PUT — нет). Строка
    ещё не закоммичена (session.flush() внутри
    _recalculate_invoice_totals достаточно, коммит сделает
    update_item в engine/api.py уже после этого хука)."""
    instance.unit_price_after_discount = round(
        instance.unit_price * (1 + (instance.discount_percent or 0.0) / 100.0), 2
    )
    instance.line_total = round(instance.unit_price_after_discount * instance.quantity, 2)
    session.add(instance)
    session.flush()

    if instance.invoice_id:
        invoice = session.get(Invoice, instance.invoice_id)
        if invoice:
            _recalculate_invoice_totals(invoice, session)


specification_table = TableConfig(
    key="specification",
    model=Specification,
    title="Спецификации",
    title_singular="спецификация",
    search_placeholder="Поиск по номеру…",
    delete_mode="soft",
    allow_create=False,
    allow_delete=False,
    document_number_field="document_number",
    document_prefix="S",
    own_page_url="/specification-v2",
    default_sort_fields=[("document_date", "desc"), ("document_time", "desc")],
    extra_lookups=["calculation"],
    # extra_lookups=["calculation"] — грузит relationOptions['calculation']
    # ЦЕЛИКОМ на клиенте (см. общий механизм в config.py), нужно только
    # readonly_items_columns ниже: колонка "calculation_number" достаёт
    # document_number калькуляции по specification_item.calculation_id
    # без похода на сервер (см. readonlyItemsColumnValue() в page.py).
    readonly_items_tab="Позиции",
    readonly_items_table_key="specification_item",
    readonly_items_columns=[
        ("calculation_number", "Калькуляция", "text"),
        ("product_name", "Изделие", "text"),
        ("quantity", "Кол-во", "text"),
        ("unit_price", "Цена за ед.", "money"),
        ("line_total", "Итого", "money"),
    ],
    readonly_items_sum_field="total_amount",
    # build_invoice (2026-08-29) — кнопка "Создать счёт" (см.
    # _build_invoice_handler выше). tab=None — specification не имеет
    # form_tabs (как и request), рендерится тем же способом, что
    # у request'овских кнопок build_specification_N.
    action_buttons=[
        ActionButton(action="build_invoice", label="Создать счёт", tab=None),
    ],
    action_handlers={
        "build_invoice": _build_invoice_handler,
    },
    fields=[
        FieldConfig(name="document_number", label="Номер", list_width="90px", form_width="120px"),
        FieldConfig(name="document_date", label="Дата", widget="date", list_width="110px", form_width="140px"),
        FieldConfig(name="document_time", label="Время", widget="time", list_width="90px", form_width="110px"),
        FieldConfig(name="request_id", label="Заявка", widget="select", list_width="18%", form_width="140px"),
        FieldConfig(name="client_id", label="Заказчик", widget="select", list_width="22%"),
        FieldConfig(name="brand_slot", label="Вариант (слот бренда)", widget="select",
                    list_width="90px", readonly=True,
                    options=[("1", "Вариант 1"), ("2", "Вариант 2"), ("3", "Вариант 3")]),
        FieldConfig(name="total_amount", label="Сумма по спецификации", widget="number",
                    is_numeric=True, list_width="120px", readonly=True),
    ],
    relations=[
        Relation(field="request_id", target_table="request", display_field="document_number", label="Заявка",
                 show_filter_chips=False),
        Relation(field="client_id", target_table="client", display_field="short_name", label="Заказчик",
                 show_filter_chips=False),
    ],
    form_rows=[
        FormRow(field_names=["document_number", "document_date", "document_time"]),
        FormRow(field_names=["client_id", "brand_slot"]),
    ],
)



# specification_item — строки спецификации (см. подробный комментарий
# механики формирования в app/models/specification.py). НЕ отдельный
# пункт меню и не drill-down уровень — hierarchy здесь ЧИСТО ради
# parent_field (тот же приём, что и у kit_item/calculation_item): даёт
# GET /api/specification_item?parent_id={specification_id} бесплатно
# через уже существующий универсальный механизм движка. allow_create/
# allow_delete=False — строки исключительно снэпшот, создаются и
# удаляются ТОЛЬКО целиком вместе со всей спецификацией (см.
# _build_specification_handler), отдельное ручное редактирование
# строки нарушило бы "замороженность" снимка и total_amount шапки.
specification_item_table = TableConfig(
    key="specification_item",
    model=SpecificationItem,
    title="Позиции спецификации",
    title_singular="позиция спецификации",
    search_placeholder="Поиск по названию…",
    allow_create=False,
    allow_delete=False,
    hierarchy=Hierarchy(parent_field="specification_id", parent_key="specification"),
    fields=[
        FieldConfig(name="specification_id", label="Спецификация", widget="select", in_list=False, in_form=False),
        FieldConfig(name="calculation_id", label="Калькуляция", widget="select", in_list=False, in_form=False),
        FieldConfig(name="product_name", label="Изделие", list_width="30%"),
        FieldConfig(name="quantity", label="Количество", widget="number",
                    is_numeric=True, list_width="90px"),
        FieldConfig(name="unit_price", label="Цена за изделие", widget="number",
                    is_numeric=True, list_width="120px"),
        FieldConfig(name="line_total", label="Сумма по строке", widget="number",
                    is_numeric=True, list_width="120px"),
    ],
    relations=[
        Relation(field="specification_id", target_table="specification", display_field="document_number",
                 label="Спецификация", show_filter_chips=False),
        Relation(field="calculation_id", target_table="calculation", display_field="full_name",
                 label="Калькуляция", show_filter_chips=False),
    ],
)


# Фирма (firm) — справочник СВОИХ юрлиц-продавцов, см. подробный
# комментарий в app/models/firm.py. Используется шапкой счёта
# (invoice.firm_id) как "Постачальник". is_default — ровно одна
# фирма может быть отмечена как фирма "по умолчанию" (простой
# checkbox, без constraint в БД — при создании нового Invoice
# берётся ПЕРВАЯ найденная is_default=True, см.
# _build_invoice_handler; если их случайно несколько — Вахтанг сам
# поправит вручную, это не автоматизируется).
# _set_default_firm_handler — кнопка "Сделать по умолчанию" (см.
# firm_table ниже). is_default НЕ обычное FieldConfig-поле (та же
# логика, что и is_deleted — см. app/models/material.py): движок не
# умеет коректно коэрсить bool из <select>/<radio> (x-model отдаёт
# строку "true"/"false", а create_item её никак не приводит к
# настоящему bool перед INSERT — упало бы на Postgres). Вместо этого
# отдельная кнопка через action_handlers, как и остальные
# нестандартные переключатели в проекте.
def _set_default_firm_handler(instance: Firm, session) -> dict:
    """Снимает is_default со ВСЕХ остальных фирм и ставит его только
    на instance — гарантирует, что "по умолчанию" ровно одна фирма
    (простая инвариантная проверка в коде, без constraint в БД)."""
    others = session.exec(select(Firm).where(Firm.id != instance.id)).all()
    for other in others:
        if other.is_default:
            other.is_default = False
            session.add(other)
    instance.is_default = True
    session.add(instance)
    session.commit()
    session.refresh(instance)
    return {"is_default": True}


firm_table = TableConfig(
    key="firm",
    model=Firm,
    title="Наши фирмы",
    title_singular="фирма",
    search_placeholder="Поиск по названию…",
    delete_mode="soft",
    action_buttons=[
        ActionButton(action="set_default_firm", label="Сделать по умолчанию", tab=None),
    ],
    action_handlers={
        "set_default_firm": _set_default_firm_handler,
    },
    fields=[
        FieldConfig(name="full_name", label="Полное название", required=True,
                    searchable=True, search_default=True, list_width="30%"),
        FieldConfig(name="egrpou_code", label="ЄДРПОУ", list_width="110px"),
        FieldConfig(name="tax_id", label="ІПН", list_width="130px", in_list=False),
        FieldConfig(name="vat_certificate_number", label="№ свідоцтва платника ПДВ", in_list=False),
        FieldConfig(name="bank_account", label="Р/р (IBAN)", in_list=False),
        FieldConfig(name="bank_name", label="Банк", in_list=False),
        FieldConfig(name="bank_mfo", label="МФО", list_width="90px", in_list=False),
        FieldConfig(name="phone", label="Телефон", list_width="120px"),
        FieldConfig(name="address", label="Адрес", in_list=False),
    ],
    form_rows=[
        FormRow(field_names=["egrpou_code", "tax_id", "bank_mfo"]),
        FormRow(field_names=["bank_account", "bank_name"]),
        FormRow(field_names=["vat_certificate_number"]),
        FormRow(field_names=["phone", "address"]),
    ],
)


# Счёт (invoice) — см. подробный комментарий механики в
# app/models/invoice.py и обработчики выше (_build_invoice_handler и
# соседние). own_page_url — та же логика, что у specification: кнопка
# "Создать счёт" делает redirect на "/invoice-v2/{id}".
#
# unlink_invoice — кнопка "Отвязать" (см. _unlink_invoice_handler)
# показывается ТОЛЬКО пока specification_id заполнен (проверка на
# фронте — CONFIG-driven x-show, см. page.py); после отвязки вместо
# неё показывается заглушка "Отвязан от спецификации".
# refresh_invoice_items — кнопка "Обновить", тоже только пока
# привязан (см. _refresh_invoice_items_handler).
invoice_table = TableConfig(
    key="invoice",
    model=Invoice,
    title="Счета",
    title_singular="счёт",
    search_placeholder="Поиск по номеру…",
    delete_mode="soft",
    allow_create=False,
    document_number_field="document_number",
    document_prefix="I",
    own_page_url="/invoice-v2",
    default_sort_fields=[("document_date", "desc"), ("document_time", "desc")],
    extra_lookups=["firm"],
    invoice_items_tab="Позиции",
    invoice_items_table_key="invoice_item",
    invoice_items_columns=[
        ("product_name", "Изделие", "text"),
        ("quantity", "Кіл-сть", "text"),
    ],
    invoice_items_discount_field="discount_percent",
    invoice_items_price_field="unit_price",
    invoice_items_price_after_discount_field="unit_price_after_discount",
    invoice_items_line_total_field="line_total",
    invoice_items_sum_field="total_excl_vat",
    invoice_items_bulk_discount_action="apply_bulk_discount",
    action_buttons=[
        ActionButton(action="refresh_invoice_items", label="Обновить", tab=None),
        ActionButton(action="unlink_invoice", label="Отвязать от спецификации", tab=None),
        # download_invoice_pdf / download_invoice_xlsx — client_side=True,
        # см. CLIENT_ACTIONS в app/engine/page.py и GET
        # /invoice-print/{id}/pdf|xlsx (app/invoice_print/router.py).
        # Excel-кнопка добавлена 2026-08-31 сразу после PDF, тот же паттерн.
        ActionButton(action="download_invoice_pdf", label="Скачать PDF", tab=None, client_side=True),
        ActionButton(action="download_invoice_xlsx", label="Скачать Excel", tab=None, client_side=True),
    ],
    action_handlers={
        "apply_bulk_discount": _apply_bulk_discount_handler,
        "refresh_invoice_items": _refresh_invoice_items_handler,
        "unlink_invoice": _unlink_invoice_handler,
    },
    fields=[
        FieldConfig(name="document_number", label="Номер", list_width="90px", form_width="120px"),
        FieldConfig(name="document_date", label="Дата", widget="date", list_width="110px", form_width="140px"),
        FieldConfig(name="document_time", label="Время", widget="time", list_width="90px", form_width="110px"),
        FieldConfig(name="request_id", label="Заявка", widget="select", list_width="16%", form_width="140px"),
        FieldConfig(name="specification_id", label="Спецификация", widget="select", list_width="16%",
                    form_width="140px"),
        FieldConfig(name="firm_id", label="Постачальник (наша фирма)", widget="select", list_width="20%"),
        FieldConfig(name="client_id", label="Заказчик", widget="select", list_width="18%"),
        FieldConfig(name="client_invoice_id", label="Платник", widget="select", list_width="18%"),
        FieldConfig(name="total_excl_vat", label="Разом без ПДВ", widget="number",
                    is_numeric=True, list_width="110px", readonly=True),
        FieldConfig(name="vat_amount", label="ПДВ", widget="number",
                    is_numeric=True, list_width="90px", readonly=True),
        FieldConfig(name="total_incl_vat", label="Всього з ПДВ", widget="number",
                    is_numeric=True, list_width="110px", readonly=True),
    ],
    relations=[
        Relation(field="request_id", target_table="request", display_field="document_number", label="Заявка",
                 show_filter_chips=False),
        Relation(field="specification_id", target_table="specification", display_field="document_number",
                 label="Спецификация", show_filter_chips=False),
        Relation(field="firm_id", target_table="firm", display_field="full_name", label="Постачальник",
                 show_filter_chips=False),
        Relation(field="client_id", target_table="client", display_field="short_name", label="Заказчик",
                 show_filter_chips=False),
        Relation(field="client_invoice_id", target_table="client", display_field="short_name", label="Платник",
                 show_filter_chips=False),
    ],
    form_rows=[
        FormRow(field_names=["document_number", "document_date", "document_time"]),
        FormRow(field_names=["request_id", "specification_id"]),
        FormRow(field_names=["firm_id"]),
        FormRow(field_names=["client_id", "client_invoice_id"]),
        FormRow(field_names=["total_excl_vat", "vat_amount", "total_incl_vat"]),
    ],
)


# invoice_item — строки счёта (см. подробный комментарий механики в
# app/models/invoice_item.py). allow_create/allow_delete=False —
# строки создаются/пересоздаются ТОЛЬКО вместе со всем счётом (см.
# _build_invoice_handler/_refresh_invoice_items_handler), но, В
# ОТЛИЧИЕ от specification_item, discount_percent КАЖДОЙ отдельной
# строки редактируется человеком напрямую — через обычный
# PUT /api/invoice_item/{id} движка (см. invoice_items_tab на
# invoice_table и рендер в page.py), не только целиком через
# пересоздание счёта.
invoice_item_table = TableConfig(
    key="invoice_item",
    model=InvoiceItem,
    title="Позиции счёта",
    title_singular="позиция счёта",
    search_placeholder="Поиск по названию…",
    allow_create=False,
    allow_delete=False,
    hierarchy=Hierarchy(parent_field="invoice_id", parent_key="invoice"),
    before_update_hook=_recalc_invoice_item_before_update,
    fields=[
        FieldConfig(name="invoice_id", label="Счёт", widget="select", in_list=False, in_form=False),
        FieldConfig(name="specification_item_id", label="Строка спецификации", widget="select",
                    in_list=False, in_form=False),
        FieldConfig(name="product_name", label="Изделие", list_width="26%"),
        FieldConfig(name="quantity", label="Количество", widget="number",
                    is_numeric=True, list_width="90px"),
        FieldConfig(name="unit_price", label="Цена без ПДВ", widget="number",
                    is_numeric=True, list_width="120px", readonly=True),
        FieldConfig(name="discount_percent", label="Знижка, %", widget="number",
                    is_numeric=True, list_width="100px", default=0),
        FieldConfig(name="unit_price_after_discount", label="Ціна зі знижкою", widget="number",
                    is_numeric=True, list_width="120px", readonly=True),
        FieldConfig(name="line_total", label="Сума без ПДВ", widget="number",
                    is_numeric=True, list_width="120px", readonly=True),
    ],
    relations=[
        Relation(field="invoice_id", target_table="invoice", display_field="document_number",
                 label="Счёт", show_filter_chips=False),
    ],
)


constant_table = TableConfig(
    key="constant",
    model=Constant,
    title="Константы",
    title_singular="константа",
    search_placeholder="Поиск по названию…",
    # Набор ключей фиксирован и задаётся один раз seed_constants()
    # при старте (см. app/database.py) — через UI создавать/удалять
    # записи нельзя, только менять value уже существующих.
    allow_create=False,
    allow_delete=False,
    fields=[
        FieldConfig(name="key", label="Ключ", readonly=True, searchable=True, list_width="26%"),
        FieldConfig(name="value", label="Значение", list_width="18%"),
        FieldConfig(name="description", label="Описание", readonly=True, in_form=False),
    ],
)


ALL_TABLES = [
    brand_table, unit_table, material_table, kit_group_table, kit_section_table,
    kit_table, kit_item_table, constant_table, client_table, request_table,
    calculation_table, calculation_item_table, product_type_rate_table,
    specification_table, specification_item_table, firm_table, invoice_table,
    invoice_item_table,
]
