# app/engine/page.py
# ============================================================
# Генерирует HTML-страницу (список + модалка редактирования на
# Alpine.js) по TableConfig — заменяет собой ручное написание
# list_alpine.html на каждую таблицу.
#
# Генерируется единая Jinja-заготовка (page_template ниже,
# написана один раз для всего движка) + JS-объект для Alpine,
# собранный из конфигурации: какие поля есть, какие пары считаются,
# какие relation-поля тянутся как выпадающий список.
#
# Ограничение (осознанное): страница рендерится как обычный Jinja-
# шаблон через render_table_page(config) → HTML-строка. Это не
# "компиляция" в файл на диске — просто generate-on-request, что
# для admin-панели простых справочников более чем достаточно по
# производительности.
# ============================================================

import json
from typing import Optional

from app.engine.config import TableConfig, FieldConfig


_NON_ROOT_HIERARCHY_TEMPLATE_SOURCE = r"""
{% extends "base.html" %}
{% block content %}
<div class="topbar">
  <div class="topbar-title"><h1>{{ config.title }}</h1></div>
</div>
<p style="color:var(--ink-soft); padding:16px 0;">
  «{{ config.title }}» открывается изнутри дерева
  {% if config.hierarchy.parent_key %}«{{ config.hierarchy.parent_key }}»{% endif %} —
  перейдите на страницу верхнего уровня и раскройте нужный узел кликом.
</p>
{% endblock %}
"""


