# app/engine/config.py
# ============================================================
# УНИВЕРСАЛЬНЫЙ ДВИЖОК CRUD-ТАБЛИЦ — конфигурация.
#
# Идея: вместо того чтобы на каждую справочную таблицу (материалы,
# бренды, категории и т.д.) писать отдельный роутер + отдельный
# Alpine-шаблон вручную, мы один раз описываем таблицу декларативно
# через TableConfig — а движок (engine/api.py + engine/page.py) сам
# генерирует JSON API и HTML-страницу со списком+модалкой.
#
# Что покрывает движок:
#  - обычные поля (текст, число)
#  - computed_pairs — пара полей, взаимно пересчитываемых по формуле
#    (пример: price_excl_vat <-> price_incl_vat через vat_rate)
#  - relations — внешний ключ, отображаемый как выпадающий список
#    и как "живая ссылка" (имя связанной записи, а не голый ID)
#
# Чего движок НЕ покрывает (и не должен) — это осознанно:
#  - каскадные пересчёты между разными документами (продукт → спека
#    → заказ) — слишком специфичная бизнес-логика
#  - составные документы (заказ, инвойс) со своими правилами
#  - снапшоты (расчётные факты, которые не должны быть "живыми
#    ссылками") — для таких сценариев пишем отдельный код, движок
#    только для простых источников истины (справочников)
# ============================================================

from dataclasses import dataclass, field
from typing import Any, Literal, Optional
from sqlmodel import SQLModel


FieldWidget = Literal["text", "number", "select", "date", "time", "textarea"]


@dataclass
class FieldConfig:
    """Одно поле формы/списка."""
    name: str                      # имя атрибута в модели, например "short_name"
    label: str                     # подпись на русском для формы/списка
    widget: FieldWidget = "text"
    options: list[tuple[str, str]] = field(default_factory=list)
                                    # Статичный список опций (value, label) для
                                    # widget="select" БЕЗ связи с другой таблицей
                                    # (в отличие от Relation — тот всегда ссылается
                                    # на реальную справочную таблицу с id/name).
                                    # Пример: Calculation.status — фиксированный
                                    # набор ["draft","active",...], не таблица в БД.
                                    # Пусто — поле либо не select, либо select
                                    # управляется через Relation как раньше.
    required: bool = False
    placeholder: str = ""
    in_list: bool = True           # показывать в таблице списка
    list_width: Optional[str] = None   # например "26%" или "100px"
    searchable: bool = False       # участвует в текстовом поиске (q=...)
    search_toggle: bool = True     # если searchable=True и на таблице включены
                                    # enable_search_toggles — показывать ли для
                                    # этого поля отдельный чекбокс "искать по …"
                                    # (True) или включать его в поиск всегда,
                                    # без отдельного управления (False)
    search_default: bool = True    # если search_toggle=True — состояние чекбокса
                                    # при первой загрузке страницы (True — отмечен,
                                    # False — снят; человек может переключить вручную,
                                    # выбор держится, пока страница открыта)
    is_numeric: bool = False       # для выравнивания по правому краю и форматирования
    in_form: bool = True           # показывать в форме модалки (по умолчанию — да)
    form_width: Optional[str] = None   # фиксированная ширина поля в форме, например "140px";
                                        # если не задано — поле растягивается на всю доступную ширину ряда
    default: Any = None            # значение по умолчанию при создании новой записи
                                    # (если None — используется 0 для числовых, '' для текстовых)
    readonly: bool = False         # поле показывается в форме как обычный текст,
                                    # не как input — редактировать нельзя ни через
                                    # форму, ни через API (см. update_item в api.py)
    virtual: bool = False          # поле НЕ хранится в модели/БД вообще — не
                                    # передаётся в create/update, не сериализуется
                                    # из instance. Значение подтягивается на фронте
                                    # отдельным запросом (см. source_constant_key)
                                    # и показывается как readonly "живая ссылка".
                                    # Пример: ставка НДС у материала — общая для
                                    # всех, хранится только в constants, но должна
                                    # быть видна в карточке.
    source_constant_key: Optional[str] = None  # для virtual-полей: ключ константы
                                    # в справочнике constants, откуда фронт берёт
                                    # значение для отображения в форме/списке.
    row_actions: list[str] = field(default_factory=list)
                                    # Заголовки кнопок-заглушек, показанных СРАЗУ
                                    # ЗА этим полем в том же ряду формы (не под
                                    # формой целиком, в отличие от
                                    # TableConfig.extra_actions). Кнопки неактивны
                                    # (disabled), видны только у существующей
                                    # записи (editing.id). Пример: у request каждое
                                    # поле brand_slot_N_id получает свою кнопку
                                    # «Спецификация» и «Пересчитать» рядом с
                                    # выбором бренда этого варианта — их логика
                                    # появится вместе с calculation.
    tab: Optional[str] = None      # Если у TableConfig задан form_tabs — на какой
                                    # вкладке формы показывается это поле (должно
                                    # совпадать с одним из значений form_tabs). None
                                    # (или form_tabs не задан у таблицы вообще) —
                                    # поле рендерится как раньше, без вкладок.
                                    # Поля без tab при заданном form_tabs попадают
                                    # на первую вкладку по умолчанию (см.
                                    # _build_form_layout в page.py).