_PAGE_TEMPLATE_SOURCE = r"""
{% extends "base.html" %}
{% block content %}
<div x-data="enginePage()" x-init="init()">

  {% if render_mode != 'form' %}
  {% if not config.hierarchy %}
  <div class="topbar">
    <div class="topbar-title">
      <h1>{{ config.title }}</h1>
      <span class="count" x-text="items.length + ' позиций'"></span>
    </div>
    <div style="display:flex; gap:8px;">
      <button class="btn" x-show="chainReturnUrl" x-cloak @click="window.location.href = chainReturnUrl">← К цепочке</button>
      {% if config.allow_create %}
      <button class="btn btn-primary" @click="openCreateRow()">+ {{ config.title_singular|capitalize }}</button>
      {% endif %}
    </div>
  </div>

  {% if config.allow_create %}
  <div class="selection-bar" x-show="selectedIds.length > 0" x-cloak>
    <span x-text="selectedIds.length + ' выделено'"></span>
    <button type="button" class="btn" :disabled="selectedIds.length !== 1" @click="copySelected()">Копировать</button>
    {% if config.child_document_actions|length > 0 %}
    {% if config.create_child_document_url %}
    <button type="button" class="btn" :disabled="selectedIds.length !== 1" @click="createChildDocument()">{{ config.child_document_actions[0] }}</button>
    {% else %}
    <button type="button" class="btn" disabled title="Пока недоступно">{{ config.child_document_actions[0] }}</button>
    {% endif %}
    {% endif %}
    {% if config.child_document_actions|length > 1 %}
    {% if config.documents_chain_url %}
    <button type="button" class="btn" :disabled="selectedIds.length !== 1" @click="showDocumentsChain()">{{ config.child_document_actions[1] }}</button>
    {% else %}
    <button type="button" class="btn" disabled title="Пока недоступно">{{ config.child_document_actions[1] }}</button>
    {% endif %}
    {% endif %}
    {% if config.delete_mode == "soft" %}
    <button type="button" class="btn" @click="bulkMarkDelete(true)">Пометить на удаление</button>
    <button type="button" class="btn" @click="bulkMarkDelete(false)">Снять пометку</button>
    {% endif %}
    <button type="button" class="selection-clear" @click="selectedIds = []">Снять выделение</button>
  </div>
  {% endif %}

  {% if config.enable_search_toggles and (toggleable_search_fields or toggleable_search_relations) %}
  <div class="search-toggles-row">
    {% for f in toggleable_search_fields %}
    <label class="search-toggle-chip">
      <input type="checkbox" x-model="searchFields['{{ f.name }}']" @change="onSearchFieldsChange()">
      {{ f.label }}
    </label>
    {% endfor %}
    {% for r in toggleable_search_relations %}
    <label class="search-toggle-chip">
      <input type="checkbox" x-model="searchFields['rel:{{ r.field }}']" @change="onSearchFieldsChange()">
      {{ r.search_label or r.label }}
    </label>
    {% endfor %}
    <span style="width:1px;height:20px;background:var(--line);margin:0 2px;"></span>
    <label class="search-toggle-chip" title="Искать только совпадения, начинающиеся с введённого текста, а не любое вхождение">
      <input type="checkbox" x-model="exactPrefix" @change="onSearchFieldsChange()">
      Точное совпадение
    </label>
  </div>
  {% endif %}

  <div class="filterbar">
    <div class="search-wrap">
      <input class="search-input" type="text" placeholder="{{ config.search_placeholder }}"
             x-model="q" @input.debounce.300ms="page=1; load()">
      <button type="button" class="search-clear" title="Сбросить поиск" @click="q=''; page=1; load()">✕</button>
    </div>
    {% if config.relations %}
    {% for rel in config.relations %}
    {% if rel.show_filter_chips %}
    <span style="width:1px;height:20px;background:var(--line);margin:0 4px;"></span>
    <span class="chip" :class="{active: !activeFilters['{{ rel.field }}']}" @click="activeFilters['{{ rel.field }}']=null; page=1; load()">Все</span>
    <template x-for="opt in relationOptions['{{ rel.field }}']" :key="opt.id">
      <span class="chip" :class="{active: activeFilters['{{ rel.field }}'] === opt.id}"
            @click="activeFilters['{{ rel.field }}'] = opt.id; page=1; load()" x-text="opt['{{ rel.display_field }}']"></span>
    </template>
    {% endif %}
    {% endfor %}
    {% endif %}

  </div>

  <div class="table-wrap">
    <table>
      <thead>
        <tr>
          {% if config.allow_create %}
          <th style="width:28px"></th>
          {% endif %}
          {% if config.delete_mode == "soft" %}
          <th style="width:28px"></th>
          {% endif %}
          {% for f in config.fields %}{% if f.in_list %}
          {% set rel = config.relations | selectattr("field", "equalto", f.name) | first %}
          <th{% if f.list_width %} style="width:{{ f.list_width }}"{% endif %}{% if f.is_numeric %} class="col-num"{% endif %}
              {% if not rel %}class="col-sortable" @click="toggleSort('{{ f.name }}')"{% endif %}>
            {{ f.label }}
            {% if not rel %}
            <span x-show="sortBy === '{{ f.name }}'" x-text="sortDir === 'asc' ? '▲' : '▼'" class="sort-arrow"></span>
            {% endif %}
          </th>
          {% endif %}{% endfor %}
          <th style="width:70px"></th>
        </tr>
      </thead>
      <tbody>
        <template x-for="item in items" :key="item.id">
          <tr @click="openDocumentRow(item)">
            {% if config.allow_create %}
            <td @click.stop>
              <input type="checkbox" :value="item.id" :checked="selectedIds.includes(item.id)" @change="toggleSelect(item.id)">
            </td>
            {% endif %}
            {% if config.delete_mode == "soft" %}
            <td>
              <span x-show="item.is_deleted" class="status-dot" title="Помечено к удалению"></span>
            </td>
            {% endif %}
            {% for f in config.fields %}{% if f.in_list %}
            {% set rel = config.relations | selectattr("field", "equalto", f.name) | first %}
            <td{% if f.is_numeric %} class="col-num"{% endif %}>
              {% if f.virtual %}
              <span x-text="constants['{{ f.source_constant_key }}'] ?? ''"></span>
              {% elif rel %}
              <span class="brand-badge" x-text="relationName('{{ f.name }}', item.{{ f.name }})"></span>
              {% elif f.list_as_dot and f.options %}
              <span class="status-dot" :style="{ background: {{ f.dot_colors|tojson }}[item.{{ f.name }}] || '#c9c6bd' }" :title="optionLabel('{{ f.name }}', item.{{ f.name }})"></span>
              {% elif f.options %}
              <span x-text="optionLabel('{{ f.name }}', item.{{ f.name }})"></span>
              {% elif f.is_numeric %}
              <span x-text="Number(item.{{ f.name }} ?? 0).toFixed(2)"></span>
              {% else %}
              <span x-text="item.{{ f.name }} ?? ''"></span>
              {% endif %}
            </td>
            {% endif %}{% endfor %}
            <td></td>
          </tr>
        </template>
        <tr x-show="items.length === 0">
          <td colspan="{{ config.fields | selectattr('in_list') | list | length + 1 + (1 if config.delete_mode == 'soft' else 0) + (1 if config.allow_create else 0) }}" style="text-align:center; color:var(--ink-soft); padding:24px;">Ничего не найдено</td>
        </tr>
      </tbody>
    </table>
  </div>

  <div class="pagination" x-show="totalPages > 1">
    <button type="button" @click="prevPage()" :disabled="page <= 1">‹ Назад</button>
    <span x-text="'Стр. ' + page + ' из ' + totalPages"></span>
    <button type="button" @click="nextPage()" :disabled="page >= totalPages">Далее ›</button>
  </div>
  {% else %}
  <div class="topbar">
    <div class="topbar-title">
      <h1>{{ config.title }}</h1>
    </div>
  </div>

  <div class="drill-breadcrumbs">
    <button type="button" class="btn drill-back" x-show="drillPath.length > 0" @click="drillBack()">‹</button>
    <template x-for="(crumb, idx) in drillCrumbs" :key="idx">
      <span>
        <a href="#" class="drill-crumb-link" :class="{'drill-crumb-current': idx === drillCrumbs.length - 1}"
           @click.prevent="drillGoTo(idx)" x-text="crumb.label"></a>
        <span x-show="idx < drillCrumbs.length - 1" class="drill-crumb-sep">›</span>
      </span>
    </template>
  </div>

  <!-- Выделение (чекбоксы + панель) — только на уровнях с items_modal
       (сейчас единственный такой уровень дерева — kit): у kit_group/
       kit_section (delete_mode="simple", edit_mode="modal") группового
       копирования/пометки на удаление нет и не планировалось — см.
       ответ Вахтанга при постановке задачи ("чекбоксы только на
       уровне комплектов"). isSelectableLevel() — то же самое условие,
       что и editMode здесь, вынесено в JS, чтобы не дублировать его
       ещё и в проверках copySelected()/bulkMarkDelete(). -->
  <div class="selection-bar" x-show="isSelectableLevel() && selectedIds.length > 0" x-cloak>
    <span x-text="selectedIds.length + ' выделено'"></span>
    <button type="button" class="btn" :disabled="selectedIds.length !== 1" @click="copySelected()">Копировать</button>
    <template x-if="currentLevel().deleteMode === 'soft'">
      <span style="display:contents;">
        <button type="button" class="btn" @click="bulkMarkDelete(true)">Пометить на удаление</button>
        <button type="button" class="btn" @click="bulkMarkDelete(false)">Снять пометку</button>
      </span>
    </template>
    <button type="button" class="selection-clear" @click="selectedIds = []">Снять выделение</button>
  </div>

  <div class="drill-list">
    <template x-for="item in items" :key="item.id">
      <div class="drill-row">
        <template x-if="isSelectableLevel()">
          <input type="checkbox" class="drill-row-checkbox" :value="item.id"
                 :checked="selectedIds.includes(item.id)" @click.stop="toggleSelect(item.id)">
        </template>
        <span class="status-dot" x-show="currentLevel().deleteMode === 'soft' && item.is_deleted" title="Помечено к удалению"></span>
        <!-- Иконка ✎ остаётся видимой как явная подсказка "здесь можно
             редактировать", но перестала быть ЕДИНСТВЕННЫМ способом
             открыть карточку/модалку — раньше тело строки на нижнем
             уровне дерева (kit, hasNextLevel=false) не реагировало на
             клик вообще, приходилось точно попадать по маленькой
             иконке (см. правку ниже и HANDOFF: "выбор можно было
             осуществить прямо непосредственно тапнув на позицию"). -->
        <button type="button" class="drill-row-edit" @click.stop="openEdit(item)" title="Редактировать">✎</button>
        <div class="drill-row-body" :class="{'drill-row-body-clickable': true}" @click="rowClick(item)">
          <span x-text="item.name"></span>
        </div>
        <span class="drill-row-arrow" x-show="hasNextLevel">›</span>
      </div>
    </template>
    <div class="drill-row drill-row-empty" x-show="items.length === 0">Ничего не найдено</div>
    <div class="drill-row drill-row-add" x-show="currentLevel().allowCreate" @click="openCreate()">
      <span x-text="'+ ' + currentLevel().titleSingular"></span>
    </div>
  </div>
  {% endif %}
  {% endif %}

  {% if render_mode == 'form' and not config.hierarchy %}
  <div class="topbar">
    <div class="topbar-title">
      <h1>{{ config.title_singular|capitalize }}</h1>
    </div>
    <div style="display:flex; gap:8px;">
      <button class="btn" x-show="chainReturnUrl" x-cloak @click="window.location.href = chainReturnUrl">← К цепочке</button>
    </div>
  </div>
  {% endif %}

  {% if render_mode != 'list' %}
  <div class="modal-backdrop"{% if render_mode == 'form' and not config.hierarchy %} style="position:static; padding:0; background:none; display:block;"{% endif %} x-show="{{ 'true' if (render_mode == 'form' and not config.hierarchy) else 'modalOpen' }}" x-cloak>
    <div class="modal"{% if render_mode == 'form' and not config.hierarchy %} style="width:100%; max-width:none; margin:0; min-height:100dvh; border-radius:0;"{% endif %}>
      <div class="modal-header">
        <div>
          <h2 x-show="!isItemsModal() || !editing.id" x-text="editing.id ? 'Редактирование' : 'Новая запись'"></h2>
          <h2 x-show="isItemsModal() && editing.id" x-text="editing.name || ''"></h2>
        </div>
      </div>

      <div id="js-error-banner" style="display:none; background:#f3e6e3; border:1px solid #9c3b2e; color:#9c3b2e; padding:10px 16px; margin:0 20px 14px; border-radius:6px; font-family:monospace; font-size:12px; white-space:pre-wrap;"></div>

      {% macro render_form_rows(rows) %}
        {% for row in rows %}
        <div{% if row.is_computed_pair %} class="price-pair"{% elif row.fields | length > 1 %} class="field-row"{% endif %}>
          {% for f in row.fields %}
          {% set rel = config.relations | selectattr("field", "equalto", f.name) | first %}
          {% set inline_btn = config.action_buttons | selectattr("action", "equalto", f.inline_action) | first if f.inline_action else None %}
          <div class="field"{% if f.form_width %} style="flex: 0 0 {{ f.form_width }};"{% endif %}>
            {% set pair_as_b = config.computed_pairs | selectattr("field_b", "equalto", f.name) | selectattr("rate_constant_key") | first %}
            {% if pair_as_b %}
            <label>{{ f.label }} (<span x-text="constants['{{ pair_as_b.rate_constant_key }}'] ?? ''"></span>%)</label>
            {% else %}
            <label>{{ f.label }}</label>
            {% endif %}
            {% if rel %}
            <div class="field-with-actions">
              <select x-model.number="editing.{{ f.name }}"{% if f.on_change_action %} @change="runAction('{{ f.on_change_action }}')"{% endif %}>
                <option :value="null">—</option>
                <template x-for="opt in relationOptions['{{ f.name }}']" :key="opt.id">
                  <option :value="opt.id" x-text="opt['{{ rel.display_field }}']"></option>
                </template>
              </select>
              {% if f.row_actions %}
              <div class="row-actions" x-show="editing.id">
                {% for action_label in f.row_actions %}
                {% set action_name = f.row_action_names[loop.index0] if f.row_action_names|length > loop.index0 else None %}
                {% if action_name %}
                <button type="button" class="btn btn-ghost btn-small" @click="runAction('{{ action_name }}')">{{ action_label }}</button>
                {% else %}
                <button type="button" class="btn btn-ghost btn-small" disabled title="Пока недоступно">{{ action_label }}</button>
                {% endif %}
                {% endfor %}
              </div>
              {% endif %}
            </div>
            {% elif inline_btn %}
            <div class="field-with-actions">
              <input type="text"{% if f.required %} required{% endif %} placeholder="{{ f.placeholder }}" x-model="editing.{{ f.name }}">
              <div class="row-actions">
                {% if inline_btn.client_side %}
                <button type="button" class="btn btn-ghost btn-small" @click="runAction('{{ inline_btn.action }}')">{{ inline_btn.label }}</button>
                {% else %}
                <button type="button" class="btn btn-ghost btn-small" @click="runAction('{{ inline_btn.action }}')" :disabled="!editing.id" :title="editing.id ? '' : 'Сначала сохраните запись'">{{ inline_btn.label }}</button>
                {% endif %}
              </div>
            </div>
            {% elif f.virtual %}
            <span class="field-readonly-text" x-text="constants['{{ f.source_constant_key }}'] ?? ''"></span>
            {% elif f.readonly %}
            <span class="field-readonly-text" x-text="editing.{{ f.name }} ?? ''"></span>
            {% elif f.name in computed_field_names %}
            <input type="number" step="0.01" x-model.number="editing.{{ f.name }}" @input="onComputedChange('{{ f.name }}')">
            {% elif f.widget == "number" %}
            <input type="number" step="0.01"{% if f.required %} required{% endif %} placeholder="{{ f.placeholder }}" x-model.number="editing.{{ f.name }}">
            {% elif f.widget == "date" %}
            <input type="date"{% if f.required %} required{% endif %} x-model="editing.{{ f.name }}">
            {% elif f.widget == "time" %}
            <input type="time"{% if f.required %} required{% endif %} x-model="editing.{{ f.name }}">
            {% elif f.widget == "select" and f.options %}
            <select x-model="editing.{{ f.name }}">
              <option value="">—</option>
              {% for value, label in f.options %}
              <option value="{{ value }}">{{ label }}</option>
              {% endfor %}
            </select>
            {% elif f.widget == "radio" and f.options %}
            <div class="radio-group">
              {% for value, label in f.options %}
              <label class="radio-option">
                <input type="radio" name="{{ f.name }}" value="{{ value }}" x-model="editing.{{ f.name }}"{% if f.on_change_action %} @change="runAction('{{ f.on_change_action }}')"{% endif %}>
                <span x-text="(editing.{{ f.radio_labels_field or '_none_' }} && editing.{{ f.radio_labels_field or '_none_' }}['{{ value }}']) || '{{ label }}'"></span>
              </label>
              {% endfor %}
            </div>
            {% elif f.widget == "textarea" %}
            <textarea rows="2"{% if f.required %} required{% endif %} placeholder="{{ f.placeholder }}" x-model="editing.{{ f.name }}"></textarea>
            {% else %}
            <input type="text"{% if f.required %} required{% endif %} placeholder="{{ f.placeholder }}" x-model="editing.{{ f.name }}">
            {% endif %}
            {% if f.hint %}
            <p class="field-hint">{{ f.hint }}</p>
            {% endif %}
          </div>
          {% endfor %}
        </div>
        {% endfor %}
      {% endmacro %}

      {% macro render_action_buttons(buttons) %}
        {# Кнопки, у которых есть поле с inline_action на них (см.
           render_form_rows) уже отрисованы рядом со своим полем —
           здесь не дублируем, показываем только "бесхозные" действия. #}
        {% set inline_action_names = config.fields | selectattr("inline_action") | map(attribute="inline_action") | list %}
        {% set standalone = buttons | rejectattr("action", "in", inline_action_names) | list %}
        {% if standalone %}
        <div class="extra-actions">
          {% for btn in standalone %}
          <button type="button" class="btn btn-ghost" @click="runAction('{{ btn.action }}')"{% if not btn.client_side %} x-show="editing.id"{% endif %}>{{ btn.label }}</button>
          {% endfor %}
        </div>
        {% endif %}
      {% endmacro %}

      <div class="modal-body"{% if render_mode == 'form' and not config.hierarchy %} style="max-height:none; overflow-y:visible;"{% endif %}>
        {% if not config.hierarchy %}
        {% if config.form_tabs %}
        <!-- Форма с вкладками (TableConfig.form_tabs) — переключение
             внутри модалки без закрытия/перезагрузки, чистый Alpine
             x-show по индексу activeFormTab (см. JS state). Введено
             для calculation: "Основное" (поля документа) + "Настройки"
             (шаблон полного названия + кнопка "Пересчитать название",
             см. ActionButton) — переиспользуемо для любой будущей
             таблицы движка с похожей потребностью, не хак под
             calculation конкретно. -->
        <div class="form-tabs-bar">
          {% for tab in config.form_tabs %}
          <button type="button" class="form-tab-btn" :class="{'form-tab-btn-active': activeFormTab === {{ loop.index0 }}}" @click="activeFormTab = {{ loop.index0 }}">{{ tab }}</button>
          {% endfor %}
        </div>
        {% for tab in config.form_tabs %}
        <div x-show="activeFormTab === {{ loop.index0 }}">
          {% if config.materials_tab == tab %}
          <!-- Вкладка "Материалы" (TableConfig.materials_tab, calculation,
               2026-08-23) — НЕ обычные поля формы, а отдельный виджет
               состава: список позиций + сумма без НДС сверху + выделение/
               копирование/массовое удаление + инлайн-редактирование
               количества + кнопка "Добавить" (открывает ТОТ ЖЕ picker-
               интерфейс, что и MaterialPicker кита — верхняя зона
               черновика + хэндл + нижняя зона поиска, см.
               openMaterialAdder()/pickerTarget='calculation' в JS,
               по прямой просьбе "тот же интерфейс, что и в подборе для
               комплектов") + кнопка "Пересчитать" (materials_recalc_action,
               алиас: обновляет цены без открытия picker'а, когда состав
               менять не нужно). Не показывается для ещё НЕ сохранённой
               записи — позиции материалов физически привязаны к
               calculation_id, которого ещё нет у новой записи (человек
               сначала сохраняет "шапку" документа на вкладке "Основное",
               потом переходит сюда). -->
          <div x-show="!editing.id" class="materials-tab-hint">Сначала сохраните калькуляцию — материалы можно добавить после.</div>
          <div x-show="editing.id" x-cloak>
            <div class="materials-summary">
              <span>Сумма без НДС:</span>
              <span x-text="materialsTotal.toFixed(2)"></span>
            </div>
            <div class="materials-toolbar">
              <button type="button" class="btn btn-primary" @click="openMaterialAdder()">+ Добавить</button>
              {% if config.materials_recalc_action %}
              <button type="button" class="btn btn-ghost" @click="runAction('{{ config.materials_recalc_action }}').then(() => loadMaterialsItems())">Пересчитать</button>
              {% endif %}
            </div>
            <div class="selection-bar" x-show="materialsSelectedIds.length > 0" x-cloak>
              <span x-text="materialsSelectedIds.length + ' выделено'"></span>
              <button type="button" class="btn" :disabled="materialsSelectedIds.length !== 1" @click="copyMaterialItem()">Копировать</button>
              <button type="button" class="btn btn-danger-ghost" @click="deleteSelectedMaterialItems()">Удалить</button>
              <button type="button" class="selection-clear" @click="materialsSelectedIds = []">Снять выделение</button>
            </div>
            <div class="materials-list">
              <template x-for="row in materialsItems" :key="row.id">
                <div class="materials-row">
                  <input type="checkbox" class="drill-row-checkbox" :value="row.id"
                         :checked="materialsSelectedIds.includes(row.id)" @click="toggleMaterialSelect(row.id)">
                  <div class="materials-row-info">
                    <span class="materials-row-name" x-text="materialItemLabel(row.material_id)"></span>
                    <span class="materials-row-unit" x-text="materialItemUnit(row.material_id)"></span>
                  </div>
                  <div class="picker-qty-control">
                    <button type="button" class="picker-qty-btn" @click="materialItemDecrement(row)">−</button>
                    <span class="picker-qty-value" x-text="row.quantity"></span>
                    <button type="button" class="picker-qty-btn" @click="materialItemIncrement(row)">+</button>
                  </div>
                  <span class="materials-row-price" x-text="Number(row.price_excl_vat ?? 0).toFixed(2)"></span>
                  <span class="materials-row-sum" x-text="(Number(row.price_excl_vat ?? 0) * Number(row.quantity ?? 0)).toFixed(2)"></span>
                </div>
              </template>
              <div class="materials-row materials-row-empty" x-show="materialsItems.length === 0">Пока пусто — материалы не добавлены</div>
            </div>
          </div>
          {% elif config.kits_tab == tab %}
          <!-- Вкладка "Комплекты" (TableConfig.kits_tab, calculation,
               2026-08-23, пикер добавлен 2026-08-23 вторым заходом по
               прямой просьбе Вахтанга) — параллельный аналог вкладки
               "Материалы", та же физическая таблица calculation_item,
               отфильтрованная по kit_id вместо material_id (см.
               loadKitsItems()). Цена строки — снэпшот СУММЫ СОСТАВА
               комплекта (не цена самого Kit — у него ценового поля нет,
               состав живой), проставляется на сервере при "Сохранить
               состав" (PUT .../items, has_kit_snapshot) и обновляется
               общей кнопкой "Пересчитать" (тот же action, что и у
               материалов). Добавление — ТЕПЕРЬ через ТОТ ЖЕ picker-
               интерфейс, что и у материалов (openKitAdder() открывает
               picker с pickerTarget='kits'), но нижняя зона подбора —
               ДЕРЕВО группа→раздел→комплект вместо плоского поиска (см.
               picker-overlay ниже: pickerTarget==='kits' переключает
               разметку нижней панели). Инлайн +/− количества в списке —
               тот же паттерн, что и у материалов (kitItemIncrement/
               kitItemDecrement). Клик по НАЗВАНИЮ строки открывает
               read-only модалку состава комплекта (openKitDetail()) —
               остальные зоны строки (степпер, цена, сумма) не триггерят
               модалку, чтобы не конфликтовать с +/-. -->
          <div x-show="!editing.id" class="materials-tab-hint">Сначала сохраните калькуляцию — комплекты можно добавить после.</div>
          <div x-show="editing.id" x-cloak>
            <div class="materials-summary">
              <span>Сумма без НДС:</span>
              <span x-text="kitsTotal.toFixed(2)"></span>
            </div>
            <div class="materials-toolbar">
              <button type="button" class="btn btn-primary" @click="openKitAdder()">+ Добавить</button>
              {% if config.materials_recalc_action %}
              <button type="button" class="btn btn-ghost" @click="runAction('{{ config.materials_recalc_action }}').then(() => loadKitsItems())">Пересчитать</button>
              {% endif %}
            </div>
            <div class="selection-bar" x-show="kitsSelectedIds.length > 0" x-cloak>
              <span x-text="kitsSelectedIds.length + ' выделено'"></span>
              <button type="button" class="btn" :disabled="kitsSelectedIds.length !== 1" @click="copyKitItem()">Копировать</button>
              <button type="button" class="btn btn-danger-ghost" @click="deleteSelectedKitItems()">Удалить</button>
              <button type="button" class="selection-clear" @click="kitsSelectedIds = []">Снять выделение</button>
            </div>
            <div class="materials-list">
              <template x-for="row in kitsItems" :key="row.id">
                <div class="materials-row">
                  <input type="checkbox" class="drill-row-checkbox" :value="row.id"
                         :checked="kitsSelectedIds.includes(row.id)" @click="toggleKitSelect(row.id, $event)">
                  <div class="materials-row-info kit-row-clickable" @click="openKitDetail(row)">
                    <span class="materials-row-name" x-text="kitItemLabel(row.kit_id)"></span>
                  </div>
                  <div class="picker-qty-control">
                    <button type="button" class="picker-qty-btn" @click="kitItemDecrement(row)">−</button>
                    <span class="picker-qty-value" x-text="row.quantity"></span>
                    <button type="button" class="picker-qty-btn" @click="kitItemIncrement(row)">+</button>
                  </div>
                  <span class="materials-row-price" x-text="Number(row.price_excl_vat ?? 0).toFixed(2)"></span>
                  <span class="materials-row-sum" x-text="(Number(row.price_excl_vat ?? 0) * Number(row.quantity ?? 0)).toFixed(2)"></span>
                </div>
              </template>
              <div class="materials-row materials-row-empty" x-show="kitsItems.length === 0">Пока пусто — комплекты не добавлены</div>
            </div>
          </div>
          {% else %}
          {{ render_form_rows(form_layout_by_tab[tab]) }}
          {% if loop.first and config.computed_pairs %}
          <div class="vat-note">↻ Пересчитывается автоматически при изменении одного из полей — можно переопределить вручную.</div>
          {% endif %}
          {% if tab == 'Стоимость' and config.materials_recalc_action %}
          <!-- Автопересчёт "Стоимости" (2026-08-28) — x-effect отслеживает
               ВСЕ реактивные зависимости, прочитанные внутри
               applyLiveCostTotals() (materialsTotal/kitsTotal/editing.*, см.
               соответствующие геттеры выше в page.py), и перезапускается
               сам при любом их изменении: добавили/удалили/поправили
               строку материала или комплекта, поменяли insurance_markup/
               markup_percent/assembly_hours/product_type_rate_id/
               cost_method — без похода на сервер, без нажатия "Пересчитать"
               (та кнопка ниже осталась ТОЛЬКО ради подтяжки актуальных цен
               из справочника материалов, см. её комментарий). Пустой div,
               не показывается — сюда просто удобно повесить x-effect
               именно на область вкладки "Стоимость", а не глобально на всю
               форму (там она давала бы лишние срабатывания на вкладках, где
               суммы стоимости не показываются). -->
          <div x-effect="applyLiveCostTotals()" style="display:none"></div>
          <!-- Вкладка "Стоимость" калькуляции (2026-08-27) — та же самая
               кнопка "Пересчитать" и то же действие (materials_recalc_action
               = recalc_material_prices), что и на вкладках "Материалы"/
               "Комплекты": по решению Вахтанга кнопка везде делает ОДНО И
               ТО ЖЕ — идёт в справочник материалов, обновляет актуальные
               цены строк calculation_item (и материалов, и комплектов),
               затем на их основе пересчитывает итоги "Стоимости". Здесь
               физически продублирована в разметке, чтобы с этой вкладки
               не нужно было прыгать на "Материалы" ради того же действия.
               После выполнения подтягиваем оба списка позиций, чтобы они
               не оставались с устаревшими ценами, если человек потом
               откроет те вкладки в этой же сессии. -->
          <div class="materials-toolbar" x-show="editing.id" x-cloak>
            <button type="button" class="btn btn-ghost"
                    @click="runAction('{{ config.materials_recalc_action }}').then(() => Promise.all([loadMaterialsItems(), loadKitsItems()]))">Пересчитать</button>
          </div>
          {% endif %}
          {{ render_action_buttons(action_buttons_by_tab.get(tab, [])) }}
          {% if loop.first and config.extra_actions %}
          <div class="extra-actions" x-show="editing.id">
            {% for action_label in config.extra_actions %}
            <button type="button" class="btn btn-ghost" disabled title="Пока недоступно">{{ action_label }}</button>
            {% endfor %}
          </div>
          {% endif %}
          {% endif %}
        </div>
        {% endfor %}
        {% else %}
        {{ render_form_rows(form_layout_by_tab['']) }}
        {% if config.computed_pairs %}
        <div class="vat-note">↻ Пересчитывается автоматически при изменении одного из полей — можно переопределить вручную.</div>
        {% endif %}
        {{ render_action_buttons(action_buttons_by_tab.get('', [])) }}
        {% if config.readonly_items_tab %}
        <!-- Read-only список дочерних строк (TableConfig.readonly_items_tab,
             2026-08-28) — таблица без form_tabs (specification), поэтому
             рендерится здесь безусловно, не внутри цикла по вкладкам (тот
             блок — выше, для таблиц С вкладками, см. ветку
             config.materials_tab == tab). Не показывается для ещё НЕ
             сохранённой записи — у specification позиции физически не
             могут существовать без specification_id (впрочем
             specification и так allow_create=False — этот случай сейчас
             не встречается на практике, проверка оставлена для общности
             примитива). -->
        <div x-show="!editing.id" class="materials-tab-hint">Позиции появятся после сохранения документа.</div>
        <div x-show="editing.id" x-cloak class="readonly-items-block">
          <table class="readonly-items-table">
            <thead>
              <tr>
                {% for field_name, col_label, col_format in config.readonly_items_columns %}
                <th>{{ col_label }}</th>
                {% endfor %}
              </tr>
            </thead>
            <tbody>
              <template x-for="row in readonlyItems" :key="row.id">
                <tr>
                  {% for field_name, col_label, col_format in config.readonly_items_columns %}
                  <td x-text="readonlyItemsColumnValue(row, '{{ field_name }}', '{{ col_format }}')"></td>
                  {% endfor %}
                </tr>
              </template>
            </tbody>
          </table>
          <div class="readonly-items-empty" x-show="readonlyItems.length === 0">Пока пусто — позиции не сформированы</div>
          {% if config.readonly_items_sum_field %}
          <div class="readonly-items-total">
            <span>Итого:</span>
            <span x-text="Number(editing['{{ config.readonly_items_sum_field }}'] ?? 0).toFixed(2)"></span>
          </div>
          {% endif %}
        </div>
        {% endif %}
        {% if config.invoice_items_tab %}
        <!-- Редактируемая (только колонка скидки) таблица строк счёта
             (TableConfig.invoice_items_tab, 2026-08-29) — параллельный
             аналог readonly_items_tab выше, см. подробный комментарий в
             app/engine/config.py. Не показывается для ещё не сохранённой
             записи — invoice сейчас allow_create=False (создаётся только
             кнопкой "Создать счёт" на спецификации), проверка оставлена
             для общности примитива, как и у readonly_items_tab. -->
        <div x-show="!editing.id" class="materials-tab-hint">Позиции появятся после сохранения документа.</div>
        <div x-show="editing.id" x-cloak class="readonly-items-block">
          <div class="materials-toolbar">
            <button type="button" class="btn btn-ghost" @click="invoiceItemsApplyBulkDiscount()">Дать скидку</button>
          </div>
          <table class="readonly-items-table invoice-items-table">
            <thead>
              <tr>
                {% for field_name, col_label, col_format in config.invoice_items_columns %}
                <th>{{ col_label }}</th>
                {% endfor %}
                <th>Ціна без ПДВ</th>
                <th>Знижка, %</th>
                <th>Ціна зі знижкою</th>
                <th>Сума без ПДВ</th>
              </tr>
            </thead>
            <tbody>
              <template x-for="row in readonlyItems" :key="row.id">
                <tr>
                  {% for field_name, col_label, col_format in config.invoice_items_columns %}
                  <td x-text="readonlyItemsColumnValue(row, '{{ field_name }}', '{{ col_format }}')"></td>
                  {% endfor %}
                  <td x-text="Number(row['{{ config.invoice_items_price_field }}'] ?? 0).toFixed(2)"></td>
                  <td>
                    <input type="number" step="0.01" class="invoice-discount-input"
                           x-model.number="row.{{ config.invoice_items_discount_field }}"
                           @change="invoiceItemDiscountChanged(row)">
                  </td>
                  <td x-text="Number(row['{{ config.invoice_items_price_after_discount_field }}'] ?? 0).toFixed(2)"></td>
                  <td x-text="Number(row['{{ config.invoice_items_line_total_field }}'] ?? 0).toFixed(2)"></td>
                </tr>
              </template>
            </tbody>
          </table>
          <div class="readonly-items-empty" x-show="readonlyItems.length === 0">Пока пусто — позиции не сформированы</div>
          {% if config.invoice_items_sum_field %}
          <div class="readonly-items-total">
            <span>Разом без ПДВ:</span>
            <span x-text="Number(editing['{{ config.invoice_items_sum_field }}'] ?? 0).toFixed(2)"></span>
          </div>
          {% endif %}
        </div>
        {% endif %}
        {% if config.extra_actions %}
        <div class="extra-actions" x-show="editing.id">
          {% for action_label in config.extra_actions %}
          <button type="button" class="btn btn-ghost" disabled title="Пока недоступно">{{ action_label }}</button>
          {% endfor %}
        </div>
        {% endif %}
        {% endif %}

        {% else %}
        <!-- hierarchy-таблица: три взаимоисключающих режима тела модалки,
             все собираются на JS из currentLevel(), т.к. открытый уровень
             дерева меняется динамически без перезагрузки страницы (Jinja
             form_layout вычислен только один раз при первом рендере
             страницы и не умеет "переключаться" вместе с drillPath). -->

        <!-- Режим 1: items_modal, СПИСОК состава (не форма редактирования
             самого узла) — используется kit. Показывается, когда открыта
             существующая запись (editing.id). "Редактировать" открывает
             MaterialPicker — отдельный полноэкранный экран (см. ниже),
             не режим внутри этой же модалки, как было раньше с формой
             добавления одной позиции. -->
        <template x-if="isItemsModal() && editing.id">
          <div>
            <div class="items-modal-list">
              <template x-for="item in kitItems" :key="item.id">
                <div class="items-modal-row">
                  <span x-text="itemsSourceRelationName('material_id', item.material_id)"></span>
                  <span class="items-modal-qty" x-text="Number(item.quantity ?? 0)"></span>
                </div>
              </template>
              <div class="items-modal-row items-modal-empty" x-show="kitItems.length === 0">Пока пусто — состав не заполнен</div>
            </div>
            <button type="button" class="btn items-modal-add-btn" @click="openMaterialPicker()">Редактировать</button>
          </div>
        </template>

        <!-- Режим 3: обычная hierarchy-модалка (kit_group/kit_section) —
             форма редактирования название+доп.поля, без списка состава.
             Также покрывает СОЗДАНИЕ нового kit (editing.id ещё нет —
             у новой записи не может быть состава, показывать список
             kit_items смысла нет, нужна обычная форма название+раздел). -->
        <template x-if="!isItemsModal() || !editing.id">
          <div>
            <template x-for="f in currentLevel().formLayoutFields" :key="f.name">
              <div class="field">
                <label x-text="f.label"></label>
                <input x-show="f.widget !== 'number'" type="text" :required="f.required"
                       :placeholder="f.placeholder" x-model="editing[f.name]">
                <input x-show="f.widget === 'number'" type="number" step="0.01" :required="f.required"
                       :placeholder="f.placeholder" x-model.number="editing[f.name]">
              </div>
            </template>
          </div>
        </template>
        {% endif %}
      </div>

      <div class="modal-footer">
        {% if not config.hierarchy %}
        {% if config.allow_delete %}
        <button type="button" class="btn btn-danger-ghost" x-show="editing.id" @click="remove()">
          {% if config.delete_mode == "soft" %}
          <span x-text="editing.is_deleted ? 'Отменить' : 'Удалить'"></span>
          {% else %}
          Удалить
          {% endif %}
        </button>
        {% else %}
        <span></span>
        {% endif %}
        <span x-show="!editing.id"></span>
        <div class="modal-footer-right">
          <button type="button" class="btn btn-ghost" @click="close()">Закрыть</button>
          <button type="button" class="btn btn-primary" @click="save()">Сохранить</button>
        </div>
        {% else %}
        <!-- items_modal, режим просмотра списка состава: единственная
             кнопка — закрыть (изменения состава идут через отдельный
             полноэкранный MaterialPicker, у него свои кнопки сохранения). -->
        <template x-if="isItemsModal() && editing.id">
          <div class="modal-footer-right" style="width:100%; justify-content:flex-end;">
            <button type="button" class="btn btn-ghost" @click="close()">Закрыть</button>
          </div>
        </template>
        <!-- обычная форма footer: kit_group/kit_section всегда, ЛИБО kit
             в момент СОЗДАНИЯ (editing.id ещё нет — форма название+
             раздел, не список состава, см. соответствующий режим тела
             модалки выше). -->
        <template x-if="!isItemsModal() || !editing.id">
          <div style="display:contents;">
            <button type="button" class="btn btn-danger-ghost" x-show="editing.id && currentLevel().allowDelete" @click="remove()">Удалить</button>
            <span x-show="!editing.id"></span>
            <div class="modal-footer-right">
              <button type="button" class="btn btn-ghost" @click="close()">Закрыть</button>
              <button type="button" class="btn btn-primary" @click="save()">Сохранить</button>
            </div>
          </div>
        </template>
        {% endif %}
      </div>
    </div>
  </div>

  <!-- ============================================================
       MaterialPicker — отдельный полноэкранный экран (НЕ часть modal-
       backdrop выше), открывается кнопкой "Редактировать" в модалке
       kit. Bottom sheet: верхняя зона "Отобрано" (черновик состава,
       в памяти экрана, ничего не сохраняется на сервере до нажатия
       финальной кнопки) + нижняя зона (поиск материалов, плоский
       список — без групп/дерева, см. HANDOFF_kits_and_calculation.md
       раздел 2.8-2.9). Между зонами — перетаскиваемая пальцем полоса
       (pickerSplit, 15%-85%, см. CSS .picker-handle).

       Кнопки "Отмена"/"Сохранить состав" — В ШАПКЕ, не в футере снизу.
       Раньше (v42-v46) они были в .picker-footer под обеими зонами и
       на реальном телефоне физически не попадали в видимую область —
       список результатов поиска снизу растягивал общую высоту
       содержимого больше, чем 100dvh, а .picker-footer, будучи
       ПОСЛЕДНИМ элементом flex-column, надёжно оказывался за пределами
       экрана (см. отчёт Вахтанга со скриншотом: кнопок не видно
       вообще). Шапка — единственная позиция, которая гарантированно
       остаётся на экране независимо от объёма контента ниже (она
       flex-shrink:0 и стоит ПЕРВОЙ, а не последней). -->
  <div class="picker-overlay" x-show="pickerOpen" x-cloak>
    <!-- Единый интерфейс подбора для kit, calculation-материалов И
         calculation-комплектов (pickerTarget: 'kit' | 'calculation' |
         'kits') — верхняя зона черновика (pickerDraft) + хэндл + нижняя
         зона подбора, с шапкой "Отмена"/"Сохранить состав". Нижняя зона
         РАЗНАЯ по содержимому в зависимости от pickerTarget: 'kit' и
         'calculation' — плоский поиск по материалам (см. ниже), 'kits' —
         дерево группа→раздел→комплект БЕЗ поиска (см. picker-kit-tree,
         2026-08-23, по прямой просьбе Вахтанга "экран подбора комплектов
         организован через иерархию так же, как экран комплектов").
         Верхняя зона черновика — ОБЩАЯ разметка для всех трёх целей:
         pickerRowLabel(row) возвращает название материала или комплекта
         в зависимости от того, что лежит в строке черновика. -->
    <div class="picker-top-actions">
      <button type="button" class="btn btn-ghost" @click="pickerCancel()">Отмена</button>
      <button type="button" class="btn btn-primary" @click="pickerSave()">Сохранить состав</button>
    </div>

    <div class="picker-pane picker-pane-top" :style="'flex: 0 0 ' + pickerSplit + '%;'">
      <div class="picker-pane-header">
        <span x-text="pickerDraft.length + ' позиций'"></span>
        <!-- Сумма без НДС по всем отобранным комплектам — ТОЛЬКО для
             pickerTarget==='kits' (2026-08-24, по прямой просьбе
             Вахтанга: "сверху в окне отобранных комплектов должна
             указываться сумма всего без НДС"). У материалов в этом же
             черновике цена/сумма не показывается — там цена всегда
             берётся заново из справочника при сохранении (replace_items
             сам проставляет актуальную material.price_excl_vat), а не
             считается заранее на клиенте. -->
        <span x-show="pickerTarget === 'kits'" x-text="'Итого без НДС: ' + pickerKitsTotal.toFixed(2)"></span>
      </div>
      <div class="picker-list">
        <template x-for="(row, idx) in pickerDraft" :key="row._key">
          <div class="picker-row">
            <!-- Клик по названию строки-комплекта открывает read-only
                 модалку состава (openKitDetail принимает любой объект с
                 .kit_id, тот же метод что и у сохранённого списка на
                 вкладке "Комплекты", 2026-08-24, по прямой просьбе:
                 "тапаю на отобранный комплект — должно открываться окно
                 с составом"). Для материалов (pickerTarget !== 'kits')
                 клика по названию нет — там своей детальной модалки не
                 предусмотрено. -->
            <span class="picker-row-name" :class="{'kit-row-clickable': pickerTarget === 'kits'}"
                  @click="pickerTarget === 'kits' && openKitDetail(row)" x-text="pickerRowLabel(row)"></span>
            <div class="picker-qty-control">
              <button type="button" class="picker-qty-btn" @click="pickerDecrement(idx)">−</button>
              <span class="picker-qty-value" x-text="row.quantity"></span>
              <button type="button" class="picker-qty-btn" @click="pickerIncrement(idx)">+</button>
            </div>
            <!-- Цена за единицу и сумма по строке — ТОЛЬКО для
                 pickerTarget==='kits' (2026-08-24). kitUnitPrice()
                 читает клиентский кэш (см. kitPriceCache в state) —
                 считается на лету по живому составу комплекта, т.к.
                 черновик ещё не сохранён на сервере и серверного
                 снэпшота для этих строк ещё не существует. -->
            <span class="picker-row-price" x-show="pickerTarget === 'kits'" x-text="kitUnitPrice(row.kit_id).toFixed(2)"></span>
            <span class="picker-row-sum" x-show="pickerTarget === 'kits'" x-text="(kitUnitPrice(row.kit_id) * Number(row.quantity ?? 0)).toFixed(2)"></span>
            <button type="button" class="picker-row-remove" @click="pickerRemoveRow(idx)">🗑</button>
          </div>
        </template>
        <div class="picker-row picker-row-empty" x-show="pickerDraft.length === 0">Пока ничего не выбрано</div>
      </div>
    </div>

    <div class="picker-handle" @pointerdown="pickerDragStart($event)"><div class="picker-handle-bar"></div></div>

    <div class="picker-pane picker-pane-bottom"
         :style="(pickerTarget !== 'kits' ? '' : 'display: none;') + 'flex: 0 0 ' + (100 - pickerSplit) + '%;'">
      <!-- ВАЖНО: display управляется ВНУТРИ :style, а не отдельным x-show
           (2026-08-24, найденный и исправленный баг "дерево комплектов
           пропадает при перетаскивании ползунка"). Разбирались с этим
           дважды: сначала ошибочно подозревали body-scroll/viewport dvh
           (v70), но проблема оказалась глубже — реальный баг Alpine.js в
           связке x-show + :style на одном элементе. Когда pickerSplit
           меняется (то есть человек тянет ползунок), Alpine пересчитывает
           :style ДАЖЕ у СКРЫТОГО x-show'ом элемента и полностью
           перезаписывает его атрибут style, СТИРАЯ "display: none",
           который до этого поставил x-show — а заново скрыть элемент
           x-show не может, потому что его выражение (pickerTarget !==
           'kits') не зависит от pickerSplit и поэтому не перезапускается.
           Итог: при первом же движении ползунка скрытая панель становится
           видимой и остаётся видимой поверх/рядом с нужной. Подтверждено
           изолированным воспроизведением на голом Alpine.js (10 строк, без
           остального кода приложения) — это не наша логика pickerTarget
           (она всё это время была верна), а особенность Alpine: :style
           полностью перезаписывает style-атрибут и не "помнит" про
           display, выставленный другим директивом. Фикс: display теперь
           часть ТОГО ЖЕ :style-выражения, что и flex — оба выставляются
           ОДНИМ и тем же вычислением, поэтому ничего не может друг друга
           затереть. Если добавляется третий такой parный блок где-то ещё
           в этом файле — та же ловушка, тот же фикс: display внутрь
           :style, отдельный x-show на такой элемент не вешать. -->
      <div class="picker-search-toggles">
        <label class="search-toggle-chip">
          <input type="checkbox" x-model="pickerSearchFields.short_name" @change="pickerSearch()">
          Short name
        </label>
        <label class="search-toggle-chip">
          <input type="checkbox" x-model="pickerSearchFields.full_name" @change="pickerSearch()">
          Full name
        </label>
        <label class="search-toggle-chip">
          <input type="checkbox" x-model="pickerSearchFields.sku_article" @change="pickerSearch()">
          Артикул производителя
        </label>
      </div>
      <div class="picker-search-row">
        <input type="text" class="picker-search-input" placeholder="Поиск по названию или артикулу…"
               x-model="pickerQuery" @input.debounce.300ms="pickerSearch()">
      </div>
      <div class="picker-brand-chips">
        <span class="chip" :class="{active: !pickerBrandFilter}" @click="pickerSetBrandFilter(null)">Все</span>
        <template x-for="b in pickerBrands" :key="b.id">
          <span class="chip" :class="{active: pickerBrandFilter === b.id}"
                @click="pickerSetBrandFilter(b.id)" x-text="b.name"></span>
        </template>
      </div>
      <div class="picker-search-results">
        <template x-for="mat in pickerResults" :key="mat.id">
          <!-- Тап по ВСЕЙ строке добавляет материал в черновик — та же
               логика, что и в v45 для drill-list: маленькая кнопка
               "+ Добавить" остаётся видимой как визуальный ориентир, но
               не единственный способ. -->
          <div class="picker-search-row-item" @click="pickerAddMaterial(mat)">
            <div class="picker-search-row-info">
              <span class="picker-search-row-name" x-text="mat.short_name"></span>
              <span class="picker-search-row-sub" x-text="materialBrandName(mat.brand_id) + (mat.sku_article ? ' · ' + mat.sku_article : '')"></span>
            </div>
            <button type="button" class="btn btn-primary picker-add-btn" @click.stop="pickerAddMaterial(mat)">+ Добавить</button>
          </div>
        </template>
        <div class="picker-search-row-item picker-row-empty" x-show="pickerResults.length === 0">Ничего не найдено</div>
      </div>
    </div>

    <!-- Нижняя зона подбора для pickerTarget==='kits' — ДЕРЕВО
         группа→раздел→комплект, БЕЗ поиска (прямое решение Вахтанга).
         Собственный маленький drill-стек (kitTreePath), НЕЗАВИСИМЫЙ от
         drillPath страницы (тот привязан к CONFIG.levels текущей
         hierarchy-страницы — здесь мы всегда листаем kit_group/
         kit_section/kit независимо от того, какая страница открыта).
         Тап по строке на уровне "группа"/"раздел" уходит вглубь дерева
         (kitTreeOpen), тап по строке на уровне "комплект" (последний,
         без дальнейшего drill) сразу добавляет его в черновик
         (pickerAddKit) — по прямой просьбе "при нажатии на комплект он
         выбирается и переносится в отобранные". -->
    <div class="picker-pane picker-pane-bottom" x-cloak
         :style="(pickerTarget === 'kits' ? '' : 'display: none;') + 'flex: 0 0 ' + (100 - pickerSplit) + '%;'">
      <!-- display внутри :style, а не отдельным x-show — см. подробное
           обоснование в комментарии у первого .picker-pane-bottom выше
           (материалы), это ровно тот же баг и тот же фикс, зеркально для
           комплектов. x-cloak оставлен как есть — он работает независимо
           (управляет ТОЛЬКО начальным !important до первого прохода
           Alpine, к раннее найденному багу отношения не имеет). -->
      <div class="picker-search-toggles">
        <button type="button" class="btn drill-back" x-show="kitTreePath.length > 0" @click="kitTreeBack()">‹</button>
        <!-- Хлебная крошка — кликабельные сегменты (2026-08-24, по
             прямой просьбе Вахтанга: "клик на хлебные крошки — переход
             на соответствующий раздел"). Последний сегмент (текущий
             экран) рендерится обычным текстом без клика — переходить
             никуда не нужно, он уже открыт. Разделитель "›" между
             сегментами не кликабелен, только сами названия. -->
        <span class="picker-kit-tree-crumb">
          <template x-for="(seg, idx) in kitTreeCrumbSegments()" :key="idx">
            <span>
              <span x-show="idx > 0" class="picker-kit-tree-crumb-sep">›</span>
              <span x-text="seg.label"
                    :class="{'picker-kit-tree-crumb-link': !seg.isCurrent}"
                    @click="!seg.isCurrent && kitTreeGoTo(seg.depth)"></span>
            </span>
          </template>
        </span>
      </div>
      <div class="picker-search-results">
        <template x-for="node in kitTreeNodes" :key="node.id">
          <div class="picker-search-row-item" @click="kitTreeNodeClick(node)">
            <div class="picker-search-row-info">
              <span class="picker-search-row-name" x-text="node.name"></span>
            </div>
            <span class="picker-kit-tree-arrow" x-show="kitTreePath.length < 2">›</span>
            <button type="button" class="btn btn-primary picker-add-btn" x-show="kitTreePath.length === 2" @click.stop="pickerAddKit(node)">+ Добавить</button>
          </div>
        </template>
        <div class="picker-search-row-item picker-row-empty" x-show="kitTreeNodes.length === 0">Пока пусто</div>
      </div>
    </div>
  </div>

  <!-- Модалка просмотра состава комплекта (вкладка "Комплекты"
       калькуляции, 2026-08-23) — открывается кликом по строке
       kitsItems (см. openKitDetail() в JS). ЧИСТО read-only: перечень
       материалов комплекта (кол-во, цена без НДС, сумма без НДС),
       итоговая сумма комплекта сверху — ничего внутри не
       редактируется (по прямому решению Вахтанга), состав комплекта
       правится отдельно на карточке самого kit. Не переиспользует
       общий .modal (та модалка привязана к editing/save() универсальной
       формы движка) — отдельный лёгкий оверлей поверх формы
       калькуляции. -->
  <div class="modal-backdrop" x-show="kitDetailOpen" x-cloak>
    <div class="modal">
      <div class="modal-header">
        <div>
          <h2 x-text="kitDetailName"></h2>
        </div>
      </div>

      <div class="materials-summary">
        <span>Сумма комплекта без НДС:</span>
        <span x-text="kitDetailTotal.toFixed(2)"></span>
      </div>
      <div class="materials-list">
        <template x-for="row in kitDetailItems" :key="row.id">
          <div class="materials-row">
            <div class="materials-row-info">
              <span class="materials-row-name" x-text="materialItemLabel(row.material_id)"></span>
              <span class="materials-row-unit" x-text="materialItemUnit(row.material_id)"></span>
            </div>
            <span class="picker-qty-value" x-text="row.quantity"></span>
            <span class="materials-row-price" x-text="Number(row.price_excl_vat ?? 0).toFixed(2)"></span>
            <span class="materials-row-sum" x-text="(Number(row.price_excl_vat ?? 0) * Number(row.quantity ?? 0)).toFixed(2)"></span>
          </div>
        </template>
        <div class="materials-row materials-row-empty" x-show="kitDetailItems.length === 0">Состав комплекта пуст</div>
      </div>

      <div class="modal-footer">
        <span></span>
        <div class="modal-footer-right">
          <button type="button" class="btn btn-ghost" @click="kitDetailOpen = false">Закрыть</button>
        </div>
      </div>
    </div>
  </div>
  {% endif %}

</div>

<script>
function showJsError(err) {
  var banner = document.getElementById('js-error-banner');
  if (banner) {
    banner.style.display = 'block';
    banner.textContent = (err && err.message) ? err.message : String(err);
  }
}

function hideJsError() {
  var banner = document.getElementById('js-error-banner');
  if (banner) { banner.style.display = 'none'; banner.textContent = ''; }
}

// Парсит {detail: "..."} из ответа FastAPI и возвращает читаемый
// текст, а не сырой JSON — FastAPI отдаёт наши HTTPException(422, ...)
// именно в таком виде.
async function extractErrorMessage(res) {
  let bodyText = '';
  try { bodyText = await res.text(); } catch (e) { /* тело недоступно */ }
  try {
    const parsed = JSON.parse(bodyText);
    if (parsed && typeof parsed.detail === 'string') return parsed.detail;
    if (parsed && parsed.detail) return JSON.stringify(parsed.detail);
  } catch (e) { /* не JSON — используем как есть */ }
  return 'Сервер ответил ' + res.status + (bodyText ? (': ' + bodyText) : '');
}

// Явные реализации формул пересчёта (без eval) — должны совпадать
// с app/engine/formulas.py на бэкенде. Единственная формула пока — "vat".
const ENGINE_FORMULAS = {
  vat: {
    forward: (a, rate) => Math.round(a * (1 + rate / 100) * 100) / 100,   // без НДС -> с НДС
    backward: (b, rate) => Math.round(b / (1 + rate / 100) * 100) / 100,  // с НДС -> без НДС
  }
};

function round2(value) {
  return Math.round((Number(value) || 0) * 100) / 100;
}

function applyFormula(formulaName, direction, value, rate) {
  const formula = ENGINE_FORMULAS[formulaName];
  if (!formula) { showJsError('Неизвестная формула: ' + formulaName); return value; }
  return formula[direction](value, rate);
}

// Клиентские action-обработчики (см. ActionButton.client_side в
// config.py) — считают результат ЦЕЛИКОМ в браузере, без похода на
// сервер, поэтому работают и для ещё НЕ сохранённой записи (нет
// editing.id). Каждая функция(editing, appState) -> patch-объект,
// подмешиваемый в editing, или null/undefined, если менять нечего.
//
// recalc_full_name — зеркало app/engine/name_template.py::
// render_name_template() на бэкенде. ДЕРЖАТЬ В СИНХРОНЕ: тот же набор
// плейсхолдеров, та же логика подстановки. Номер связанной заявки
// берётся не отдельным запросом к серверу, а из уже загруженного
// relationOptions['request_id'] (тот же список, что показывается в
// <select> поля "Заявка") — это единственная причина, по которой
// appState передаётся вторым аргументом.
const CLIENT_ACTIONS = {
  recalc_full_name(editing, appState) {
    const template = editing.name_template || '';
    let requestNumber = '';
    if (editing.request_id) {
      const requests = (appState && appState.relationOptions && appState.relationOptions.request_id) || [];
      const req = requests.find(r => r.id === editing.request_id);
      if (req) requestNumber = req.document_number || '';
    }
    const values = {
      client_name: editing.client_name || '',
      brand_slot: editing.brand_slot ? String(editing.brand_slot) : '',
      request_number: requestNumber,
    };
    let result = template;
    for (const key of Object.keys(values)) {
      result = result.split('{' + key + '}').join(values[key]);
    }
    return { full_name: result };
  },

  // brand_slot_labels — вызывается автоматически и при открытии формы
  // (см. openEdit()), и при каждой смене поля "Заявка" в открытой форме
  // (см. on_change_action у request_id в config.py) — работает
  // целиком на клиенте, без похода на сервер, поэтому одинаково и для
  // новой, и для уже сохранённой калькуляции (решение Вахтанга
  // 2026-08-22: в подавляющем большинстве случаев калькуляция делается
  // на основании заявки, значит бренды нужно видеть сразу как заявка
  // выбрана, а не только после сохранения). Требует TableConfig.
  // extra_lookups=["brand"] у таблицы (полный список брендов уже в
  // appState.relationOptions.brand — см. init() в page.py).
  brand_slot_labels(editing, appState) {
    const labels = {};
    if (!editing.request_id) return { brand_slot_labels: labels };
    const requests = (appState && appState.relationOptions && appState.relationOptions.request_id) || [];
    const brands = (appState && appState.relationOptions && appState.relationOptions.brand) || [];
    const req = requests.find(r => r.id === editing.request_id);
    if (!req) return { brand_slot_labels: labels };
    const slotFieldByNumber = { 1: 'brand_slot_1_id', 2: 'brand_slot_2_id', 3: 'brand_slot_3_id' };
    for (const [slot, field] of Object.entries(slotFieldByNumber)) {
      const brandId = req[field];
      if (!brandId) continue;
      const brand = brands.find(b => b.id === brandId);
      if (brand) labels[slot] = brand.name;
    }
    return { brand_slot_labels: labels };
  },
  // pick_final_total — переключатель "Способ расчёта стоимости"
  // (cost_method, calculation, 2026-08-27) — final_total должен
  // мгновенно обновляться при переключении radio "Наценка"/"По часам",
  // не дожидаясь клика "Пересчитать" (обнаружено Вахтангом: после
  // переключения radio "Итоговая стоимость" оставалась старым
  // значением, пока не нажата кнопка). Работает целиком на клиенте —
  // markup_total/hours_total уже посчитаны и лежат в editing (либо из
  // последнего "Пересчитать", либо из refresh_cost_totals при
  // открытии формы, см. open_edit_action), пересчитывать их заново не
  // нужно — только выбрать нужное значение под текущий cost_method.
  pick_final_total(editing) {
    const final_total = editing.cost_method === 'hours'
      ? Number(editing.hours_total ?? 0)
      : Number(editing.markup_total ?? 0);
    return { final_total };
  },
};

function enginePage() {
  const CONFIG = {{ config_json | safe }};
  // Нормализация: для плоской таблицы (hierarchyRoot=false) считаем,
  // что у неё один "уровень" — сама CONFIG — чтобы currentLevel()
  // работала одинаково в обоих режимах и остальной код (load/save/
  // remove/openEdit) не дублировался под каждый режим отдельно.
  const LEVELS = CONFIG.hierarchyRoot ? CONFIG.levels : [CONFIG];

  return {
    items: [],
    relationOptions: {},
    constants: {},
    activeFilters: {},
    searchFields: {},
    q: '',
    exactPrefix: false,
    chainReturnUrl: null,   // задаётся в maybeOpenById() из ?chain_request_id=
                             // (v74) — если страница открыта переходом со
                             // страницы "Цепочка документов", здесь URL для
                             // возврата туда; иначе остаётся null и кнопка
                             // "← К цепочке" в topbar не отображается.
    modalOpen: false,
    editing: {},
    // activeFormTab: индекс активной вкладки формы (0-based), только
    // для таблиц с CONFIG.formTabs непустым (см. TableConfig.form_tabs) —
    // сбрасывается на 0 при каждом openCreate()/openEdit(), чтобы форма
    // всегда открывалась на первой вкладке ("Основное"), а не на той,
    // что была активна в предыдущий раз, когда модалку закрыли.
    activeFormTab: 0,
    // --- Вкладка "Материалы" калькуляции (CONFIG.materialsTab,
    // 2026-08-23) — состав ТЕКУЩЕЙ открытой калькуляции (editing.id),
    // отдельно от items_modal/kitItems выше (другая модель хранения:
    // каждая позиция хранит СВОЙ снэпшот цены, не replace-all). ---
    materialsItems: [],
    readonlyItems: [],
    materialsSelectedIds: [],
    materialsMaterialOptions: [],
    materialsUnitOptions: [],
    get materialsTotal() {
      // Сумма без НДС по всем позициям — Σ(price_excl_vat × quantity),
      // цена берётся из СНЭПШОТА позиции (row.price_excl_vat), не live
      // из справочника material (см. HANDOFF: "именно так").
      return this.materialsItems.reduce(
        (sum, row) => sum + Number(row.price_excl_vat ?? 0) * Number(row.quantity ?? 0), 0
      );
    },
    // --- Вкладка "Комплекты" калькуляции (CONFIG.kitsTab, 2026-08-23) —
    // параллельный аналог вкладки "Материалы" выше: та же физическая
    // таблица calculation_item (см. CONFIG.kitsItemTableKey), позиции с
    // заполненным kit_id вместо material_id. price_excl_vat здесь —
    // снэпшот СУММЫ СОСТАВА комплекта, не цена самого Kit. ---
    kitsItems: [],
    kitsSelectedIds: [],
    kitsKitOptions: [],
    kitDetailOpen: false,
    kitDetailName: '',
    kitDetailItems: [],
    // --- Дерево подбора комплектов внутри picker'а (pickerTarget==='kits',
    // 2026-08-23) — собственный маленький drill-стек, НЕ переиспользует
    // drillPath/LEVELS страницы (те привязаны к CONFIG.levels ТЕКУЩЕЙ
    // hierarchy-страницы, а здесь мы всегда листаем kit_group/kit_section/
    // kit НЕЗАВИСИМО от того, какая страница сейчас открыта — форма
    // calculation сама по себе не hierarchy-страница). kitTreePath —
    // стек {id, name} узлов, длина 0 = список групп, 1 = список разделов
    // внутри группы, 2 = список комплектов внутри раздела (последний
    // уровень — тап по строке добавляет в черновик, а не углубляется
    // дальше). -->
    kitTreePath: [],
    kitTreeNodes: [],
    // kitPriceCache: kit_id -> цена за единицу (Σ kit_item.quantity ×
    // material.price_excl_vat), считается на лету на фронте для ЕЩЁ НЕ
    // сохранённого черновика picker'а (pickerTarget==='kits') — сервер
    // о черновике ничего не знает, пока не нажато "Сохранить состав", а
    // показать актуальную цену за единицу и сумму по строке в черновике
    // нужно сразу, без ожидания сохранения (2026-08-24, по прямой
    // просьбе Вахтанга: "цена за единицу и сумма должны быть видны в
    // самом отобранном списке комплектов"). Кэш по kit_id, не по строке
    // черновика — один и тот же комплект, добавленный дважды, не
    // запрашивает состав повторно.
    kitPriceCache: {},
    get kitsTotal() {
      // Сумма без НДС по всем отобранным комплектам — Σ(price_excl_vat ×
      // quantity), price_excl_vat — снэпшот суммы состава каждого
      // комплекта (не пересчитывается на лету из kit_item, см.
      // обоснование в app/models/calculation_item.py).
      return this.kitsItems.reduce(
        (sum, row) => sum + Number(row.price_excl_vat ?? 0) * Number(row.quantity ?? 0), 0
      );
    },
    get kitDetailTotal() {
      return this.kitDetailItems.reduce(
        (sum, row) => sum + Number(row.price_excl_vat ?? 0) * Number(row.quantity ?? 0), 0
      );
    },
    // --- Автопересчёт вкладки "Стоимость" калькуляции (2026-08-28) ---
    // Зеркало _recalc_cost_totals (app/engine/tables.py) на клиенте.
    // ЦЕЛИКОМ реактивно (computed-геттеры на materialsTotal/kitsTotal/
    // editing.*) — при любом изменении состава материалов/комплектов
    // (добавили строку, поправили quantity, удалили позицию) итоговая
    // стоимость на экране обновляется СРАЗУ, без похода на сервер и без
    // нажатия "Пересчитать". Кнопка "Пересчитать" по-прежнему нужна и
    // остаётся — она одна умеет подтянуть АКТУАЛЬНЫЕ цены из справочника
    // материалов (см. _recalc_material_prices_handler), чего клиент без
    // сетевого запроса сделать не может; этот блок лишь суммирует то,
    // что уже введено в строках на экране (снэпшоты), той же формулой.
    // ВАЖНО: при добавлении новых слагаемых в формулу на бэке (в
    // _recalc_cost_totals) — держать в синхроне и здесь, как и
    // recalc_full_name/render_name_template выше.
    get liveBaseTotal() {
      return round2(this.materialsTotal + this.kitsTotal);
    },
    get liveInsuredTotal() {
      const insuranceMarkup = Number(this.editing?.insurance_markup ?? 0);
      return round2(this.liveBaseTotal * insuranceMarkup);
    },
    get liveMarkupTotal() {
      const markupPercent = Number(this.editing?.markup_percent ?? 0);
      return round2(this.liveInsuredTotal * markupPercent);
    },
    get liveHourlyRate() {
      const rateId = this.editing?.product_type_rate_id;
      if (!rateId) return 0;
      const rates = (this.relationOptions && this.relationOptions.product_type_rate_id) || [];
      const rate = rates.find(r => r.id === rateId);
      return rate ? Number(rate.hourly_rate ?? 0) : 0;
    },
    get liveHoursTotal() {
      const assemblyHours = Number(this.editing?.assembly_hours ?? 0);
      return round2(this.liveInsuredTotal + assemblyHours * this.liveHourlyRate);
    },
    get liveFinalTotal() {
      return this.editing?.cost_method === 'hours' ? this.liveHoursTotal : this.liveMarkupTotal;
    },
    // Подмешивает свежепосчитанные значения в editing — вызывается из
    // x-effect на форме calculation (см. шаблон вкладки "Стоимость"),
    // а не из самих геттеров выше (геттеры только читают, не пишут),
    // чтобы поля editing.materials_total и т.д. отражались в
    // :value/x-model полей формы и уходили в БД при "Сохранить" ровно
    // тем же путём, что и после ручного "Пересчитать".
    applyLiveCostTotals() {
      if (!this.editing) return;
      this.editing.materials_total = round2(this.materialsTotal);
      this.editing.kits_total = round2(this.kitsTotal);
      this.editing.base_total = this.liveBaseTotal;
      this.editing.insured_total = this.liveInsuredTotal;
      this.editing.markup_total = this.liveMarkupTotal;
      this.editing.hours_total = this.liveHoursTotal;
      this.editing.final_total = this.liveFinalTotal;
    },
    // Начальная сортировка (v56) — из TableConfig.default_sort_field/
    // default_sort_dir, если задано (например request сортируется по
    // дате, новые сверху), иначе прежнее поведение (без сортировки).
    // Для hierarchy эта опция пока не используется (LEVELS[0] === CONFIG
    // для плоских таблиц — единственный случай, где default_sort_field
    // сейчас заполняется), поэтому берём из CONFIG напрямую, не из
    // currentLevel(), которая на момент инициализации ещё не нужна.
    sortBy: CONFIG.defaultSortField ?? null,
    sortDir: CONFIG.defaultSortDir ?? 'asc',
    page: 1,
    totalPages: 1,
    selectedIds: [],
    // --- items_modal (только для currentLevel().editMode === "items_modal",
    // сейчас это kit) ---
    // kitItems: состав ТЕКУЩЕГО открытого узла (editing.id), загружается
    // заново при каждом openEdit() — см. loadKitItems().
    kitItems: [],
    // itemRelationOptions: выпадающие списки/справочники, связанные с
    // items_modal (например список материалов, для отображения названий
    // в kitItems и для поиска внутри MaterialPicker) — отдельно от
    // relationOptions верхнего уровня, т.к. поля разных таблиц
    // (kit.formLayoutFields vs kit_item.itemsSource.formLayoutFields)
    // не должны путать друг друга при одинаковых именах полей.
    itemRelationOptions: {},
    // --- MaterialPicker (отдельный полноэкранный экран поверх modal-
    // backdrop, открывается кнопкой "Редактировать" в модалке kit, и
    // кнопкой "Добавить" на вкладке "Материалы" calculation) ---
    pickerOpen: false,
    // pickerTarget: 'kit' | 'calculation' — куда pickerSave() отправляет
    // финальный PUT .../items и куда pickerCancel()/pickerSave() должны
    // вернуть человека после закрытия (см. openMaterialPicker vs
    // openMaterialAdder). null — picker ещё не открывали в этой сессии.
    pickerTarget: null,
    // pickerDraft: черновик состава в памяти экрана, НЕ синхронизирован
    // с сервером до pickerSave(). Каждая строка {_key, material_id,
    // quantity} — _key нужен как стабильный :key для x-for (не material_id,
    // т.к. дубликаты material_id разрешены — см. HANDOFF раздел 2.9).
    pickerDraft: [],
    pickerDraftSeq: 0,
    pickerQuery: '',
    // pickerSearchFields/pickerBrandFilter/pickerBrands: те же
    // возможности поиска, что и в обычной плоской таблице материалов
    // (чекбоксы полей поиска + чипы брендов) — по прямой просьбе
    // "где фильтры по брендам, поиск по артикулу и все остальные
    // возможности поиска в плоской таблице". short_name включён по
    // умолчанию, full_name/sku_article выключены — те же дефолты, что
    // и у material_table в tables.py (search_default).
    pickerSearchFields: { short_name: true, full_name: false, sku_article: false },
    pickerBrandFilter: null,
    pickerBrands: [],
    pickerResults: [],
    // pickerSplit: процент высоты верхней зоны ("Отобрано"), диапазон
    // 15-85 — см. pickerDragStart/pickerDragMove, HANDOFF раздел 2.8.
    pickerSplit: 40,
    pickerDragging: false,
    pickerDragStartY: 0,
    pickerDragStartSplit: 40,
    pickerOverlayHeight: 0,
    // --- drill-down (только для CONFIG.hierarchyRoot) ---
    // drillPath: стек открытых узлов дерева НИЖЕ корневого уровня,
    // каждый элемент {parentId, label} — id открытой записи и её
    // название (для крошки). Длина drillPath == индекс текущего
    // уровня в LEVELS (drillPath.length === 0 -> LEVELS[0], корень).
    drillPath: [],

    currentLevel() {
      // Без фоллбэка на LEVELS[0]: если бы currentLevel() когда-нибудь
      // получил drillPath глубже, чем реально существующих уровней в
      // LEVELS, "тихий" откат на корень маскировал бы баг навигации —
      // человек увидел бы группы верхнего уровня внутри чужой крошки
      // и решил бы, что это отдельные записи (был реальный кейс).
      // Правильная защита — не пускать drillOpen() за пределы LEVELS
      // вообще (см. drillOpen ниже), тогда этот метод никогда не
      // получает валидный, но "пустой" индекс.
      return LEVELS[this.drillPath.length];
    },

    get hasNextLevel() {
      // true только если СЛЕДУЮЩИЙ уровень реально закодирован
      // (есть в LEVELS) — не просто "childKey указан в конфиге
      // текущего уровня". kit_section.hierarchy.childKey="kit" уже
      // заполнен сейчас, хотя kit ещё не реализован — childKey сам по
      // себе не гарантирует, что вглубь есть куда идти. Используется
      // и для стрелки в строке, и как часть проверки в drillOpen —
      // одно место истины вместо дублирования условия.
      const lvl = this.currentLevel();
      return !!(lvl.hierarchy && lvl.hierarchy.childKey && LEVELS[this.drillPath.length + 1]);
    },

    get drillCrumbs() {
      if (!CONFIG.hierarchyRoot) return [];
      const rootLabel = (LEVELS[0].hierarchy && LEVELS[0].hierarchy.rootLabel) || LEVELS[0].title;
      return [{ label: rootLabel }, ...this.drillPath.map(p => ({ label: p.label }))];
    },

    async init() {
      try {
        const lvl = this.currentLevel();
        for (const f of lvl.toggleableSearchFields) {
          // состояние чекбокса при первой загрузке — берётся из
          // search_default конкретного поля (см. FieldConfig); дальше
          // человек может переключать вручную, выбор держится, пока
          // страница открыта (не сбрасывается при новом поиске/фильтре).
          this.searchFields[f.name] = f.default;
        }
        for (const r of lvl.toggleableSearchRelations) {
          // то же самое, но для поиска по связанной таблице через
          // relation (например request.client_id -> искать среди
          // client.short_name/full_name) — см. Relation.searchable_fields.
          // Ключ в searchFields — с префиксом 'rel:', чтобы не
          // столкнуться с обычным полем с тем же именем.
          this.searchFields['rel:' + r.field] = r.default;
        }
        for (const rel of lvl.relations) {
          // page_size=1000 — выпадающему списку/фильтру нужен весь
          // справочник целиком, а не одна страница (см. решение по
          // пагинации: явный page_size приоритетнее default_page_size).
          const res = await fetch('/api/' + rel.target_table + '?page_size=1000');
          const data = await res.json();
          this.relationOptions[rel.field] = data.items;
          this.activeFilters[rel.field] = null;
        }
        for (const tableKey of (lvl.extraLookups || [])) {
          // Дополнительный справочник БЕЗ формального relation-поля
          // (см. TableConfig.extra_lookups) — ключ в relationOptions
          // здесь это имя таблицы (tableKey), а не имя поля формы, в
          // отличие от обычных relations выше; используется клиентской
          // JS-логикой напрямую (например поиск бренда по id для
          // подписи радиокнопки), не рендером <select>.
          const res = await fetch('/api/' + tableKey + '?page_size=1000');
          const data = await res.json();
          this.relationOptions[tableKey] = data.items;
        }
        // Подтягиваем constants, если таблице нужна хотя бы одна
        // "живая ссылка" — virtual-поле (например ставка НДС в
        // карточке материала) или computed pair со ставкой из
        // справочника, а не из собственного поля записи.
        const needsConstants = lvl.needsConstants || lvl.fields.some(f => f.virtual) ||
          lvl.computedPairs.some(p => p.rateConstantKey);
        if (needsConstants) {
          const res = await fetch('/api/constant?page_size=1000');
          const data = await res.json();
          for (const row of data.items) { this.constants[row.key] = row.value; }
        }
        if (CONFIG.renderMode === 'form') {
          // Форма-страница (v75, только для документов с ownPageUrl) —
          // список этой таблицы здесь не нужен вообще (в разметке его
          // нет), поэтому this.load() не вызываем — экономим один
          // запрос и не тратим время на пагинацию/сортировку, которые
          // здесь никак не используются. Открытие конкретной записи —
          // отдельным путём (maybeOpenOwnPage читает id из URL и сама
          // при необходимости догружает запись через GET /api/{key}/{id}).
          await this.maybeOpenOwnPage();
        } else {
          await this.load();
          await this.maybeOpenFromRequest();
        }
        // Блокировка скролла <body> пока открыт picker-overlay или
        // обычная модалка (2026-08-24) — без этого перетаскивание
        // хэндла picker'а (.picker-handle, pickerDragStart) может
        // "провалиться" сквозь position:fixed оверлей и проскроллить
        // страницу ПОД ним: на мобильном Chrome это заставляет адресную
        // строку выехать обратно на экран (native-поведение браузера,
        // не наше), что на живом устройстве Вахтанг наблюдал как
        // "дерево комплектов пропадает при перетаскивании ползунка" —
        // после скролла тела страницы под фиксированным оверлеем layout
        // окна меняется (100dvh пересчитывается по новому видимому
        // viewport'у). lockBodyScroll()/unlockBodyScroll() — не просто
        // toggle класса, а сохранение/восстановление scrollY, иначе
        // position:fixed на body визуально "подбрасывает" страницу
        // наверх в момент блокировки и роняет её при снятии.
        this.$watch('pickerOpen', open => this.updateBodyScrollLock(open || this.modalOpen));
        this.$watch('modalOpen', open => this.updateBodyScrollLock(open || this.pickerOpen));
      } catch (err) { showJsError(err); }
    },

    // scrollLockY: запомненная позиция скролла страницы НА МОМЕНТ
    // блокировки — нужна, чтобы снять блокировку ровно в ту же точку
    // (position:fixed на body сам по себе не помнит, откуда его
    // "зафиксировали").
    scrollLockY: 0,

    updateBodyScrollLock(shouldLock) {
      const alreadyLocked = document.body.classList.contains('body-scroll-locked');
      if (shouldLock && !alreadyLocked) {
        this.scrollLockY = window.scrollY || window.pageYOffset || 0;
        document.body.style.top = '-' + this.scrollLockY + 'px';
        document.body.classList.add('body-scroll-locked');
      } else if (!shouldLock && alreadyLocked) {
        document.body.classList.remove('body-scroll-locked');
        document.body.style.top = '';
        window.scrollTo(0, this.scrollLockY);
      }
    },

    async maybeOpenFromRequest() {
      // Подхватывает ?from_request={id} в адресе страницы (v62) —
      // редирект сюда делает createChildDocument() со страницы заявок
      // ("Создать документ на основании"). Работает для ЛЮБОЙ таблицы
      // с полем "request_id" в форме (сейчас единственная — calculation),
      // не хардкод под неё по имени таблицы — так тот же путь
      // переиспользуется, если в будущем у другого документа тоже
      // появится request_id. Если параметра нет в адресе — ничего не
      // делает, обычная загрузка страницы не затронута.
      const params = new URLSearchParams(window.location.search);
      const requestId = params.get('from_request');
      if (!requestId) return;
      const lvl = this.currentLevel ? this.currentLevel() : null;
      const hasRequestField = lvl && lvl.fields.some(f => f.name === 'request_id');
      if (!hasRequestField) return;
      // Убираем параметр из адресной строки сразу — иначе повторное
      // открытие формы (закрыть/создать новую вручную) снова подставило
      // бы ту же заявку при каждой перезагрузке страницы.
      window.history.replaceState({}, '', window.location.pathname);
      await this.openCreate();
      this.editing.request_id = Number(requestId);
      await this.runAction('brand_slot_labels');
    },

    async maybeOpenOwnPage() {
      // Открывает форму на СВОЕЙ отдельной странице (v75) — вызывается
      // из init() ТОЛЬКО когда CONFIG.renderMode === 'form' (список в
      // разметке этой страницы вообще отсутствует, см. render_mode в
      // page.py). Последний сегмент пути — "new" (создание) или
      // числовой id (редактирование). ?chain_request_id= в query —
      // опциональный, только чтобы показать кнопку "← К цепочке" в
      // topbar формы, если сюда пришли со страницы "Цепочка документов"
      // (app/documents_chain/) — не путать с самим путём, который
      // всегда указывает конкретный документ.
      const params = new URLSearchParams(window.location.search);
      const chainRequestId = params.get('chain_request_id');
      if (chainRequestId) {
        this.chainReturnUrl = '/documents-chain?request_id=' + encodeURIComponent(chainRequestId);
      }
      const segments = window.location.pathname.split('/').filter(Boolean);
      const last = segments[segments.length - 1];
      if (last === 'new') {
        // Приоритет источников предзаполнения при создании (v75):
        // 1) ?from_request= — переход по кнопке "Создать документ на
        //    основании" с другого документа (см. createChildDocument()),
        //    2) sessionStorage-префилл от copySelected() на списке,
        //    3) обычное пустое создание.
        const params = new URLSearchParams(window.location.search);
        if (params.get('from_request')) {
          await this.maybeOpenFromRequest();
          return;
        }
        const prefillKey = 'engineCopyPrefill:' + this.currentLevel().key;
        const prefillRaw = sessionStorage.getItem(prefillKey);
        if (prefillRaw) {
          sessionStorage.removeItem(prefillKey);
          try {
            const prefill = JSON.parse(prefillRaw);
            await this.openCreate();
            this.editing = { ...this.editing, ...prefill };
            return;
          } catch (e) { /* испорченные данные — откатываемся на обычное создание ниже */ }
        }
        await this.openCreate();
        return;
      }
      const id = Number(last);
      if (!Number.isFinite(id)) {
        showJsError('Некорректный адрес документа.');
        return;
      }
      // Запись могла не попасть в уже загруженную первую страницу
      // списка (сортировка/фильтры/пагинация) — сначала пробуем найти
      // среди того, что уже загружено (частый случай — только что
      // созданный документ, "свежие сверху"), иначе точечно
      // догружаем именно эту запись отдельным запросом по id (см.
      // GET /api/{key}/{id}, добавлен для этого в v74).
      let item = this.items.find(i => i.id === id);
      if (!item) {
        try {
          const res = await fetch('/api/' + this.currentLevel().key + '/' + id);
          if (res.ok) item = await res.json();
        } catch (e) { /* см. ниже — покажем ошибку, если так и не нашли */ }
      }
      if (!item) {
        showJsError('Документ #' + id + ' не найден.');
        return;
      }
      await this.openEdit(item);
    },

    openDocumentRow(item) {
      // Клик по строке в СПИСКЕ (v75) — на плоских таблицах с
      // собственной формой (CONFIG.ownPageUrl задан, см. TableConfig.
      // own_page_url) переходит на её страницу вместо открытия модалки
      // на месте; полная перезагрузка, тот же принцип, что и остальная
      // навигация между страницами движка. Если own_page_url не задан
      // (тип документа ещё не переведён на отдельные страницы) —
      // старое поведение, модалка на этой же странице, для обратной
      // совместимости.
      if (CONFIG.ownPageUrl) {
        window.location.href = CONFIG.ownPageUrl + '/' + item.id;
        return;
      }
      this.openEdit(item);
    },

    openCreateRow() {
      // Кнопка "+ Запись" в СПИСКЕ (v75) — аналогично openDocumentRow(),
      // но для создания новой записи (own_page_url + "/new").
      if (CONFIG.ownPageUrl) {
        window.location.href = CONFIG.ownPageUrl + '/new';
        return;
      }
      this.openCreate();
    },

    closeToList() {
      // "Закрыть"/после "Сохранить"/после "Удалить" — на ФОРМЕ-странице
      // (CONFIG.renderMode === 'form') уходит НАЗАД на список, а не
      // просто скрывает модалку (которой на этой странице в разметке
      // нет вообще, см. render_mode в page.py). history.back() —
      // человек мог попасть на форму из своего родного списка ИЛИ из
      // страницы "Цепочка документов" (app/documents_chain/): в обоих
      // случаях "назад" ведёт туда, откуда реально пришли, без
      // жёсткого хардкода одного конкретного URL возврата.
      if (window.history.length > 1) {
        window.history.back();
      } else {
        window.location.href = CONFIG.ownPageUrl || '/';
      }
    },

    relationName(fieldName, id) {
      const rel = this.currentLevel().relations.find(r => r.field === fieldName);
      if (!rel) return '';
      const opts = this.relationOptions[fieldName] || [];
      const found = opts.find(o => o.id === id);
      return found ? found[rel.display_field] : '';
    },

    optionLabel(fieldName, value) {
      // Русская подпись для полей со статичным списком опций
      // (FieldConfig.options, например Calculation.status) — аналог
      // relationName(), но без обращения к relationOptions/API, т.к.
      // список опций целиком приходит уже в CONFIG.fields.
      const f = this.currentLevel().fields.find(x => x.name === fieldName);
      if (!f || !f.options) return value ?? '';
      const found = f.options.find(([v]) => v === value);
      return found ? found[1] : (value ?? '');
    },

    onSearchFieldsChange() {
      try { this.page = 1; this.load(); } catch (err) { showJsError(err); }
    },

    toggleSort(fieldName) {
      // Клик по тому же заголовку — переключает направление
      // (asc → desc → asc...). Клик по другому заголовку — сортирует
      // по нему заново, всегда начиная с asc.
      try {
        if (this.sortBy === fieldName) {
          this.sortDir = this.sortDir === 'asc' ? 'desc' : 'asc';
        } else {
          this.sortBy = fieldName;
          this.sortDir = 'asc';
        }
        this.page = 1;
        this.load();
      } catch (err) { showJsError(err); }
    },

    async load() {
      try {
        const lvl = this.currentLevel();
        const params = new URLSearchParams();
        if (this.q) params.set('q', this.q);
        if (this.exactPrefix) params.set('exact_prefix', 'true');
        if (lvl.toggleableSearchFields.length > 0 || lvl.toggleableSearchRelations.length > 0) {
          // Явно передаём набор активных полей поиска — какие из
          // toggleable-полей отмечены галочкой + всегда-искомые поля
          // (searchable=True, search_toggle=False, например артикул).
          for (const f of lvl.toggleableSearchFields) {
            if (this.searchFields[f.name]) params.append('search_fields', f.name);
          }
          for (const name of lvl.alwaysSearchedFields) {
            params.append('search_fields', name);
          }
          for (const r of lvl.toggleableSearchRelations) {
            if (this.searchFields['rel:' + r.field]) params.append('search_fields', 'rel:' + r.field);
          }
          for (const fieldName of lvl.alwaysSearchedRelationFields) {
            params.append('search_fields', 'rel:' + fieldName);
          }
        }
        for (const [field, value] of Object.entries(this.activeFilters)) {
          if (value !== null && value !== undefined) params.set(field, value);
        }
        if (this.sortBy) {
          params.set('sort_by', this.sortBy);
          params.set('sort_dir', this.sortDir);
        } else if (CONFIG.defaultSortFields && CONFIG.defaultSortFields.length > 0) {
          // Сортировка по нескольким полям сразу (например у calculation:
          // сначала document_date, потом document_time — "новые сверху",
          // см. TableConfig.default_sort_fields) — применяется только пока
          // человек НЕ кликнул по заголовку колонки вручную (sortBy пуст);
          // однополейный sortBy/sortDir выше имеет приоритет, как обычно.
          params.set('sort_fields', JSON.stringify(CONFIG.defaultSortFields));
        }
        // drill-down: текущий узел дерева фильтруется по родителю —
        // id последнего элемента drillPath (родитель уровня, который
        // сейчас открыт). На корневом уровне (drillPath пуст) parent_id
        // не передаётся — таблица верхнего уровня (kit_group) ни от
        // кого не зависит.
        if (CONFIG.hierarchyRoot && this.drillPath.length > 0) {
          params.set('parent_id', this.drillPath[this.drillPath.length - 1].parentId);
        }
        params.set('page', this.page);
        const res = await fetch('/api/' + lvl.key + '?' + params.toString());
        const data = await res.json();
        this.items = data.items;
        this.page = data.page;
        this.totalPages = data.total_pages;
        // Выделение — про конкретные видимые строки; при перезагрузке
        // списка (смена страницы/поиска/фильтра/сортировки) старые
        // выделенные id могут больше не быть на экране — сбрасываем,
        // чтобы тулбар не показывал "выделено N" для невидимых строк.
        this.selectedIds = [];
      } catch (err) { showJsError(err); }
    },

    prevPage() {
      if (this.page > 1) { this.page -= 1; this.load(); }
    },

    nextPage() {
      if (this.page < this.totalPages) { this.page += 1; this.load(); }
    },

    async openCreate() {
      try {
        hideJsError();
        const lvl = this.currentLevel();
        const relationFieldNames = new Set(lvl.relations.map(r => r.field));
        const blank = {};
        for (const f of lvl.fields) {
          if (f.inForm === false) {
            // Поле не показывается в форме (например Calculation.status
            // — статус проставляется точкой в списке, не полем формы) —
            // не отправляем на сервер вообще, чтобы сработал
            // default модели/default_factory, а не пустая строка.
            continue;
          }
          if (relationFieldNames.has(f.name)) {
            // relation-поле (select, ссылка на другую таблицу) — блан
            // должен быть null, не '', иначе на Postgres (прод) пустая
            // строка в integer-колонке падает ошибкой БД при сохранении
            // (см. _normalize_relation_fields в api.py — подчищает то
            // же самое на бэкенде как отдельная линия защиты, но здесь
            // правильнее не производить '' вообще).
            if (f.defaultFirstOption) {
              // См. FieldConfig.default_first_option в config.py —
              // подставляем id первой записи связанной таблицы вместо
              // null, если список опций уже загружен и непуст.
              const options = (this.relationOptions && this.relationOptions[f.name]) || [];
              blank[f.name] = options.length > 0 ? options[0].id : (f.default ?? null);
            } else {
              blank[f.name] = f.default ?? null;
            }
          } else if (f.defaultFromConstant && this.constants[f.defaultFromConstant] !== undefined) {
            // Динамический default из справочника constant (см.
            // FieldConfig.default_from_constant) — приоритетнее
            // статичного f.default, но только если constant реально
            // загружен и ключ там есть; иначе падаем на обычные ветки
            // ниже (статичный default как fallback).
            blank[f.name] = this.constants[f.defaultFromConstant];
          } else if (f.widget === 'date' && (f.default === null || f.default === undefined)) {
            // date-поле без явного default — подставляем сегодняшнюю
            // дату сразу на фронте (видно человеку сразу при открытии
            // формы), бэкенд всё равно перепроверит/дозаполнит своим
            // default_factory, если поле придёт пустым (см.
            // _normalize_date_fields в api.py).
            const today = new Date();
            const pad = (n) => String(n).padStart(2, '0');
            blank[f.name] = `${today.getFullYear()}-${pad(today.getMonth() + 1)}-${pad(today.getDate())}`;
          } else if (f.widget === 'time' && (f.default === null || f.default === undefined)) {
            // time-поле без явного default (Calculation.document_time,
            // v57) — та же логика, что и у date выше: подставляем
            // текущее время сразу на фронте, бэкенд перепроверит своим
            // default_factory через _normalize_time_fields в api.py.
            const now = new Date();
            const pad = (n) => String(n).padStart(2, '0');
            blank[f.name] = `${pad(now.getHours())}:${pad(now.getMinutes())}`;
          } else if (f.default !== null && f.default !== undefined) {
            blank[f.name] = f.default;
          } else {
            blank[f.name] = f.isNumeric ? 0 : '';
          }
        }
        // drill-down: новая запись, создаваемая внутри открытого узла,
        // должна сразу ссылаться на своего родителя (например новый
        // kit_section, созданный внутри группы 5, получает
        // kit_group_id=5) — иначе она "потеряется" вне текущего узла
        // сразу после создания (список отфильтрован по parent_id).
        if (CONFIG.hierarchyRoot && this.drillPath.length > 0 && lvl.hierarchy && lvl.hierarchy.parentField) {
          blank[lvl.hierarchy.parentField] = this.drillPath[this.drillPath.length - 1].parentId;
        }
        this.editing = blank;
        this.modalOpen = true;
        this.activeFormTab = 0;
        if (lvl.documentNumberField) {
          // Показываем человеку номер СРАЗУ при открытии формы, а не
          // только после сохранения — иначе поле выглядит "сломанным"
          // (пустое там, где ожидается автономер). Не резервирует номер —
          // реальный номер присваивается на save (см. _apply_document_numbering
          // в api.py); это просто предпросмотр (GET /api/{key}/next-document-number).
          try {
            const res = await fetch('/api/' + lvl.key + '/next-document-number');
            if (res.ok) {
              const data = await res.json();
              this.editing[lvl.documentNumberField] = data.document_number;
            }
          } catch (e) { /* не критично — поле останется пустым, сервер всё равно сгенерирует номер на save */ }
        }
      } catch (err) { showJsError(err); }
    },

    async openEdit(item) {
      try {
        hideJsError();
        this.editing = { ...item };
        this.modalOpen = true;
        this.activeFormTab = 0;
        if (this.isItemsModal()) {
          this.loadKitItems();
        }
        if (CONFIG.materialsTab && this.editing.id) {
          this.loadMaterialsItems();
        }
        if (CONFIG.kitsTab && this.editing.id) {
          this.loadKitsItems();
        }
        if (CONFIG.readonlyItemsTab && this.editing.id) {
          this.loadReadonlyItems();
        }
        if (CONFIG.invoiceItemsTab && this.editing.id) {
          this.loadReadonlyItems();
        }
        // Автозагрузка динамических подписей для radio-полей (см.
        // FieldConfig.radio_labels_field/radio_labels_action в
        // config.py) — переиспользует runAction(), поэтому идёт по
        // клиентскому пути без похода на сервер, если действие
        // зарегистрировано в CLIENT_ACTIONS (см. page.py), иначе — по
        // старому серверному пути. Вызывается сразу при открытии формы,
        // без клика человека. Молча пропускается, если у таблицы нет ни
        // одного radio-поля с radio_labels_action (обычный случай для
        // всех таблиц кроме calculation).
        const lvl = this.currentLevel ? this.currentLevel() : null;
        const radioActions = lvl ? lvl.fields.filter(f => f.widget === 'radio' && f.radioLabelsAction) : [];
        for (const f of radioActions) {
          await this.runAction(f.radioLabelsAction);
        }
        // Автовызов CONFIG.openEditAction (TableConfig.open_edit_action,
        // 2026-08-27) — то же место в цикле открытия формы, что и у
        // radioActions выше, но не привязано к конкретному полю: у
        // calculation используется для refresh_cost_totals, чтобы
        // вкладка "Стоимость" показывала актуальные суммы сразу при
        // открытии, без обязательного клика "Пересчитать" (см.
        // _refresh_cost_totals_handler в tables.py).
        if (CONFIG.openEditAction && this.editing.id) {
          await this.runAction(CONFIG.openEditAction);
        }
      } catch (err) { showJsError(err); }
    },

    async runAction(action) {
      // Вызывает именованное действие с реальной логикой — либо
      // ЦЕЛИКОМ в браузере (CLIENT_ACTIONS, см. ниже — action
      // помечен client_side=True в TableConfig.action_buttons),
      // либо на бэкенде (см. TableConfig.action_handlers в
      // config.py): POST /api/{key}/{id}/actions/{action}, результат
      // подмешивается в открытую форму (editing) без закрытия
      // модалки и без отдельного save() — человек видит эффект сразу
      // и может поправить получившееся значение вручную перед
      // сохранением.
      try {
        hideJsError();
        const clientFn = CLIENT_ACTIONS[action];
        if (clientFn) {
          // Клиентское действие — не требует editing.id, работает
          // одинаково и для новой, и для уже сохранённой записи (см.
          // FieldConfig.hint у name_template и решение Вахтанга
          // 2026-08-22 — "Сформировать название" должно работать
          // сразу, без обязательного сохранения).
          const patch = clientFn(this.editing, this);
          if (patch) this.editing = { ...this.editing, ...patch };
          return;
        }
        if (!this.editing.id) {
          showJsError('Сначала сохраните запись — действие доступно только для уже сохранённых.');
          return;
        }
        const res = await fetch(`/api/${this.currentLevel().key}/${this.editing.id}/actions/${action}`, { method: 'POST' });
        if (!res.ok) { showJsError(await res.text()); return; }
        const data = await res.json();
        // redirect_url (2026-08-27, введено для "Спецификация" у
        // request) — действие СОЗДАЁТ ДРУГОЙ документ (не правит
        // текущую запись), поэтому вместо обычного подмешивания
        // результата в editing текущей формы уходим на страницу
        // созданного документа. Универсальный контракт — любой
        // action_handler может вернуть {"redirect_url": "..."} вместо
        // обычного патча полей, ничего не хардкодится под конкретную
        // таблицу/действие.
        if (data && data.redirect_url) {
          window.location.href = data.redirect_url;
          return;
        }
        this.editing = { ...this.editing, ...data };
      } catch (err) { showJsError(err); }
    },

    // --- items_modal (kit: модалка состава вместо формы редактирования) ---

    isItemsModal() {
      // Раньше вызова currentLevel() у плоских таблиц (CONFIG.hierarchyRoot
      // === false) не бывает — там всегда обычная модалка (снаружи есть
      // серверная развилка на верхнем уровне шаблона), но на всякий
      // случай не падаем, если currentLevel() вернёт undefined (drillPath
      // временно не совпадает с LEVELS в момент между двумя load()).
      const lvl = this.currentLevel ? this.currentLevel() : null;
      return !!(lvl && lvl.editMode === 'items_modal');
    },

    async loadKitItems() {
      // Загружает состав ТЕКУЩЕГО открытого комплекта (editing.id) через
      // тот же универсальный parent_id-механизм, что и drill-down между
      // уровнями дерева (см. app/engine/api.py list_items) — kit_item
      // не уровень дерева, но hierarchy.parent_field у него задан именно
      // ради этого переиспользования.
      try {
        hideJsError();
        const src = this.currentLevel().itemsSource;
        const params = new URLSearchParams();
        params.set('parent_id', this.editing.id);
        params.set('page_size', 1000);
        const res = await fetch('/api/' + src.key + '?' + params.toString());
        const data = await res.json();
        this.kitItems = data.items;
        // подтягиваем опции материалов для отображения названия в списке
        // (itemsSourceRelationName/materialLabel) — используется и списком
        // состава в модалке, и MaterialPicker (поиск/подписи выбранных
        // строк), грузим один раз при открытии модалки kit.
        for (const rel of src.relations) {
          if (rel.field === 'kit_id') continue; // kit_id проставляется автоматически, select для него не нужен
          const optRes = await fetch('/api/' + rel.target_table + '?page_size=1000');
          const optData = await optRes.json();
          this.itemRelationOptions[rel.field] = optData.items;
        }
      } catch (err) { showJsError(err); }
    },

    itemsSourceRelationFor(fieldName) {
      const src = this.currentLevel().itemsSource;
      return src.relations.find(r => r.field === fieldName) || null;
    },

    itemsSourceRelationName(fieldName, id) {
      const rel = this.itemsSourceRelationFor(fieldName);
      if (!rel) return '';
      const opts = this.itemRelationOptions[fieldName] || [];
      const found = opts.find(o => o.id === id);
      return found ? found[rel.display_field] : '';
    },

    // --- MaterialPicker: отдельный полноэкранный экран для редактирования
    // состава kit (см. HANDOFF_kits_and_calculation.md, разделы 2.8-2.9).
    // Открывается кнопкой "Редактировать" в модалке kit, закрывается
    // либо отменой (черновик отбрасывается), либо сохранением (полная
    // замена состава на сервере через PUT /api/kit/{id}/items). -->

    materialLabel(materialId) {
      // Единый источник подписи для черновика picker'а (pickerDraft) —
      // используется ОБОИМИ pickerTarget ('kit' и 'calculation').
      // itemRelationOptions['material_id'] — кэш кита (заполняется при
      // loadKitItems), materialsMaterialOptions — кэш калькуляции
      // (заполняется при loadMaterialsItems) — проверяем оба, т.к.
      // предзаполнение черновика может ссылаться на материал, который
      // есть только в одном из них.
      const kitOpts = this.itemRelationOptions['material_id'] || [];
      const found = kitOpts.find(o => o.id === materialId) ||
        this.materialsMaterialOptions.find(o => o.id === materialId);
      return found ? found.short_name : '';
    },

    pickerRowLabel(row) {
      // Общая подпись строки черновика для ЛЮБОГО pickerTarget —
      // ветвится по тому, что заполнено в строке (2026-08-23, вместе с
      // добавлением pickerTarget==='kits'): kit_id -> название комплекта
      // (kitItemLabel, тот же кэш kitsKitOptions, что и у списка на
      // вкладке "Комплекты"), иначе -> материал (materialLabel, как
      // раньше).
      if (row.kit_id) return this.kitItemLabel(row.kit_id);
      return this.materialLabel(row.material_id);
    },

    async openMaterialPicker() {
      try {
        hideJsError();
        // Предзаполнение: черновик стартует с текущим составом kit
        // (kitItems уже загружены при openEdit/loadKitItems), не с
        // пустого списка — человек правит существующие позиции наравне
        // с новыми (см. решение 2026-08-18).
        this.pickerDraft = this.kitItems.map(item => ({
          _key: 'existing-' + item.id,
          material_id: item.material_id,
          quantity: Number(item.quantity ?? 1),
        }));
        this.pickerDraftSeq = this.pickerDraft.length;
        this.pickerTarget = 'kit';
        this.pickerQuery = '';
        this.pickerSearchFields = { short_name: true, full_name: false, sku_article: false };
        this.pickerBrandFilter = null;
        this.pickerResults = [];
        this.pickerSplit = 40;
        // Модалка kit закрывается — MaterialPicker открывается ВМЕСТО
        // неё, не поверх (см. HANDOFF, раздел 2.9: "клик «Редактировать»
        // закрывает модалку, открывается MaterialPicker на весь экран").
        // Раньше modalOpen не трогался, из-за чего модалка оставалась
        // открытой (затемнённым фоном) под пикером — баг, замеченный
        // Вахтангом на скриншоте: "открытое окно всё равно не ушло".
        this.modalOpen = false;
        this.pickerOpen = true;
        // Список брендов для чипов-фильтров — те же данные, что и у
        // обычной таблицы материалов (relationOptions['brand_id']), но
        // грузим отдельно и кэшируем в pickerBrands (не завязано на то,
        // открыта ли сейчас страница material-v2).
        if (this.pickerBrands.length === 0) {
          const res = await fetch('/api/brand?page_size=1000');
          const data = await res.json();
          this.pickerBrands = data.items;
        }
        // Список виден сразу при открытии, как в обычной плоской
        // таблице материалов (не только после ввода текста в поиск) —
        // по прямой просьбе "интерфейс подбора такой же, как у обычных
        // таблиц плоских".
        this.pickerSearch();
      } catch (err) { showJsError(err); }
    },

    // --- Вкладка "Материалы" калькуляции (calculation, 2026-08-23) ---
    // По прямому решению Вахтанга кнопка "Добавить" открывает ТОТ ЖЕ
    // самый picker-интерфейс, что и MaterialPicker кита (верхняя зона
    // "черновик" + хэндл + нижняя зона поиска), а не урезанный вариант
    // "тап = сразу на сервер". Полная замена состава по кнопке
    // "Сохранить состав" (см. pickerSave ниже — общий метод для обоих
    // pickerTarget). Единственное архитектурное отличие calculation от
    // kit — цена: replace_items на бэке при каждом сохранении состава
    // проставляет ТЕКУЩУЮ material.price_excl_vat всем строкам заново
    // (решение Вахтанга: "цена берётся в момент каждого сохранения
    // состава" — старый снэпшот при полной замене не сохраняется).
    async openMaterialAdder() {
      try {
        hideJsError();
        // Предзаполнение из ТЕКУЩИХ calculation_item (materialsItems уже
        // загружены при openEdit/loadMaterialsItems) — та же логика
        // предзаполнения, что и у openMaterialPicker() для kit.
        this.pickerDraft = this.materialsItems.map(item => ({
          _key: 'existing-' + item.id,
          material_id: item.material_id,
          quantity: Number(item.quantity ?? 1),
        }));
        this.pickerDraftSeq = this.pickerDraft.length;
        this.pickerTarget = 'calculation';
        this.pickerQuery = '';
        this.pickerSearchFields = { short_name: true, full_name: false, sku_article: false };
        this.pickerBrandFilter = null;
        this.pickerResults = [];
        this.pickerSplit = 40;
        this.modalOpen = false;
        this.pickerOpen = true;
        if (this.pickerBrands.length === 0) {
          const res = await fetch('/api/brand?page_size=1000');
          const data = await res.json();
          this.pickerBrands = data.items;
        }
        this.pickerSearch();
      } catch (err) { showJsError(err); }
    },

    materialBrandName(brandId) {
      const found = this.pickerBrands.find(b => b.id === brandId);
      return found ? found.name : '';
    },

    async pickerSearch() {
      // Переиспользует существующий GET /api/material?q=...&search_fields=
      // — тот же эндпоинт и те же параметры, что и обычная плоская
      // таблица материалов, включая мультивыбор полей поиска и фильтр
      // по бренду (?brand_id=) — по прямой просьбе "где фильтры по
      // брендам, поиск по артикулу и все остальные возможности поиска
      // в плоской таблице". Пустой запрос ('' — как при первом
      // открытии) возвращает первую страницу без фильтра.
      try {
        hideJsError();
        const params = new URLSearchParams();
        const query = this.pickerQuery.trim();
        if (query) {
          params.set('q', query);
          for (const [field, enabled] of Object.entries(this.pickerSearchFields)) {
            if (enabled) params.append('search_fields', field);
          }
        }
        if (this.pickerBrandFilter) params.set('brand_id', this.pickerBrandFilter);
        params.set('page_size', 50);
        const res = await fetch('/api/material?' + params.toString());
        const data = await res.json();
        this.pickerResults = data.items;
      } catch (err) { showJsError(err); }
    },

    pickerSetBrandFilter(brandId) {
      this.pickerBrandFilter = brandId;
      this.pickerSearch();
    },

    pickerAddMaterial(material) {
      // Дубликаты material_id разрешены — не суммируются с уже
      // существующей строкой (см. HANDOFF, 2.9: явное решение).
      this.pickerDraftSeq += 1;
      this.pickerDraft.push({ _key: 'new-' + this.pickerDraftSeq, material_id: material.id, quantity: 1 });
      // подпись новой строки должна резолвиться сразу — если материала
      // ещё нет в списке подписей, добавляем его на лету. kit использует
      // itemRelationOptions['material_id'], calculation — отдельный кэш
      // materialsMaterialOptions (см. materialItemLabel/materialLabel).
      const opts = this.itemRelationOptions['material_id'] || [];
      if (!opts.some(o => o.id === material.id)) {
        this.itemRelationOptions['material_id'] = [...opts, material];
      }
      if (this.pickerTarget === 'calculation') {
        const matOpts = this.materialsMaterialOptions;
        if (!matOpts.some(o => o.id === material.id)) {
          this.materialsMaterialOptions = [...matOpts, material];
        }
      }
    },

    pickerIncrement(idx) {
      this.pickerDraft[idx].quantity = Number((this.pickerDraft[idx].quantity + 1).toFixed(2));
    },

    pickerDecrement(idx) {
      const next = Number((this.pickerDraft[idx].quantity - 1).toFixed(2));
      this.pickerDraft[idx].quantity = next > 0 ? next : 1;
    },

    pickerRemoveRow(idx) {
      this.pickerDraft.splice(idx, 1);
    },

    pickerCancel() {
      // Черновик просто отбрасывается — ничего на сервере не менялось
      // (см. HANDOFF, 2.9: кнопка "Отмена" обязательна).
      this.pickerOpen = false;
      this.pickerDraft = [];
      if (this.pickerTarget === 'calculation' || this.pickerTarget === 'kits') {
        // Возврат на форму калькуляции (вкладка "Материалы" или
        // "Комплекты"), НЕ на список калькуляций целиком — в отличие от
        // kit, здесь есть полноценная форма с другими вкладками, которую
        // не нужно закрывать только потому что отменили подбор.
        this.modalOpen = true;
        return;
      }
      // kit — возврат СРАЗУ на экран со списком комплектов (drill-list),
      // БЕЗ промежуточного показа модалки просмотра состава — раньше
      // здесь стояло modalOpen = true, и после закрытия пикера человек
      // попадал на модалку "Подключение 25а", которую нужно было
      // закрывать ещё раз отдельным тапом (см. HANDOFF: "окно там не
      // нужно, его можно закрывать и сам не выходить на экран с
      // перечнем комплектов").
      this.modalOpen = false;
      this.editing = {};
      this.kitItems = [];
    },

    async pickerSave() {
      try {
        hideJsError();
        if (this.pickerTarget === 'kits') {
          // Полная замена всех отобранных комплектов калькуляции разом
          // (2026-08-23, по прямой просьбе Вахтанга — "как у материалов")
          // — отдельный эндпоинт PUT .../kit-items-replace, параллельный
          // replace_items, но для kit_id-строк: каждая созданная строка
          // получает price_excl_vat = ТЕКУЩАЯ сумма состава комплекта
          // (Σ kit_item.quantity × material.price_excl_vat) на момент
          // сохранения, та же формула, что и при "Пересчитать".
          const payload = {
            items: this.pickerDraft.map(row => ({ kit_id: row.kit_id, quantity: row.quantity })),
          };
          const res = await fetch('/api/calculation/' + this.editing.id + '/kit-items-replace', {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
          });
          if (!res.ok) { showJsError(await extractErrorMessage(res)); return; }
          this.pickerOpen = false;
          this.pickerDraft = [];
          this.modalOpen = true;
          await this.loadKitsItems();
          return;
        }
        const payload = {
          items: this.pickerDraft.map(row => ({ material_id: row.material_id, quantity: row.quantity })),
        };
        const endpoint = this.pickerTarget === 'calculation'
          ? '/api/calculation/' + this.editing.id + '/items'
          : '/api/kit/' + this.editing.id + '/items';
        const res = await fetch(endpoint, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
        });
        if (!res.ok) {
          showJsError(await extractErrorMessage(res));
          return;
        }
        this.pickerOpen = false;
        this.pickerDraft = [];
        if (this.pickerTarget === 'calculation') {
          // Возврат на форму калькуляции, вкладка "Материалы" —
          // подгружаем свежий состав (свежие цены-снэпшоты, только что
          // проставленные replace_items на бэке).
          this.modalOpen = true;
          await this.loadMaterialsItems();
          return;
        }
        // Состав kit уже сохранён на сервере (см. запрос выше) —
        // обновляем список drill-list, чтобы актуальные данные
        // подтянулись при следующем открытии этого комплекта. Возврат
        // СРАЗУ на список комплектов, БЕЗ промежуточного показа модалки
        // просмотра состава (см. HANDOFF: модалка на этом шаге не нужна).
        this.modalOpen = false;
        this.editing = {};
        this.kitItems = [];
        await this.load();
      } catch (err) { showJsError(err); }
    },

    // --- MaterialPicker: перетаскиваемая полоса между "Отобрано" и
    // поиском (см. HANDOFF, 2.8) — pointer-события работают одинаково
    // для мыши и тача, не нужен отдельный код под touchstart/mousedown.
    pickerDragStart(evt) {
      this.pickerDragging = true;
      this.pickerDragStartY = evt.clientY;
      this.pickerDragStartSplit = this.pickerSplit;
      // Высота ИМЕННО .picker-overlay (а не window.innerHeight) —
      // 2026-08-24, по мотивам бага "дерево комплектов пропадает при
      // перетаскивании ползунка" (см. HANDOFF): на мобильном Chrome
      // touch-жест на хэндле мог "провалиться" сквозь position:fixed
      // оверлей на скролл страницы под ним, из-за чего адресная строка
      // выезжала обратно на экран и window.innerHeight МЕНЯЛСЯ прямо
      // посреди одного и того же жеста — deltaPercent считался против
      // движущейся цели, split мог улететь далеко за пределы
      // ожидаемого. Высота самого оверлея — величина, которая не должна
      // прыгать даже если viewport вокруг него меняется, плюс
      // updateBodyScrollLock() (см. init()) теперь в принципе не
      // позволяет странице позади оверлея скроллиться, пока он открыт —
      // это тоже часть исправления, дополняющая, а не заменяющая,
      // измерение через сам оверлей.
      const overlay = evt.currentTarget.closest('.picker-overlay');
      this.pickerOverlayHeight = overlay ? overlay.getBoundingClientRect().height : (window.innerHeight || document.documentElement.clientHeight);
      evt.preventDefault();
      const onMove = (moveEvt) => this.pickerDragMove(moveEvt);
      const onUp = () => {
        this.pickerDragging = false;
        window.removeEventListener('pointermove', onMove);
        window.removeEventListener('pointerup', onUp);
      };
      window.addEventListener('pointermove', onMove);
      window.addEventListener('pointerup', onUp);
    },

    pickerDragMove(evt) {
      if (!this.pickerDragging) return;
      const overlayHeight = this.pickerOverlayHeight || window.innerHeight || document.documentElement.clientHeight;
      const deltaPercent = ((evt.clientY - this.pickerDragStartY) / overlayHeight) * 100;
      let next = this.pickerDragStartSplit + deltaPercent;
      // Диапазон 15-85% — ни одна из двух зон никогда не схлопывается
      // полностью (см. HANDOFF, 2.8).
      if (next < 15) next = 15;
      if (next > 85) next = 85;
      this.pickerSplit = next;
    },

    // --- Вкладка "Материалы" калькуляции (CONFIG.materialsTab,
    // 2026-08-23) — список позиций CalculationItem текущей открытой
    // калькуляции. В отличие от items_modal/MaterialPicker выше (kit:
    // черновик + replace-all при сохранении), здесь КАЖДАЯ операция
    // (добавить/изменить количество/удалить/скопировать) идёт сразу
    // на сервер отдельным запросом — нет "черновика", нечего
    // "отменять" одной кнопкой, ровно как у обычных плоских таблиц
    // движка (material/brand). ---

    async loadReadonlyItems() {
      // Read-only список дочерних строк (TableConfig.readonly_items_tab,
      // 2026-08-28) — тот же parent_id-механизм, что и loadMaterialsItems,
      // но без фильтрации по material_id/kit_id (эта таблица однородна —
      // одна SpecificationItem = одна строка, без "материалы vs
      // комплекты вперемешку", как у calculation_item).
      //
      // invoiceItemsTableKey (2026-08-29) — тот же метод переиспользован
      // для invoice_items_tab (см. openEdit()): единственная разница —
      // источник ключа дочерней таблицы, сам parent_id-запрос идентичен.
      try {
        hideJsError();
        const key = CONFIG.readonlyItemsTableKey || CONFIG.invoiceItemsTableKey;
        const params = new URLSearchParams();
        params.set('parent_id', this.editing.id);
        params.set('page_size', 1000);
        const res = await fetch('/api/' + key + '?' + params.toString());
        const data = await res.json();
        this.readonlyItems = data.items;
      } catch (err) { showJsError(err); }
    },

    async invoiceItemDiscountChanged(row) {
      // Построчное редактирование скидки в таблице invoice_items_tab
      // (2026-08-29) — обычный PUT движка на дочернюю таблицу
      // (invoice_item), сервер сам пересчитывает unit_price_after_discount/
      // line_total (см. before_update_hook у invoice_item_table в
      // tables.py) — здесь только шлём новое discount_percent и
      // подменяем строку результатом, чтобы расчётные колонки и итог
      // "Разом без ПДВ" обновились сразу без перезагрузки всей таблицы.
      try {
        hideJsError();
        const key = CONFIG.invoiceItemsTableKey;
        const discountField = CONFIG.invoiceItemsDiscountField;
        const res = await fetch(`/api/${key}/${row.id}`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ [discountField]: row[discountField] }),
        });
        if (!res.ok) { showJsError(await res.text()); return; }
        const updated = await res.json();
        const idx = this.readonlyItems.findIndex(r => r.id === row.id);
        if (idx !== -1) this.readonlyItems[idx] = updated;
        await this.invoiceItemsRefreshTotals();
      } catch (err) { showJsError(err); }
    },

    async invoiceItemsRefreshTotals() {
      // После правки построчной скидки (см. invoiceItemDiscountChanged)
      // шапка счёта (total_excl_vat/vat_amount/total_incl_vat) не
      // пересчитывается сама по себе — перечитываем актуальную запись
      // целиком, т.к. эти поля считает сервер (см.
      // _apply_bulk_discount_handler/_recalculate_invoice_totals в
      // tables.py — тот же принцип пересчёта, что нужен и здесь, но
      // без изменения самих строк, поэтому просто GET текущей записи).
      try {
        const res = await fetch(`/api/${this.currentLevel().key}/${this.editing.id}`);
        if (!res.ok) return;
        const data = await res.json();
        this.editing = { ...this.editing, ...data };
      } catch (err) { showJsError(err); }
    },

    async invoiceItemsApplyBulkDiscount() {
      // Кнопка "Дать скидку" (2026-08-29) — один window.prompt() для
      // всего счёта сразу (см. TableConfig.invoice_items_bulk_discount_
      // action и _apply_bulk_discount_handler в tables.py). Простой
      // prompt(), а не отдельная модалка — единственное значение,
      // вводимое человеком, не оправдывает более тяжёлый UI. Пустой
      // ввод/Отмена — ничего не отправляем.
      const raw = window.prompt('Скидка/наценка, % (например -10 или 5):', '0');
      if (raw === null || raw.trim() === '') return;
      const discountPercent = Number(raw);
      if (Number.isNaN(discountPercent)) {
        showJsError('Скидка должна быть числом.');
        return;
      }
      try {
        hideJsError();
        const action = CONFIG.invoiceItemsBulkDiscountAction;
        const res = await fetch(`/api/${this.currentLevel().key}/${this.editing.id}/actions/${action}`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ discount_percent: discountPercent }),
        });
        if (!res.ok) { showJsError(await res.text()); return; }
        const data = await res.json();
        this.editing = { ...this.editing, ...data };
        await this.loadReadonlyItems();
      } catch (err) { showJsError(err); }
    },

    readonlyItemsColumnValue(row, fieldName, format) {
      // "calculation_number" — единственное расчётное поле сейчас: не
      // физическая колонка SpecificationItem, а document_number
      // калькуляции, найденный по row.calculation_id в
      // relationOptions['calculation'] (см. extra_lookups=["calculation"]
      // у specification_table) — без похода на сервер. Остальные поля
      // читаются с row напрямую по формату.
      let value;
      if (fieldName === 'calculation_number') {
        const calcs = (this.relationOptions && this.relationOptions.calculation) || [];
        const calc = calcs.find(c => c.id === row.calculation_id);
        value = calc ? calc.document_number : '';
      } else {
        value = row[fieldName];
      }
      if (format === 'money') {
        return Number(value ?? 0).toFixed(2);
      }
      return value ?? '';
    },

    async loadMaterialsItems() {
      try {
        hideJsError();
        const key = CONFIG.materialsItemTableKey;
        const params = new URLSearchParams();
        params.set('parent_id', this.editing.id);
        params.set('page_size', 1000);
        const res = await fetch('/api/' + key + '?' + params.toString());
        const data = await res.json();
        // Один и тот же родительский список calculation_item содержит и
        // материалы, и комплекты вперемешку (см. CalculationItem.kit_id) —
        // фильтр по material_id делается на фронте, зеркально фильтру
        // !!row.kit_id в loadKitsItems(). Без этого строки-комплекты
        // тоже попадают в список материалов: material_id у них пуст,
        // materialItemLabel() ничего не находит — строка отображается
        // без названия, но с ценой.
        this.materialsItems = data.items.filter(row => !!row.material_id);
        this.materialsSelectedIds = [];
        if (this.materialsMaterialOptions.length === 0) {
          const matRes = await fetch('/api/material?page_size=1000');
          const matData = await matRes.json();
          this.materialsMaterialOptions = matData.items;
        }
        if (this.materialsUnitOptions.length === 0) {
          const unitRes = await fetch('/api/unit?page_size=1000');
          const unitData = await unitRes.json();
          this.materialsUnitOptions = unitData.items;
        }
      } catch (err) { showJsError(err); }
    },

    materialItemLabel(materialId) {
      const found = this.materialsMaterialOptions.find(m => m.id === materialId);
      return found ? found.short_name : '';
    },

    materialItemUnit(materialId) {
      const material = this.materialsMaterialOptions.find(m => m.id === materialId);
      if (!material || !material.unit_id) return '';
      const unit = this.materialsUnitOptions.find(u => u.id === material.unit_id);
      return unit ? unit.name : '';
    },

    toggleMaterialSelect(id) {
      const idx = this.materialsSelectedIds.indexOf(id);
      if (idx === -1) { this.materialsSelectedIds.push(id); } else { this.materialsSelectedIds.splice(idx, 1); }
    },

    async materialItemSetQuantity(row, quantity) {
      // Инлайн-редактирование количества прямо в строке списка (решение
      // Вахтанга 2026-08-23: "менять количество прямо в режиме
      // просмотра", без открытия MaterialPicker заново) — сохраняет
      // сразу на сервер (PUT), не ждёт отдельной кнопки "Сохранить".
      const clean = quantity > 0 ? Math.round(quantity * 100) / 100 : 1;
      row.quantity = clean;
      try {
        hideJsError();
        const res = await fetch('/api/' + CONFIG.materialsItemTableKey + '/' + row.id, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            calculation_id: this.editing.id,
            material_id: row.material_id,
            quantity: clean,
            price_excl_vat: row.price_excl_vat,
          }),
        });
        if (!res.ok) { showJsError(await extractErrorMessage(res)); return; }
      } catch (err) { showJsError(err); }
    },

    materialItemIncrement(row) { this.materialItemSetQuantity(row, Number(row.quantity ?? 0) + 1); },
    materialItemDecrement(row) { this.materialItemSetQuantity(row, Number(row.quantity ?? 0) - 1); },

    async copyMaterialItem() {
      // Копирование доступно только при РОВНО одном выделенном элементе,
      // тот же принцип, что и copySelected() в обычных плоских таблицах
      // (см. решение сессии v33) — создаёт независимую новую позицию
      // с теми же material_id/quantity/price_excl_vat.
      if (this.materialsSelectedIds.length !== 1) return;
      const row = this.materialsItems.find(r => r.id === this.materialsSelectedIds[0]);
      if (!row) return;
      try {
        hideJsError();
        const res = await fetch('/api/' + CONFIG.materialsItemTableKey, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            calculation_id: this.editing.id,
            material_id: row.material_id,
            quantity: row.quantity,
            price_excl_vat: row.price_excl_vat,
          }),
        });
        if (!res.ok) { showJsError(await extractErrorMessage(res)); return; }
        this.materialsSelectedIds = [];
        await this.loadMaterialsItems();
      } catch (err) { showJsError(err); }
    },

    async deleteSelectedMaterialItems() {
      // Массовое удаление выделенных позиций — физическое (delete_mode
      // не задан у calculation_item -> "hard", см. модель), безусловное,
      // без подтверждения (тот же принцип, что и у обычного DELETE
      // одной позиции состава кита). Каждая позиция удаляется отдельным
      // запросом (нет отдельного bulk-эндпоинта под calculation_item —
      // осознанно не заводили ради простоты, см. HANDOFF).
      if (this.materialsSelectedIds.length === 0) return;
      try {
        hideJsError();
        await Promise.all(this.materialsSelectedIds.map(id =>
          fetch('/api/' + CONFIG.materialsItemTableKey + '/' + id, { method: 'DELETE' })
        ));
        this.materialsSelectedIds = [];
        await this.loadMaterialsItems();
      } catch (err) { showJsError(err); }
    },

    // --- Вкладка "Комплекты" калькуляции (2026-08-23, пикер добавлен
    // 2026-08-23 вторым заходом) — количество/выделение/копирование/
    // удаление правятся сразу на сервер отдельными запросами (тот же
    // принцип, что и у вкладки "Материалы"), а ДОБАВЛЕНИЕ/ЗАМЕНА состава
    // идёт через тот же picker-overlay, что и у материалов, только с
    // деревом группа→раздел→комплект в нижней зоне подбора вместо
    // плоского поиска (см. openKitAdder/kitTreeLoad/pickerAddKit ниже,
    // pickerSave — общий метод, ветвится по pickerTarget==='kits'). ---

    async loadKitsItems() {
      try {
        hideJsError();
        const key = CONFIG.kitsItemTableKey;
        const params = new URLSearchParams();
        params.set('parent_id', this.editing.id);
        params.set('page_size', 1000);
        const res = await fetch('/api/' + key + '?' + params.toString());
        const data = await res.json();
        // Один и тот же родительский список calculation_item содержит и
        // материалы, и комплекты вперемешку (см. CalculationItem.kit_id) —
        // фильтр по kit_id IS NOT NULL делается на фронте, это чисто
        // разделение по вкладкам, не отдельный API-запрос.
        this.kitsItems = data.items.filter(row => !!row.kit_id);
        this.kitsSelectedIds = [];
        if (this.kitsKitOptions.length === 0) {
          const kitRes = await fetch('/api/kit?page_size=1000');
          const kitData = await kitRes.json();
          this.kitsKitOptions = kitData.items;
        }
        // Подписи материалов в модалке просмотра состава (openKitDetail)
        // используют materialItemLabel/materialItemUnit — те же кэши,
        // что и у вкладки "Материалы" (materialsMaterialOptions/
        // materialsUnitOptions). Комплекты можно открыть, даже не заходя
        // на вкладку "Материалы" в этой сессии, поэтому подгружаем те же
        // справочники здесь тоже, если их ещё нет.
        if (this.materialsMaterialOptions.length === 0) {
          const matRes = await fetch('/api/material?page_size=1000');
          const matData = await matRes.json();
          this.materialsMaterialOptions = matData.items;
        }
        if (this.materialsUnitOptions.length === 0) {
          const unitRes = await fetch('/api/unit?page_size=1000');
          const unitData = await unitRes.json();
          this.materialsUnitOptions = unitData.items;
        }
      } catch (err) { showJsError(err); }
    },

    kitItemLabel(kitId) {
      const found = this.kitsKitOptions.find(k => k.id === kitId);
      return found ? found.name : '';
    },

    // --- Пикер комплектов (pickerTarget==='kits', 2026-08-23) — тот же
    // picker-overlay, что и у материалов, но нижняя зона подбора — дерево
    // группа→раздел→комплект вместо плоского поиска (по прямой просьбе
    // Вахтанга: "экран подбора должен быть организован через иерархию
    // так же, как экран комплектов"). ---

    async openKitAdder() {
      try {
        hideJsError();
        // Предзаполнение из ТЕКУЩИХ отобранных комплектов (kitsItems уже
        // загружены при openEdit/loadKitsItems) — та же логика
        // предзаполнения, что и у openMaterialAdder().
        this.pickerDraft = this.kitsItems.map(item => ({
          _key: 'existing-' + item.id,
          kit_id: item.kit_id,
          quantity: Number(item.quantity ?? 1),
        }));
        this.pickerDraftSeq = this.pickerDraft.length;
        this.pickerTarget = 'kits';
        this.pickerSplit = 40;
        this.modalOpen = false;
        this.pickerOpen = true;
        this.kitTreePath = [];
        // Сбрасываем кэш цен за единицу — на случай если состав каких-то
        // комплектов поменялся с прошлого открытия picker'а в этой же
        // сессии (кэш иначе жил бы бессрочно, показывая устаревшую
        // цену).
        this.kitPriceCache = {};
        for (const row of this.pickerDraft) {
          this.ensureKitPrice(row.kit_id);
        }
        await this.kitTreeLoad();
      } catch (err) { showJsError(err); }
    },

    async kitTreeLoad() {
      // Загружает узлы ТЕКУЩЕГО уровня дерева (kitTreePath.length: 0 —
      // группы, 1 — разделы внутри группы, 2 не бывает — на уровне
      // "комплект" тап сразу добавляет в черновик, не открывает
      // следующий уровень, см. kitTreeNodeClick). Использует те же три
      // эндпоинта, что и полноценные страницы /kit_group-v2 и т.п., но
      // НЕ переиспользует их drillPath/LEVELS — свой независимый стек
      // (см. обоснование у kitTreePath в объявлении state выше).
      try {
        hideJsError();
        const depth = this.kitTreePath.length;
        let url;
        if (depth === 0) {
          url = '/api/kit_group?page_size=1000';
        } else if (depth === 1) {
          url = '/api/kit_section?parent_id=' + this.kitTreePath[0].id + '&page_size=1000';
        } else {
          url = '/api/kit?parent_id=' + this.kitTreePath[1].id + '&page_size=1000';
        }
        const res = await fetch(url);
        const data = await res.json();
        this.kitTreeNodes = data.items;
      } catch (err) { showJsError(err); }
    },

    kitTreeNodeClick(node) {
      // На уровнях "группа"/"раздел" (kitTreePath.length < 2) — уходим
      // вглубь дерева. На уровне "комплект" (length === 2) — клик по
      // ЛЮБОЙ части строки добавляет комплект в черновик (2026-08-24, по
      // прямой просьбе Вахтанга — "вся строка должна добавлять, как в
      // поиске материалов"): кнопка "+ Добавить" остаётся визуальным
      // акцентом справа (совпадающим по стилю с поиском материалов), но
      // клик по ней вызывает pickerAddKit() через @click.stop в разметке
      // — не всплывает до этого обработчика, поэтому дублирования нет
      // (клик по кнопке добавляет один раз через свой путь, клик по
      // остальной строке — один раз через этот).
      if (this.kitTreePath.length >= 2) {
        this.pickerAddKit(node);
        return;
      }
      this.kitTreePath.push({ id: node.id, name: node.name });
      this.kitTreeLoad();
    },

    kitTreeBack() {
      this.kitTreePath.pop();
      this.kitTreeLoad();
    },

    kitTreeGoTo(depth) {
      // Переход по хлебной крошке на произвольный уровень дерева
      // (2026-08-24, по прямой просьбе Вахтанга: "клик на хлебные крошки
      // — переход на соответствующий раздел/подраздел"). depth — целевая
      // длина kitTreePath: 0 = корень ("Группы комплектов"), 1 = список
      // разделов внутри выбранной группы, 2 (текущий последний уровень —
      // сюда крошка никогда не ведёт, см. kitTreeCrumb: последний сегмент
      // рендерится НЕ ссылкой, раз он уже совпадает с текущим экраном).
      this.kitTreePath = this.kitTreePath.slice(0, depth);
      this.kitTreeLoad();
    },

    kitTreeCrumbSegments() {
      // Хлебная крошка как массив кликабельных сегментов (2026-08-24) —
      // каждый сегмент — {label, depth, isCurrent}, где depth — то, что
      // нужно передать в kitTreeGoTo() при клике на ЭТОТ сегмент.
      // Корень ("Группы комплектов") всегда первый элемент с depth=0.
      // ПОСЛЕДНИЙ сегмент (текущий экран) — тоже включён в массив для
      // единообразного рендера через x-for, но помечается isCurrent,
      // чтобы разметка могла показать его как обычный текст, а не
      // ссылку (клик на "текущий экран" не имеет смысла — он и так уже
      // открыт).
      const segments = [{ label: 'Группы комплектов', depth: 0, isCurrent: this.kitTreePath.length === 0 }];
      this.kitTreePath.forEach((node, idx) => {
        segments.push({ label: node.name, depth: idx + 1, isCurrent: idx === this.kitTreePath.length - 1 });
      });
      return segments;
    },

    pickerAddKit(kit) {
      // Дубликаты kit_id разрешены — та же логика, что и pickerAddMaterial
      // (не суммируются с уже существующей строкой черновика).
      this.pickerDraftSeq += 1;
      this.pickerDraft.push({ _key: 'new-' + this.pickerDraftSeq, kit_id: kit.id, quantity: 1 });
      const opts = this.kitsKitOptions;
      if (!opts.some(o => o.id === kit.id)) {
        this.kitsKitOptions = [...opts, kit];
      }
      this.ensureKitPrice(kit.id);
    },

    kitItemIncrement(row) { this.kitItemSetQuantity(row, Number(row.quantity ?? 0) + 1); },
    kitItemDecrement(row) { this.kitItemSetQuantity(row, Number(row.quantity ?? 0) - 1); },

    async kitItemSetQuantity(row, quantity) {
      // Инлайн-редактирование количества прямо в строке списка отобранных
      // комплектов — тот же паттерн, что и materialItemSetQuantity()
      // (сохраняет сразу на сервер, не трогает price_excl_vat — снэпшот
      // суммы состава пересчитывается только явной кнопкой "Пересчитать"
      // или полной заменой через picker, не при простом изменении
      // количества).
      const clean = quantity > 0 ? Math.round(quantity * 100) / 100 : 1;
      row.quantity = clean;
      try {
        hideJsError();
        const res = await fetch('/api/' + CONFIG.kitsItemTableKey + '/' + row.id, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            calculation_id: this.editing.id,
            kit_id: row.kit_id,
            quantity: clean,
            price_excl_vat: row.price_excl_vat,
          }),
        });
        if (!res.ok) { showJsError(await extractErrorMessage(res)); return; }
      } catch (err) { showJsError(err); }
    },

    toggleKitSelect(id, event) {
      // event.stopPropagation не нужен отдельно — чекбокс не всплывает на
      // клик по строке (клик по строке открывает openKitDetail(), см.
      // разметку), но сам клик по чекбоксу не должен запускать
      // openKitDetail через родительский div.
      if (event) event.stopPropagation();
      const idx = this.kitsSelectedIds.indexOf(id);
      if (idx === -1) { this.kitsSelectedIds.push(id); } else { this.kitsSelectedIds.splice(idx, 1); }
    },

    async copyKitItem() {
      if (this.kitsSelectedIds.length !== 1) return;
      const row = this.kitsItems.find(r => r.id === this.kitsSelectedIds[0]);
      if (!row) return;
      try {
        hideJsError();
        const res = await fetch('/api/' + CONFIG.kitsItemTableKey, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            calculation_id: this.editing.id,
            kit_id: row.kit_id,
            quantity: row.quantity,
            price_excl_vat: row.price_excl_vat,
          }),
        });
        if (!res.ok) { showJsError(await extractErrorMessage(res)); return; }
        this.kitsSelectedIds = [];
        await this.loadKitsItems();
      } catch (err) { showJsError(err); }
    },

    async deleteSelectedKitItems() {
      if (this.kitsSelectedIds.length === 0) return;
      try {
        hideJsError();
        await Promise.all(this.kitsSelectedIds.map(id =>
          fetch('/api/' + CONFIG.kitsItemTableKey + '/' + id, { method: 'DELETE' })
        ));
        this.kitsSelectedIds = [];
        await this.loadKitsItems();
      } catch (err) { showJsError(err); }
    },

    async openKitDetail(row) {
      // Read-only просмотр состава комплекта — заходит в справочник
      // kit_item ЖИВЫМ запросом (не снэпшот, в отличие от строки списка
      // на вкладке "Комплекты"): человек должен видеть АКТУАЛЬНЫЙ состав
      // комплекта прямо сейчас, чтобы понимать из чего складывалась
      // сумма при последнем добавлении/пересчёте — если состав кита
      // поменялся ПОСЛЕ этого, сумма в строке (снэпшот) и то, что видно
      // в модалке (текущий состав), могут разойтись, это ожидаемо (см.
      // обоснование "живая ссылка vs снэпшот" в HANDOFF_kits_and_
      // calculation.md).
      try {
        hideJsError();
        this.kitDetailName = this.kitItemLabel(row.kit_id);
        const res = await fetch('/api/kit_item?parent_id=' + row.kit_id + '&page_size=1000');
        const data = await res.json();
        this.kitDetailItems = data.items.map(item => ({
          id: item.id,
          material_id: item.material_id,
          quantity: item.quantity,
          price_excl_vat: this.materialItemPrice(item.material_id),
        }));
        this.kitDetailOpen = true;
      } catch (err) { showJsError(err); }
    },

    materialItemPrice(materialId) {
      const found = this.materialsMaterialOptions.find(m => m.id === materialId);
      return found ? Number(found.price_excl_vat ?? 0) : 0;
    },

    // --- Цена за единицу комплекта внутри ЧЕРНОВИКА picker'а
    // (pickerTarget==='kits', 2026-08-24) — см. обоснование у
    // kitPriceCache в объявлении state выше. kitUnitPrice() читает кэш
    // синхронно (для x-text в разметке), ensureKitPrice() догружает
    // состав в фоне при первом обращении к ещё некэшированному kit_id и
    // сама вызывает себя из pickerAddKit()/openKitAdder(), чтобы цена
    // была готова к моменту первого рендера строки, а не появлялась с
    // задержкой после клика. ---

    kitUnitPrice(kitId) {
      if (this.kitPriceCache[kitId] === undefined) {
        this.ensureKitPrice(kitId);
        return 0;
      }
      return this.kitPriceCache[kitId];
    },

    async ensureKitPrice(kitId) {
      if (this.kitPriceCache[kitId] !== undefined) return;
      // Placeholder сразу (0), чтобы параллельные обращения к одному и
      // тому же kitId из нескольких строк черновика не запускали
      // повторные fetch, пока первый ещё не завершился.
      this.kitPriceCache[kitId] = 0;
      try {
        const res = await fetch('/api/kit_item?parent_id=' + kitId + '&page_size=1000');
        const data = await res.json();
        let total = 0;
        for (const item of data.items) {
          total += this.materialItemPrice(item.material_id) * Number(item.quantity ?? 0);
        }
        this.kitPriceCache = { ...this.kitPriceCache, [kitId]: Math.round(total * 100) / 100 };
      } catch (err) { showJsError(err); }
    },

    get pickerKitsTotal() {
      // Сумма без НДС по ВСЕМ строкам черновика picker'а — используется
      // ТОЛЬКО когда pickerTarget==='kits' (для материалов в черновике
      // цена не показывается вовсе, см. разметку picker-pane-top).
      return this.pickerDraft.reduce(
        (sum, row) => sum + this.kitUnitPrice(row.kit_id) * Number(row.quantity ?? 0), 0
      );
    },

    toggleSelect(id) {
      const idx = this.selectedIds.indexOf(id);
      if (idx === -1) { this.selectedIds.push(id); } else { this.selectedIds.splice(idx, 1); }
    },

    // Уровни, где вообще показываются чекбоксы выделения/панель —
    // сейчас: любая плоская таблица (material/brand) ЛИБО уровень
    // дерева с editMode="items_modal" (kit). kit_group/kit_section
    // выделения не имеют — групповых операций на них не планировалось.
    isSelectableLevel() {
      const lvl = this.currentLevel ? this.currentLevel() : null;
      return !!(lvl && (!CONFIG.hierarchyRoot || lvl.editMode === 'items_modal'));
    },

    async copySelected() {
      // Копирование доступно только при РОВНО одном выделенном элементе —
      // при нескольких выделенных кнопка задизейблена в разметке
      // (:disabled="selectedIds.length !== 1"), это дополнительная
      // защита на случай программного вызова.
      if (this.selectedIds.length !== 1) return;
      const item = this.items.find(i => i.id === this.selectedIds[0]);
      if (!item) return;
      try {
        hideJsError();
        if (this.isItemsModal()) {
          // kit: состав (kit_item) не хранится в самой записи, поэтому
          // "скопировать в форме" недостаточно — копия делается сразу
          // на сервере (POST /api/kit/{id}/copy), одной транзакцией
          // вместе со всем составом. Название копии совпадает с
          // оригиналом; дальше комплект сразу открывается как обычная
          // существующая запись — пользователь переименовывает его
          // на месте (см. решение: подтверждения ДО копирования не
          // нужно, копия создаётся сразу, название правится потом).
          const res = await fetch('/api/' + this.currentLevel().key + '/' + item.id + '/copy', {
            method: 'POST',
          });
          if (!res.ok) {
            showJsError('Не удалось скопировать. ' + await extractErrorMessage(res));
            return;
          }
          const newKit = await res.json();
          this.selectedIds = [];
          await this.load();
          this.openEdit(newKit);
        } else if (CONFIG.ownPageUrl) {
          // Плоские таблицы С собственной формой-страницей (v75: request/
          // calculation) — копия не может просто выставить this.editing
          // на этой странице (здесь, на списке, формы в разметке больше
          // нет вообще). Вместо этого готовим предзаполненные данные
          // (та же логика, что и раньше: без id, is_deleted сброшен,
          // дата/время — сегодняшние) и кладём во ВРЕМЕННОЕ хранилище
          // sessionStorage под фиксированным ключом — читается один раз
          // на форме-странице в maybeOpenOwnPage() и сразу удаляется
          // (см. там же), чтобы повторная загрузка той же формы (F5)
          // не подхватила старые данные копии повторно. sessionStorage,
          // а не query-параметр — данные записи (особенно с текстовыми
          // полями типа "Заметка") не гарантированно умещаются и
          // корректно проходят через длину/экранирование URL.
          const lvl = this.currentLevel();
          const copy = { ...item };
          delete copy.id;
          copy.is_deleted = false;
          for (const f of lvl.fields) {
            if (f.widget === 'date') {
              const today = new Date();
              const pad = (n) => String(n).padStart(2, '0');
              copy[f.name] = `${today.getFullYear()}-${pad(today.getMonth() + 1)}-${pad(today.getDate())}`;
            } else if (f.widget === 'time') {
              const now = new Date();
              const pad = (n) => String(n).padStart(2, '0');
              copy[f.name] = `${pad(now.getHours())}:${pad(now.getMinutes())}`;
            }
          }
          sessionStorage.setItem('engineCopyPrefill:' + lvl.key, JSON.stringify(copy));
          this.selectedIds = [];
          window.location.href = CONFIG.ownPageUrl + '/new';
        } else {
          // Плоские таблицы БЕЗ собственной формы-страницы (material/
          // brand и т.п., own_page_url не задан) — старое поведение:
          // открывает форму, предзаполненную данными существующей
          // записи, но БЕЗ id —
          // save() увидит отсутствие id и отправит POST (создание новой
          // независимой записи), а не PUT. is_deleted копии всегда
          // сброшен в false. Остальные поля копируются как есть —
          // пользователь правит вручную перед сохранением.
          const lvl = this.currentLevel();
          const copy = { ...item };
          delete copy.id;
          copy.is_deleted = false;
          // Номер документа и дата — НЕ копируются "один в один" с
          // оригинала (иначе копия заявки получила бы тот же номер и
          // старую дату, что и источник — неверно для нового документа).
          // Дата — сегодняшняя, тем же способом, что и в openCreate().
          // Номер — подтягивается тем же предпросмотр-эндпоинтом
          // (GET next-document-number), реальный номер присвоит save()
          // на бэкенде (_apply_document_numbering), это только то, что
          // видно человеку сразу при открытии формы копии.
          for (const f of lvl.fields) {
            if (f.widget === 'date') {
              const today = new Date();
              const pad = (n) => String(n).padStart(2, '0');
              copy[f.name] = `${today.getFullYear()}-${pad(today.getMonth() + 1)}-${pad(today.getDate())}`;
            } else if (f.widget === 'time') {
              const now = new Date();
              const pad = (n) => String(n).padStart(2, '0');
              copy[f.name] = `${pad(now.getHours())}:${pad(now.getMinutes())}`;
            }
          }
          this.editing = copy;
          this.modalOpen = true;
          this.selectedIds = [];
          if (lvl.documentNumberField) {
            try {
              const res = await fetch('/api/' + lvl.key + '/next-document-number');
              if (res.ok) {
                const data = await res.json();
                this.editing[lvl.documentNumberField] = data.document_number;
              }
            } catch (e) { /* не критично — сервер всё равно сгенерирует номер на save */ }
          }
        }
      } catch (err) { showJsError(err); }
    },

    createChildDocument() {
      // "Создать документ на основании" (request → calculation, v62):
      // активна только при РОВНО одном выделенном элементе (см.
      // :disabled в разметке). Переход на страницу дочернего документа
      // (сейчас единственная — /calculation-v2, из createChildDocumentUrl)
      // с query-параметром ?from_request={id} — сама целевая страница
      // (её init(), см. ниже) подхватывает параметр, открывает форму
      // новой записи и предзаполняет request_id, дальше подтягивает
      // бренды тем же путём, что и обычное ручное открытие формы.
      // Полная перезагрузка страницы (не SPA-переход) — сознательно
      // просто, две разные страницы движка, велосипед клиентского
      // роутинга между ними не нужен.
      if (this.selectedIds.length !== 1 || !CONFIG.createChildDocumentUrl) return;
      const id = this.selectedIds[0];
      window.location.href = CONFIG.createChildDocumentUrl + '/new?from_request=' + encodeURIComponent(id);
    },

    showDocumentsChain() {
      // "Показать подчинённые документы" (v73): активна только при
      // РОВНО одном выделенном элементе. Переход на полноэкранную
      // страницу /documents-chain с query-параметром ?request_id={id}
      // — та страница сама подгружает GET /api/documents-chain/{id}
      // и строит журнал заявка + все дочерние документы (calculation,
      // дальше specification/invoice, когда появятся). Полная
      // перезагрузка, тот же принцип, что и createChildDocument().
      if (this.selectedIds.length !== 1 || !CONFIG.documentsChainUrl) return;
      const id = this.selectedIds[0];
      window.location.href = CONFIG.documentsChainUrl + '?request_id=' + encodeURIComponent(id);
    },

    async bulkMarkDelete(value) {
      // Групповая пометка/снятие пометки на удаление — БЕЗУСЛОВНО
      // проставляет is_deleted=value всем выделенным записям (не
      // переключатель): если среди выделенных уже есть помеченная
      // позиция, при "Пометить на удаление" она остаётся помеченной
      // (значение просто перезаписывается тем же), при "Снять пометку" —
      // аналогично. Ведёт себя предсказуемо независимо от текущего
      // статуса каждой конкретной строки.
      if (this.selectedIds.length === 0) return;
      try {
        hideJsError();
        const res = await fetch('/api/' + this.currentLevel().key + '/bulk-mark-delete', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ ids: this.selectedIds, value: value })
        });
        if (!res.ok) {
          showJsError(await extractErrorMessage(res));
          return;
        }
        this.selectedIds = [];
        await this.load();
      } catch (err) { showJsError(err); }
    },

    onComputedChange(changedField) {
      try {
        for (const pair of this.currentLevel().computedPairs) {
          if (changedField !== pair.fieldA && changedField !== pair.fieldB) continue;
          const rate = pair.rateConstantKey
            ? Number(this.constants[pair.rateConstantKey]) || 0
            : (this.editing[pair.rateField] || 0);
          if (changedField === pair.fieldA) {
            const a = this.editing[pair.fieldA] || 0;
            this.editing[pair.fieldB] = applyFormula(pair.formula, 'forward', a, rate);
          } else {
            const b = this.editing[pair.fieldB] || 0;
            this.editing[pair.fieldA] = applyFormula(pair.formula, 'backward', b, rate);
          }
          this.editing._changed_field = changedField;
        }
      } catch (err) { showJsError(err); }
    },

    // Проверяет обязательные поля и заполненность ставок НДС ДО
    // отправки на сервер — чтобы пользователь сразу видел понятную
    // причину, а не общую ошибку сервера. Возвращает текст ошибки
    // или null, если всё в порядке.
    validateBeforeSave() {
      const lvl = this.currentLevel();
      const missing = [];
      for (const f of lvl.fields) {
        if (!f.required || f.virtual) continue;
        const value = this.editing[f.name];
        if (value === null || value === undefined || (typeof value === 'string' && value.trim() === '')) {
          missing.push(f.label);
        }
      }
      if (missing.length) {
        return 'Не заполнено обязательное поле: ' + missing.join(', ');
      }
      for (const pair of lvl.computedPairs) {
        const rate = pair.rateConstantKey
          ? this.constants[pair.rateConstantKey]
          : this.editing[pair.rateField];
        if (rate === null || rate === undefined || rate === 0 || rate === '') {
          return 'Не заполнено поле «' + pair.rateLabel + '» — без него нельзя пересчитать «' +
                 pair.fieldALabel + '» / «' + pair.fieldBLabel + '».';
        }
      }
      return null;
    },

    async save() {
      try {
        const validationError = this.validateBeforeSave();
        if (validationError) { showJsError(validationError); return; }
        hideJsError();

        const lvlKey = this.currentLevel().key;
        const isEdit = !!this.editing.id;
        const url = isEdit ? '/api/' + lvlKey + '/' + this.editing.id : '/api/' + lvlKey;
        const method = isEdit ? 'PUT' : 'POST';

        const res = await fetch(url, {
          method,
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(this.editing)
        });
        if (!res.ok) {
          showJsError(await extractErrorMessage(res));
          return;
        }
        if (CONFIG.renderMode === 'form') {
          this.closeToList();
        } else {
          this.modalOpen = false;
          await this.load();
        }
      } catch (err) { showJsError(err); }
    },

    async remove() {
      try {
        const res = await fetch('/api/' + this.currentLevel().key + '/' + this.editing.id, { method: 'DELETE' });
        if (!res.ok) {
          showJsError('Не удалось удалить. ' + await extractErrorMessage(res));
          return;
        }
        if (CONFIG.renderMode === 'form') {
          this.closeToList();
        } else {
          this.modalOpen = false;
          await this.load();
        }
      } catch (err) { showJsError(err); }
    },

    // --- drill-down навигация (только для CONFIG.hierarchyRoot) ---

    async drillOpen(item) {
      // hasNextLevel — единое место истины, что вглубь реально есть
      // куда идти (см. геттер выше: не только childKey в конфиге, но
      // и реальное присутствие следующего уровня в LEVELS).
      if (!this.hasNextLevel) return;
      try {
        hideJsError();
        this.drillPath.push({ parentId: item.id, label: item.name });
        this.page = 1;
        this.q = '';
        this.selectedIds = [];
        await this.load();
      } catch (err) { showJsError(err); }
    },

    rowClick(item) {
      // Клик по телу строки drill-list: если есть следующий уровень
      // дерева — углубляемся (kit_group → kit_section, и т.д.), если
      // это нижний уровень (kit) — сразу открываем карточку/модалку
      // редактирования, тем же способом, что и раньше давала только
      // отдельная маленькая иконка ✎ (см. HANDOFF: тап по всей строке
      // должен работать, не только по иконке — иконку сложно поймать
      // пальцем на телефоне).
      if (this.hasNextLevel) {
        this.drillOpen(item);
      } else {
        this.openEdit(item);
      }
    },

    async drillBack() {
      if (this.drillPath.length === 0) return;
      try {
        hideJsError();
        this.drillPath.pop();
        this.page = 1;
        this.q = '';
        this.selectedIds = [];
        await this.load();
      } catch (err) { showJsError(err); }
    },

    async drillGoTo(crumbIndex) {
      // crumbIndex 0 — корень (крошка "Группы" и т.п.), crumbIndex N —
      // drillPath[N-1]. Обрезаем drillPath до этой глубины и
      // перезагружаем список текущего (теперь более верхнего) уровня.
      if (crumbIndex >= this.drillPath.length) return;
      try {
        hideJsError();
        this.drillPath = this.drillPath.slice(0, crumbIndex);
        this.page = 1;
        this.q = '';
        this.selectedIds = [];
        await this.load();
      } catch (err) { showJsError(err); }
    },

    close() {
      try {
        hideJsError();
        if (CONFIG.renderMode === 'form') {
          this.closeToList();
          return;
        }
        this.modalOpen = false;
        this.kitItems = [];
      } catch (err) { showJsError(err); }
    }
  };
}
</script>
{% endblock %}
"""


def _build_form_layout(config: TableConfig, tab: Optional[str] = None) -> list[dict]:
    """
    Строит готовую раскладку полей формы по рядам, вычисляемую ДО
    рендера — чтобы в шаблоне не было двух отдельных циклов (form_rows
    отдельно, "остальные" поля отдельно), из-за которых раньше поля
    уезжали не в том порядке или пропадали.

    Идёт по config.fields строго в порядке их объявления. Если поле
    принадлежит какому-то form_row и этот row ещё не был эмитирован —
    эмитит весь ряд целиком (в порядке field_names этого row).
    Если поле не входит ни в один form_row — эмитит как одиночный ряд.
    Поля с in_form=False пропускаются полностью.

    tab: если config.form_tabs задан — строит раскладку ТОЛЬКО для
    полей этой вкладки (f.tab == tab; поле без явного tab считается
    принадлежащим первой вкладке — form_tabs[0]). None (или у таблицы
    вообще нет вкладок) — раскладка строится по всем полям сразу, как
    было раньше.

    Возвращает список {"fields": [FieldConfig, ...], "is_computed_pair": bool}.
    """
    computed_field_names = {p.field_a for p in config.computed_pairs} | {
        p.field_b for p in config.computed_pairs
    }
    fields_by_name = {f.name: f for f in config.fields}
    default_tab = config.form_tabs[0] if config.form_tabs else None

    def _field_tab(f: FieldConfig) -> Optional[str]:
        return f.tab or default_tab

    def _in_tab(f: FieldConfig) -> bool:
        return tab is None or _field_tab(f) == tab

    row_of_field: dict[str, int] = {}
    for row_index, row in enumerate(config.form_rows):
        for name in row.field_names:
            row_of_field[name] = row_index

    emitted_rows: set[int] = set()
    layout: list[dict] = []

    for f in config.fields:
        if not f.in_form or not _in_tab(f):
            continue
        if f.name in row_of_field:
            row_index = row_of_field[f.name]
            if row_index in emitted_rows:
                continue
            emitted_rows.add(row_index)
            row_field_names = config.form_rows[row_index].field_names
            row_fields = [
                fields_by_name[name]
                for name in row_field_names
                if name in fields_by_name and fields_by_name[name].in_form and _in_tab(fields_by_name[name])
            ]
            is_pair = any(name in computed_field_names for name in row_field_names)
            layout.append({"fields": row_fields, "is_computed_pair": is_pair})
        else:
            is_pair = f.name in computed_field_names
            layout.append({"fields": [f], "is_computed_pair": is_pair})

    return layout