@dataclass
class ComputedPair:
    """
    Пара полей, взаимно пересчитываемых друг из друга по формуле.
    Пример: цена без НДС <-> цена с НДС, через ставку НДС.

    formula="vat" — единственный встроенный тип пока. Формула:
        field_b = field_a * (1 + rate / 100)
        field_a = field_b / (1 + rate / 100)
    Новые формулы (наценка, скидка) добавляются в engine/formulas.py
    по мере реальной потребности — не заранее.

    Источник ставки — ровно один из двух:
      - rate_field: имя поля модели (ставка хранится в самой записи,
        как раньше у Material.vat_rate)
      - rate_constant_key: ключ в справочнике constants (ставка —
        общая "живая ссылка", не хранится в записи вообще; пример —
        vat_rate после отказа от per-material поля). Значение
        подгружается на бэкенде из таблицы constant при пересчёте,
        и на фронте — при открытии формы, показывается как readonly.
    Если задан rate_constant_key — rate_field не используется как
    источник данных, но по-прежнему нужен как имя, под которым
    ставка живёт в editing на фронте (чтобы JS-пересчёт работал
    единообразно что для поля модели, что для константы).
    """
    field_a: str
    field_b: str
    rate_field: str
    rate_constant_key: Optional[str] = None
    formula: Literal["vat"] = "vat"
    label_a: str = ""
    label_b: str = ""
    label_rate: str = ""


@dataclass
class Relation:
    """
    Связь с другой справочной таблицей — внешний ключ, показываемый
    как выпадающий список в форме и как имя (не ID) в списке.
    "Живая ссылка" в терминах проекта: показывается текущее имя
    связанной записи, обновляется само при переименовании.
    """
    field: str                     # например "brand_id"
    target_table: str              # ключ таблицы в TABLE_REGISTRY, например "brand"
    display_field: str = "name"    # какое поле связанной записи показывать
    label: str = ""
    show_filter_chips: bool = True
                                    # Показывать ли ряд чипов-фильтров
                                    # ("Все" + одна кнопка на каждое значение
                                    # связанной таблицы) в верхней панели
                                    # списка. По умолчанию True (как было
                                    # у material/brand — один relation, один
                                    # осмысленный ряд фильтров). У документов
                                    # с несколькими relation-полями сразу
                                    # (request — 5 штук: 2 клиента + 3 бренда)
                                    # ряд чипов на КАЖДОЕ поле выглядит
                                    # захламлённо и малополезно — там лучше
                                    # обычный текстовый поиск (см. request_table,
                                    # enable_search_toggles). False отключает
                                    # чипы именно для этого relation-поля, не
                                    # трогая остальные поля/таблицы.
    searchable_fields: list[str] = field(default_factory=list)
                                    # Текстовые поля СВЯЗАННОЙ (target_table)
                                    # таблицы, по которым можно искать через
                                    # этот relation (например для request.
                                    # client_id -> ["short_name", "full_name"]
                                    # клиента). Пусто — по этому relation
                                    # текстовый поиск не ведётся (обычная
                                    # ситуация для большинства relation-полей,
                                    # где ищут через сам список/чипы, а не
                                    # текстом). Заполнено — поле участвует в
                                    # общем текстовом поиске (q=...) как JOIN
                                    # по target_table, с тем же чекбоксом
                                    # "искать по …" (enable_search_toggles),
                                    # что и обычные текстовые FieldConfig —
                                    # см. searchable_relations()/toggleable_
                                    # search_relations() ниже и join-логику
                                    # в list_items (api.py).
    search_toggle: bool = True
    search_default: bool = True
    search_label: str = ""         # подпись чекбокса поиска (например
                                    # "Клиент (заказчик)"); если пусто —
                                    # используется label этого Relation.