def _serialize_level_config(config: TableConfig) -> dict:
    """Сериализует один TableConfig в JSON-совместимый словарь — общая
    часть для обычного (плоского) config_json и для каждого элемента
    CONFIG.levels у hierarchy-таблиц (см. _build_hierarchy_levels)."""
    computed_field_names = {p.field_a for p in config.computed_pairs} | {
        p.field_b for p in config.computed_pairs
    }
    return {
        "key": config.key,
        "title": config.title,
        "titleSingular": config.title_singular,
        "deleteMode": config.delete_mode,
        "allowCreate": config.allow_create,
        "allowDelete": config.allow_delete,
        "editMode": config.edit_mode,
        "documentNumberField": config.document_number_field,
        "defaultSortField": config.default_sort_field,
        "defaultSortDir": config.default_sort_dir,
        "defaultSortFields": [[f, d] for f, d in config.default_sort_fields],
        "needsConstants": config.needs_constants,
        "extraLookups": config.extra_lookups,
        "formTabs": config.form_tabs,
        "createChildDocumentUrl": config.create_child_document_url,
        "documentsChainUrl": config.documents_chain_url,
        "ownPageUrl": config.own_page_url,
        "materialsTab": config.materials_tab,
        "materialsItemTableKey": config.materials_item_table_key,
        "materialsRecalcAction": config.materials_recalc_action,
        "kitsTab": config.kits_tab,
        "kitsItemTableKey": config.kits_item_table_key,
        "readonlyItemsTab": config.readonly_items_tab,
        "readonlyItemsTableKey": config.readonly_items_table_key,
        "invoiceItemsTab": config.invoice_items_tab,
        "invoiceItemsTableKey": config.invoice_items_table_key,
        "invoiceItemsDiscountField": config.invoice_items_discount_field,
        "invoiceItemsPriceField": config.invoice_items_price_field,
        "invoiceItemsPriceAfterDiscountField": config.invoice_items_price_after_discount_field,
        "invoiceItemsLineTotalField": config.invoice_items_line_total_field,
        "invoiceItemsSumField": config.invoice_items_sum_field,
        "invoiceItemsBulkDiscountAction": config.invoice_items_bulk_discount_action,
        "openEditAction": config.open_edit_action,
        "fields": [
            {
                "name": f.name,
                "label": f.label,
                "isNumeric": f.is_numeric,
                "default": f.default,
                "defaultFromConstant": f.default_from_constant,
                "defaultFirstOption": f.default_first_option,
                "required": f.required,
                "virtual": f.virtual,
                "widget": f.widget,
                "options": f.options,
                "radioLabelsField": f.radio_labels_field,
                "radioLabelsAction": f.radio_labels_action,
                "listAsDot": f.list_as_dot,
                "dotColors": f.dot_colors,
                "inForm": f.in_form,
            }
            for f in config.fields
        ],
        "relations": [
            {"field": r.field, "target_table": r.target_table, "display_field": r.display_field}
            for r in config.relations
        ],
        "computedPairs": [
            {
                "fieldA": p.field_a,
                "fieldB": p.field_b,
                "rateField": p.rate_field,
                "rateConstantKey": p.rate_constant_key,
                "formula": p.formula,
                "fieldALabel": p.label_a,
                "fieldBLabel": p.label_b,
                "rateLabel": p.label_rate,
            }
            for p in config.computed_pairs
        ],
        "toggleableSearchFields": [
            {"name": f.name, "label": f.label, "default": f.search_default}
            for f in config.toggleable_search_fields()
        ] if config.enable_search_toggles else [],
        "alwaysSearchedFields": config.always_searched_fields() if config.enable_search_toggles else [],
        "toggleableSearchRelations": [
            {
                "field": r.field,
                "label": r.search_label or r.label,
                "default": r.search_default,
            }
            for r in config.toggleable_search_relations()
        ] if config.enable_search_toggles else [],
        "alwaysSearchedRelationFields": (
            [r.field for r in config.always_searched_relations()] if config.enable_search_toggles else []
        ),
        "formLayoutFields": [
            {
                "name": f.name,
                "label": f.label,
                "widget": f.widget,
                "required": f.required,
                "placeholder": f.placeholder,
                "readonly": f.readonly,
                "virtual": f.virtual,
                "sourceConstantKey": f.source_constant_key,
                "isComputed": f.name in computed_field_names,
                "options": f.options,
                "radioLabelsField": f.radio_labels_field,
                "hint": f.hint,
                "inlineAction": f.inline_action,
            }
            for f in config.fields if f.in_form
        ],
        "hierarchy": {
            "parentField": config.hierarchy.parent_field,
            "parentKey": config.hierarchy.parent_key,
            "childKey": config.hierarchy.child_key,
            "rootLabel": config.hierarchy.root_label,
        } if config.hierarchy else None,
        "itemsSource": _serialize_items_source(config) if config.edit_mode == "items_modal" else None,
    }