@dataclass
class FormRow:
    """
    Один визуальный ряд формы — список имён полей, которые должны
    отображаться рядом друг с другом (а не каждое на отдельной строке).

    Если в ряду 2+ поля — рендерится как flex-контейнер (.field-row
    для обычных полей или .price-pair, если хотя бы одно поле ряда
    входит в computed_pairs). Поля, не перечисленные ни в одном
    FormRow, идут каждое отдельным рядом — по порядку объявления в
    TableConfig.fields.
    """
    field_names: list[str] = field(default_factory=list)


@dataclass
class ActionButton:
    """Кнопка в теле модалки формы (рядом с extra_actions-заглушками),
    но с РЕАЛЬНОЙ логикой — вызывает конкретный именованный action на
    бэкенде вместо простого disabled-плейсхолдера. Пример: кнопка
    «Пересчитать название» у calculation — вызывает
    POST /api/{key}/{id}/actions/{action} (см. app/engine/api.py),
    получает готовое full_name и подставляет в открытую форму без
    закрытия модалки и без отдельного сохранения. Не путать с
    TableConfig.extra_actions (список заголовков disabled-заглушек
    без реального обработчика) — этот механизм для случаев, когда
    логика уже реализована, но кнопка не является обычным save/delete."""
    action: str                    # ключ действия, например "recalc_full_name" —
                                    # используется и в URL, и как имя метода
                                    # в JS (см. runAction() в page.py)
    label: str                     # подпись кнопки
    tab: Optional[str] = None      # на какой вкладке формы показывается
                                    # (см. FieldConfig.tab) — None, если
                                    # у таблицы нет вкладок вообще


@dataclass
class Hierarchy:
    """
    Помечает таблицу как один уровень дерева drill-down (вместо
    обычного плоского списка движка). Пример: kit_group -> kit_section
    -> kit — три TableConfig, каждый со своим Hierarchy.

    parent_field: имя FK-поля в МОДЕЛИ ЭТОЙ таблицы, указывающего на
        родителя (например "kit_group_id" у kit_section). None у
        корневого уровня (kit_group ни на что не ссылается).
    parent_key: ключ родительской таблицы в TABLE_REGISTRY/ALL_TABLES
        (например "kit_group"). None у корневого уровня.
    child_key: ключ дочерней таблицы — того, что открывается по клику
        на строку этого уровня (например у kit_group это "kit_section").
        None у последнего уровня (kit) — там клик по строке ведёт не
        вглубь дерева, а на отдельную страницу-карточку (см.
        TableConfig.edit_mode).
    root_label: подпись крошки самого верхнего уровня, показывается
        всегда первой в цепочке крошек (например "Группы").
    """
    parent_field: Optional[str] = None
    parent_key: Optional[str] = None
    child_key: Optional[str] = None
    root_label: str = ""

    def is_root(self) -> bool:
        return self.parent_key is None