def _serialize_items_source(config: TableConfig) -> Optional[dict]:
    """Для edit_mode="items_modal" сериализует ДОЧЕРНЮЮ таблицу
    (config.items_source_table_key, например kit_item для kit)
    рекурсивно через ту же _serialize_level_config — переиспользует
    формат уровня дерева (fields/relations/formLayoutFields), так как
    модалке состава нужно ровно то же самое: чем загрузить список
    (?parent_id={editing.id} через hierarchy.parent_field дочерней
    таблицы) и чем отрисовать простую форму добавления новой записи.
    Возвращает None и не падает, если items_source_table_key не задан
    или таблица с таким key не найдена в ALL_TABLES — ошибка
    конфигурации, а не пользователя, но лучше показать пустую модалку,
    чем уронить всю страницу дерева."""
    if not config.items_source_table_key:
        return None
    from app.engine.tables import ALL_TABLES
    source = next((t for t in ALL_TABLES if t.key == config.items_source_table_key), None)
    if not source:
        return None
    return _serialize_level_config(source)


def _build_hierarchy_levels(root_config: TableConfig) -> list[dict]:
    """Собирает цепочку УРОВНЕЙ дерева, начиная с root_config, следуя
    hierarchy.child_key рекурсивно (kit_group -> kit_section -> kit...).
    Импорт ALL_TABLES внутри функции — тот же паттерн локального
    импорта, что и в engine/api.py, чтобы не создавать циклическую
    зависимость tables.py -> page.py -> tables.py на уровне модуля.

    Отсутствующий в ALL_TABLES child_key (например "kit" ещё не
    реализован) просто обрывает цепочку на последнем существующем
    уровне — страница отрисуется без последнего шага, а не упадёт;
    когда kit появится в ALL_TABLES, следующий рендер подхватит его
    без изменений в этой функции."""
    from app.engine.tables import ALL_TABLES
    by_key = {t.key: t for t in ALL_TABLES}

    levels = []
    current = root_config
    seen = set()
    while current is not None and current.key not in seen:
        seen.add(current.key)
        levels.append(_serialize_level_config(current))
        next_key = current.hierarchy.child_key if current.hierarchy else None
        current = by_key.get(next_key) if next_key else None
    return levels


def render_table_page(config: TableConfig, jinja_env, render_mode: str = "both") -> str:
    """Рендерит HTML-страницу для таблицы. jinja_env должен быть
    окружением Jinja2Templates.env приложения (то же, что использует
    base.html) — это позволяет {% extends "base.html" %} сработать
    корректно, так как шаблон ищется через тот же loader, что и
    остальные файловые шаблоны приложения.

    render_mode (v75, только для ПЛОСКИХ таблиц — см. ниже):
      "both" — список + модалка на одной странице (старое поведение,
        единственный режим ДО v75, всё ещё единственный для
        hierarchy-таблиц — drill-down в эту переделку не входил, см.
        обсуждение с Вахтангом: форма редактирования kit_group/
        kit_section — маленькая модалка, отдельная страница на неё
        не нужна и не запрашивалась).
      "list" — только список, БЕЗ модалки в разметке вообще; клик по
        строке/кнопка "+ Запись" переходят на "form"-страницу этого
        же документа (см. openDocumentRow()/openCreateRow() в JS).
      "form" — только форма редактирования/создания, отрендеренная НЕ
        оверлеем, а на весь экран (см. inline style в шаблоне),
        открывающая нужную запись сама при загрузке (см.
        maybeOpenOwnPage() в JS) и уходящая НАЗАД (history.back(),
        см. closeToList()) вместо скрытия модалки.

    Для hierarchy-таблиц render_mode игнорируется — они всегда
    рендерятся в старом режиме "both" независимо от переданного
    значения, т.к. вся эта фича относится только к документам с
    собственным own_page_url (request/calculation), не к деревьям
    справочников.

    Для hierarchy-таблиц (config.hierarchy задан) рендерится ТОЛЬКО
    для корневого уровня дерева (config.hierarchy.parent_key is None,
    например kit_group) — register.py регистрирует HTML-страницу для
    каждой TableConfig из ALL_TABLES, но не-корневые уровни (kit_section)
    не получают собственный маршрут /kit_section-v2: вся навигация
    вглубь дерева происходит внутри ОДНОЙ страницы корневого уровня
    (см. CONFIG.levels в JS) без перезагрузки. Не-корневой hierarchy
    рендерит явную заглушку вместо страницы, чтобы по ошибке открытый
    URL не показывал пустую нерабочую страницу молча."""

    if config.hierarchy and not config.hierarchy.is_root():
        template = jinja_env.from_string(_NON_ROOT_HIERARCHY_TEMPLATE_SOURCE)
        return template.render(config=config)

    effective_render_mode = "both" if config.hierarchy else render_mode

    computed_field_names = {p.field_a for p in config.computed_pairs} | {
        p.field_b for p in config.computed_pairs
    }

    if config.hierarchy:
        config_json = json.dumps({
            "key": config.key,
            "hierarchyRoot": True,
            "levels": _build_hierarchy_levels(config),
        }, ensure_ascii=False)
    else:
        config_json = json.dumps(
            _serialize_level_config(config) | {"hierarchyRoot": False, "renderMode": effective_render_mode},
            ensure_ascii=False,
        )

    # form_layout_by_tab: если у таблицы заданы вкладки формы
    # (config.form_tabs), строим отдельную раскладку рядов НА КАЖДУЮ
    # вкладку — {"Основное": [...], "Настройки": [...]}. Без вкладок
    # (form_tabs пуст, как у всех таблиц до calculation) — один "виртуальный"
    # таб под ключом "" с полной раскладкой, как было раньше; шаблон
    # определяет наличие вкладок по config.form_tabs, не по этому словарю.
    if config.form_tabs:
        form_layout_by_tab = {tab: _build_form_layout(config, tab=tab) for tab in config.form_tabs}
    else:
        form_layout_by_tab = {"": _build_form_layout(config)}
    action_buttons_by_tab: dict[str, list] = {}
    for btn in config.action_buttons:
        key = btn.tab or (config.form_tabs[0] if config.form_tabs else "")
        action_buttons_by_tab.setdefault(key, []).append(btn)

    toggleable_search_fields = config.toggleable_search_fields() if config.enable_search_toggles else []
    toggleable_search_relations = config.toggleable_search_relations() if config.enable_search_toggles else []

    template = jinja_env.from_string(_PAGE_TEMPLATE_SOURCE)
    return template.render(
        config=config,
        config_json=config_json,
        render_mode=effective_render_mode,
        form_layout_by_tab=form_layout_by_tab,
        action_buttons_by_tab=action_buttons_by_tab,
        computed_field_names=computed_field_names,
        toggleable_search_fields=toggleable_search_fields,
        toggleable_search_relations=toggleable_search_relations,
    )