@dataclass
class TableConfig:
    """Полное декларативное описание одной таблицы для движка."""
    key: str                       # уникальный ключ, например "material"
    model: type[SQLModel]
    title: str                     # заголовок страницы, например "Материалы"
    title_singular: str            # для модалки, например "материал"
    fields: list[FieldConfig] = field(default_factory=list)
    computed_pairs: list[ComputedPair] = field(default_factory=list)
    relations: list[Relation] = field(default_factory=list)
    form_rows: list[FormRow] = field(default_factory=list)
    search_placeholder: str = "Поиск…"
    enable_search_toggles: bool = False
    # Если True — на странице сверху под строкой поиска показываются
    # чекбоксы "искать по <label>" для каждого searchable-поля, и
    # пользователь может включать/выключать поля поиска по отдельности.
    # Общий принцип поиска (искать по всем searchable через ?q=) не
    # меняется — эта опция лишь добавляет фильтр по конкретным полям
    # поверх него, через ?q=...&search_fields=name1&search_fields=name2.
    allow_create: bool = True      # False — кнопка "+ Добавить" скрыта, POST
                                    # эндпоинт запрещён (422). Для справочников,
                                    # где набор записей фиксирован (constants —
                                    # ключи задаются только через seed при старте).
    allow_delete: bool = True      # False — кнопка "Удалить" в модалке скрыта,
                                    # DELETE эндпоинт запрещён (422).
    delete_mode: Literal["hard", "soft", "simple"] = "hard"
                                    # "hard" — DELETE удаляет строку физически сразу
                                    #     (поведение по умолчанию, как раньше без
                                    #     soft_delete=True).
                                    # "soft" — модель имеет поле is_deleted. Кнопка в
                                    #     модалке становится "Удалить"/"Отменить"
                                    #     (переключает флаг, не удаляет строку), в
                                    #     первой колонке списка — точка-индикатор
                                    #     статуса. Физическое удаление — отдельно,
                                    #     через purge-обработчик (app/processors).
                                    #     Это прежнее soft_delete=True.
                                    # "simple" — для узлов дерева (Hierarchy) без
                                    #     внешних ссылок на них: DELETE удаляет
                                    #     строку физически, но только если у неё нет
                                    #     дочерних записей (см. hierarchy.child_key) —
                                    #     иначе 422 с понятным сообщением. Синхронная
                                    #     проверка count(), без processor.
    hierarchy: Optional["Hierarchy"] = None
                                    # None — обычная плоская таблица (текущее
                                    # поведение движка не меняется). Заполнено —
                                    # таблица рендерится как один уровень drill-down
                                    # дерева вместо обычного списка (см. Hierarchy).
    edit_mode: Literal["modal", "own_page", "items_modal"] = "modal"
                                    # "modal" — редактирование через универсальную
                                    #     модалку движка (как сейчас у всех таблиц).
                                    # "own_page" — клик по строке ведёт на отдельную
                                    #     страницу-карточку вне движка — зарезервировано
                                    #     на будущее (для kit сейчас используется
                                    #     "items_modal" ниже, не own_page).
                                    # "items_modal" — модалка вместо обычной формы
                                    #     полей показывает СПИСОК дочерних записей
                                    #     другой таблицы (items_source_table_key) —
                                    #     отфильтрованных по текущей записи через её
                                    #     hierarchy.parent_field — плюс кнопку
                                    #     "Добавить", открывающую простую форму
                                    #     создания новой дочерней записи. Ввёдено для
                                    #     kit: клик по комплекту показывает состав
                                    #     (KitItem — материал+количество), а не
                                    #     форму переименования комплекта. НЕ
                                    #     drill-down уровень дерева — kit_item не
                                    #     появляется в hierarchy.child_key/LEVELS,
                                    #     это самостоятельный, не встроенный в дерево
                                    #     список внутри модалки конкретного узла.
    items_source_table_key: Optional[str] = None
                                    # Обязательно при edit_mode="items_modal" — ключ
                                    # TableConfig в ALL_TABLES, чьи записи показывает
                                    # модалка состава (для kit — "kit_item"). Эта
                                    # дочерняя таблица должна иметь свой hierarchy с
                                    # parent_field, указывающим на FK к текущей
                                    # записи (kit_item.hierarchy.parent_field ==
                                    # "kit_id") — так модалка сможет и загрузить
                                    # список (?parent_id={editing.id}), и создать
                                    # новую запись с проставленным FK, переиспользуя
                                    # тот же универсальный механизм, что и drill-down
                                    # между уровнями дерева (см. Hierarchy).
    extra_actions: list[str] = field(default_factory=list)
                                    # Заголовки дополнительных кнопок-заглушек,
                                    # показанных в теле модалки под формой (только
                                    # когда editing.id уже есть — на новой записи
                                    # смысла нет). Кнопки неактивны (disabled) —
                                    # используется, когда бизнес-логика кнопки
                                    # зависит от сущности, которая ещё не реализована
                                    # (пример: request — "Собрать спецификацию по
                                    # варианту 1/2/3", "Пересчитать всё", их логика
                                    # появится вместе с calculation). Не предназначено
                                    # для постоянного использования — как только
                                    # логика реализуется, кнопка либо получает
                                    # реальный @click и уходит из этого списка, либо
                                    # остаётся здесь до следующего шага.
    document_number_field: Optional[str] = None
                                    # Имя строкового поля модели, хранящего номер
                                    # документа (например "document_number" у
                                    # request) — None, если у таблицы нет своей
                                    # нумерации (справочники вроде brand/client).
                                    # Заполнено вместе с document_prefix (см. ниже) —
                                    # включает автогенерацию номера при создании и
                                    # подтяжку счётчика при сохранении, см.
                                    # app/engine/document_numbering.py.
    document_prefix: Optional[str] = None
                                    # Префикс документа для нумерации (например "R"
                                    # у request → номера вида "R-101") — свой у
                                    # каждого типа документа, счётчики независимы
                                    # (см. app/models/document_counter.py).
    child_document_actions: list[str] = field(default_factory=list)
                                    # Заголовки кнопок-заглушек в панели выделения
                                    # списка (рядом с "Копировать"), активны при
                                    # выделении РОВНО одной строки — тот же принцип,
                                    # что и у extra_actions (см. выше), но кнопки не
                                    # в форме, а в панели над списком, т.к. должны
                                    # действовать сразу по выбранной строке без
                                    # открытия модалки. Введено для request (v56):
                                    # "Создать документ на основании" (создаст
                                    # calculation, когда появится) и "Показать
                                    # подчинённые документы" (журнал calculation/
                                    # specification/invoice этой заявки, когда
                                    # появятся) — обе кнопки disabled до реализации
                                    # соответствующей сущности.
    default_sort_field: Optional[str] = None
                                    # Имя поля для сортировки списка ПО УМОЛЧАНИЮ при
                                    # первой загрузке страницы (человек может сменить
                                    # сортировку кликом по заголовку колонки как обычно
                                    # — это не блокирует ручную пересортировку, только
                                    # задаёт начальный порядок). None — порядок не
                                    # гарантирован (как было раньше у всех таблиц).
    default_sort_dir: Literal["asc", "desc"] = "asc"
    default_sort_fields: list[tuple[str, Literal["asc", "desc"]]] = field(default_factory=list)
                                    # Сортировка списка по НЕСКОЛЬКИМ полям сразу, по
                                    # порядку значимости (например у calculation:
                                    # сначала document_date desc, потом document_time
                                    # desc — "новые сверху", но при одинаковой дате
                                    # решает время). Если задано — используется ВМЕСТО
                                    # default_sort_field/default_sort_dir (те остаются
                                    # для обратной совместимости однополевого случая,
                                    # не удаляю их, чтобы не трогать request). Пусто —
                                    # ведёт себя как раньше, по одиночному полю.
    form_tabs: list[str] = field(default_factory=list)
                                    # Названия вкладок формы, например ["Основное",
                                    # "Настройки"] — переключение без закрытия модалки.
                                    # Пусто (по умолчанию) — форма рендерится как
                                    # раньше, без вкладок, ничего не меняется у
                                    # существующих таблиц. Заполнено — КАЖДОЕ поле
                                    # формы должно иметь FieldConfig.tab, указывающий
                                    # на одно из этих названий (поле без tab уходит на
                                    # первую вкладку по умолчанию, см. _build_form_layout).
    action_buttons: list["ActionButton"] = field(default_factory=list)
                                    # Кнопки с реальной логикой в теле модалки (не
                                    # disabled-заглушки, см. ActionButton). Показываются
                                    # только у существующей записи (editing.id), как и
                                    # extra_actions. Если form_tabs задан — каждая
                                    # кнопка рендерится на своей ActionButton.tab.
    action_handlers: dict[str, Any] = field(default_factory=dict)
                                    # Обработчики для action_buttons — {action_key: fn},
                                    # где fn(instance, session) -> dict с полями, которые
                                    # нужно подмешать в открытую форму на фронте (см.
                                    # POST /api/{key}/{id}/actions/{action} в engine/api.py
                                    # и runAction() в engine/page.py). Функция сама решает,
                                    # сохранять ли изменения в БД (session.add/commit) —
                                    # движок этого не делает автоматически, т.к. разным
                                    # кнопкам может понадобиться разное (например
                                    # "Пересчитать название" у calculation сразу сохраняет
                                    # instance.full_name в БД, не только возвращает его).

    def field_names(self) -> list[str]:
        """Имена полей, реально хранящихся в модели/БД — используется
        для сериализации instance и для фильтрации payload при
        create/update. Virtual-поля (см. FieldConfig.virtual)
        намеренно исключены: для них нет атрибута в модели."""
        return [f.name for f in self.fields if not f.virtual]

    def searchable_fields(self) -> list[str]:
        return [f.name for f in self.fields if f.searchable]

    def toggleable_search_fields(self) -> list[FieldConfig]:
        """Поля, для которых показывается отдельный чекбокс поиска
        (searchable=True и search_toggle=True)."""
        return [f for f in self.fields if f.searchable and f.search_toggle]

    def always_searched_fields(self) -> list[str]:
        """Searchable-поля, которые ищутся всегда, независимо от
        состояния чекбоксов (searchable=True, но search_toggle=False)."""
        return [f.name for f in self.fields if f.searchable and not f.search_toggle]

    def searchable_relations(self) -> list["Relation"]:
        """Relation-поля с непустым searchable_fields — участвуют в
        общем текстовом поиске через JOIN на target_table (см.
        Relation.searchable_fields)."""
        return [r for r in self.relations if r.searchable_fields]

    def toggleable_search_relations(self) -> list["Relation"]:
        return [r for r in self.searchable_relations() if r.search_toggle]

    def always_searched_relations(self) -> list["Relation"]:
        return [r for r in self.searchable_relations() if not r.search_toggle]
