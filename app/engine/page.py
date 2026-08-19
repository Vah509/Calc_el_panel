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

from app.engine.config import TableConfig


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

  {% if not config.hierarchy %}
  <div class="topbar">
    <div class="topbar-title">
      <h1>{{ config.title }}</h1>
      <span class="count" x-text="items.length + ' позиций'"></span>
    </div>
    <div style="display:flex; gap:8px;">
      {% if config.allow_create %}
      <button class="btn btn-primary" @click="openCreate()">+ {{ config.title_singular|capitalize }}</button>
      {% endif %}
    </div>
  </div>

  {% if config.allow_create %}
  <div class="selection-bar" x-show="selectedIds.length > 0" x-cloak>
    <span x-text="selectedIds.length + ' выделено'"></span>
    <button type="button" class="btn" :disabled="selectedIds.length !== 1" @click="copySelected()">Копировать</button>
    {% if config.delete_mode == "soft" %}
    <button type="button" class="btn" @click="bulkMarkDelete(true)">Пометить на удаление</button>
    <button type="button" class="btn" @click="bulkMarkDelete(false)">Снять пометку</button>
    {% endif %}
    <button type="button" class="selection-clear" @click="selectedIds = []">Снять выделение</button>
  </div>
  {% endif %}

  {% if config.enable_search_toggles and toggleable_search_fields %}
  <div class="search-toggles-row">
    {% for f in toggleable_search_fields %}
    <label class="search-toggle-chip">
      <input type="checkbox" x-model="searchFields['{{ f.name }}']" @change="onSearchFieldsChange()">
      {{ f.label }}
    </label>
    {% endfor %}
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
    <span style="width:1px;height:20px;background:var(--line);margin:0 4px;"></span>
    <span class="chip" :class="{active: !activeFilters['{{ rel.field }}']}" @click="activeFilters['{{ rel.field }}']=null; page=1; load()">Все</span>
    <template x-for="opt in relationOptions['{{ rel.field }}']" :key="opt.id">
      <span class="chip" :class="{active: activeFilters['{{ rel.field }}'] === opt.id}"
            @click="activeFilters['{{ rel.field }}'] = opt.id; page=1; load()" x-text="opt['{{ rel.display_field }}']"></span>
    </template>
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
          <tr @click="openEdit(item)">
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

  <div class="modal-backdrop" x-show="modalOpen" x-cloak>
    <div class="modal">
      <div class="modal-header">
        <div>
          <h2 x-show="!isItemsModal() || !editing.id" x-text="editing.id ? 'Редактирование' : 'Новая запись'"></h2>
          <h2 x-show="isItemsModal() && editing.id" x-text="editing.name || ''"></h2>
        </div>
      </div>

      <div id="js-error-banner" style="display:none; background:#f3e6e3; border:1px solid #9c3b2e; color:#9c3b2e; padding:10px 16px; margin:0 20px 14px; border-radius:6px; font-family:monospace; font-size:12px; white-space:pre-wrap;"></div>

      <div class="modal-body">
        {% if not config.hierarchy %}
        {% for row in form_layout %}
        <div{% if row.is_computed_pair %} class="price-pair"{% elif row.fields | length > 1 %} class="field-row"{% endif %}>
          {% for f in row.fields %}
          {% set rel = config.relations | selectattr("field", "equalto", f.name) | first %}
          <div class="field"{% if f.form_width %} style="flex: 0 0 {{ f.form_width }};"{% endif %}>
            {% set pair_as_b = config.computed_pairs | selectattr("field_b", "equalto", f.name) | selectattr("rate_constant_key") | first %}
            {% if pair_as_b %}
            <label>{{ f.label }} (<span x-text="constants['{{ pair_as_b.rate_constant_key }}'] ?? ''"></span>%)</label>
            {% else %}
            <label>{{ f.label }}</label>
            {% endif %}
            {% if rel %}
            <select x-model.number="editing.{{ f.name }}">
              <option :value="null">—</option>
              <template x-for="opt in relationOptions['{{ f.name }}']" :key="opt.id">
                <option :value="opt.id" x-text="opt['{{ rel.display_field }}']"></option>
              </template>
            </select>
            {% elif f.virtual %}
            <span class="field-readonly-text" x-text="constants['{{ f.source_constant_key }}'] ?? ''"></span>
            {% elif f.readonly %}
            <span class="field-readonly-text" x-text="editing.{{ f.name }} ?? ''"></span>
            {% elif f.name in computed_field_names %}
            <input type="number" step="0.01" x-model.number="editing.{{ f.name }}" @input="onComputedChange('{{ f.name }}')">
            {% elif f.widget == "number" %}
            <input type="number" step="0.01"{% if f.required %} required{% endif %} placeholder="{{ f.placeholder }}" x-model.number="editing.{{ f.name }}">
            {% else %}
            <input type="text"{% if f.required %} required{% endif %} placeholder="{{ f.placeholder }}" x-model="editing.{{ f.name }}">
            {% endif %}
          </div>
          {% endfor %}
        </div>
        {% endfor %}
        {% if config.computed_pairs %}
        <div class="vat-note">↻ Пересчитывается автоматически при изменении одного из полей — можно переопределить вручную.</div>
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
    <div class="picker-top-actions">
      <button type="button" class="btn btn-ghost" @click="pickerCancel()">Отмена</button>
      <button type="button" class="btn btn-primary" @click="pickerSave()">Сохранить состав</button>
    </div>

    <div class="picker-pane picker-pane-top" :style="'flex: 0 0 ' + pickerSplit + '%;'">
      <div class="picker-pane-header">
        <span x-text="pickerDraft.length + ' позиций'"></span>
      </div>
      <div class="picker-list">
        <template x-for="(row, idx) in pickerDraft" :key="row._key">
          <div class="picker-row">
            <span class="picker-row-name" x-text="materialLabel(row.material_id)"></span>
            <div class="picker-qty-control">
              <button type="button" class="picker-qty-btn" @click="pickerDecrement(idx)">−</button>
              <span class="picker-qty-value" x-text="row.quantity"></span>
              <button type="button" class="picker-qty-btn" @click="pickerIncrement(idx)">+</button>
            </div>
            <button type="button" class="picker-row-remove" @click="pickerRemoveRow(idx)">🗑</button>
          </div>
        </template>
        <div class="picker-row picker-row-empty" x-show="pickerDraft.length === 0">Пока ничего не выбрано</div>
      </div>
    </div>

    <div class="picker-handle" @pointerdown="pickerDragStart($event)"><div class="picker-handle-bar"></div></div>

    <div class="picker-pane picker-pane-bottom" :style="'flex: 0 0 ' + (100 - pickerSplit) + '%;'">
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
          <!-- Тап по ВСЕЙ строке добавляет материал в "Отобрано" — та же
               логика, что и в v45 для drill-list: маленькая кнопка
               "+ Добавить" остаётся видимой как визуальный ориентир, но
               перестала быть единственным способом (по прямой просьбе:
               "вместо кнопочки добавить просто тапнуть на позицию"). -->
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
  </div>

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

function applyFormula(formulaName, direction, value, rate) {
  const formula = ENGINE_FORMULAS[formulaName];
  if (!formula) { showJsError('Неизвестная формула: ' + formulaName); return value; }
  return formula[direction](value, rate);
}

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
    modalOpen: false,
    editing: {},
    sortBy: null,
    sortDir: 'asc',
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
    // backdrop, открывается кнопкой "Редактировать" в модалке kit) ---
    pickerOpen: false,
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
        for (const rel of lvl.relations) {
          // page_size=1000 — выпадающему списку/фильтру нужен весь
          // справочник целиком, а не одна страница (см. решение по
          // пагинации: явный page_size приоритетнее default_page_size).
          const res = await fetch('/api/' + rel.target_table + '?page_size=1000');
          const data = await res.json();
          this.relationOptions[rel.field] = data.items;
          this.activeFilters[rel.field] = null;
        }
        // Подтягиваем constants, если таблице нужна хотя бы одна
        // "живая ссылка" — virtual-поле (например ставка НДС в
        // карточке материала) или computed pair со ставкой из
        // справочника, а не из собственного поля записи.
        const needsConstants = lvl.fields.some(f => f.virtual) ||
          lvl.computedPairs.some(p => p.rateConstantKey);
        if (needsConstants) {
          const res = await fetch('/api/constant?page_size=1000');
          const data = await res.json();
          for (const row of data.items) { this.constants[row.key] = row.value; }
        }
        await this.load();
      } catch (err) { showJsError(err); }
    },

    relationName(fieldName, id) {
      const rel = this.currentLevel().relations.find(r => r.field === fieldName);
      if (!rel) return '';
      const opts = this.relationOptions[fieldName] || [];
      const found = opts.find(o => o.id === id);
      return found ? found[rel.display_field] : '';
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
        if (lvl.toggleableSearchFields.length > 0) {
          // Явно передаём набор активных полей поиска — какие из
          // toggleable-полей отмечены галочкой + всегда-искомые поля
          // (searchable=True, search_toggle=False, например артикул).
          for (const f of lvl.toggleableSearchFields) {
            if (this.searchFields[f.name]) params.append('search_fields', f.name);
          }
          for (const name of lvl.alwaysSearchedFields) {
            params.append('search_fields', name);
          }
        }
        for (const [field, value] of Object.entries(this.activeFilters)) {
          if (value !== null && value !== undefined) params.set(field, value);
        }
        if (this.sortBy) {
          params.set('sort_by', this.sortBy);
          params.set('sort_dir', this.sortDir);
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

    openCreate() {
      try {
        hideJsError();
        const lvl = this.currentLevel();
        const blank = {};
        for (const f of lvl.fields) {
          if (f.default !== null && f.default !== undefined) {
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
      } catch (err) { showJsError(err); }
    },

    openEdit(item) {
      try {
        hideJsError();
        this.editing = { ...item };
        this.modalOpen = true;
        if (this.isItemsModal()) {
          this.loadKitItems();
        }
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
      const opts = this.itemRelationOptions['material_id'] || [];
      const found = opts.find(o => o.id === materialId);
      return found ? found.short_name : '';
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
      // ещё нет в itemRelationOptions (например появился после того как
      // модалка kit уже загрузилась), добавляем его на лету.
      const opts = this.itemRelationOptions['material_id'] || [];
      if (!opts.some(o => o.id === material.id)) {
        this.itemRelationOptions['material_id'] = [...opts, material];
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
      // (см. HANDOFF, 2.9: кнопка "Отмена" обязательна). Возврат СРАЗУ
      // на экран со списком комплектов (drill-list), БЕЗ промежуточного
      // показа модалки просмотра состава — раньше здесь стояло
      // modalOpen = true, и после закрытия пикера человек попадал на
      // модалку "Подключение 25а", которую нужно было закрывать ещё
      // раз отдельным тапом (см. HANDOFF: "окно там не нужно, его можно
      // закрывать и сам не выходить на экран с перечнем комплектов").
      this.pickerOpen = false;
      this.pickerDraft = [];
      this.modalOpen = false;
      this.editing = {};
      this.kitItems = [];
    },

    async pickerSave() {
      try {
        hideJsError();
        const payload = {
          items: this.pickerDraft.map(row => ({ material_id: row.material_id, quantity: row.quantity })),
        };
        const res = await fetch('/api/kit/' + this.editing.id + '/items', {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
        });
        if (!res.ok) {
          showJsError(await extractErrorMessage(res));
          return;
        }
        // Состав уже сохранён на сервере (см. запрос выше) — обновляем
        // список drill-list, чтобы актуальные данные подтянулись при
        // следующем открытии этого комплекта. Возврат СРАЗУ на список
        // комплектов, БЕЗ промежуточного показа модалки просмотра
        // состава — та же логика, что и в pickerCancel() выше (см.
        // HANDOFF: модалка на этом шаге не нужна вообще).
        this.pickerOpen = false;
        this.pickerDraft = [];
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
      const viewportHeight = window.innerHeight || document.documentElement.clientHeight;
      const deltaPercent = ((evt.clientY - this.pickerDragStartY) / viewportHeight) * 100;
      let next = this.pickerDragStartSplit + deltaPercent;
      // Диапазон 15-85% — ни одна из двух зон никогда не схлопывается
      // полностью (см. HANDOFF, 2.8).
      if (next < 15) next = 15;
      if (next > 85) next = 85;
      this.pickerSplit = next;
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
        } else {
          // Плоские таблицы (material/brand): как раньше — открывает
          // форму, предзаполненную данными существующей записи, но
          // БЕЗ id — save() увидит отсутствие id и отправит POST
          // (создание новой независимой записи), а не PUT. is_deleted
          // копии всегда сброшен в false. Остальные поля копируются
          // как есть — пользователь правит вручную перед сохранением.
          const copy = { ...item };
          delete copy.id;
          copy.is_deleted = false;
          this.editing = copy;
          this.modalOpen = true;
          this.selectedIds = [];
        }
      } catch (err) { showJsError(err); }
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
        this.modalOpen = false;
        await this.load();
      } catch (err) { showJsError(err); }
    },

    async remove() {
      try {
        const res = await fetch('/api/' + this.currentLevel().key + '/' + this.editing.id, { method: 'DELETE' });
        if (!res.ok) {
          showJsError('Не удалось удалить. ' + await extractErrorMessage(res));
          return;
        }
        this.modalOpen = false;
        await this.load();
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
        this.modalOpen = false;
        this.kitItems = [];
      } catch (err) { showJsError(err); }
    }
  };
}
</script>
{% endblock %}
"""


def _build_form_layout(config: TableConfig) -> list[dict]:
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

    Возвращает список {"fields": [FieldConfig, ...], "is_computed_pair": bool}.
    """
    computed_field_names = {p.field_a for p in config.computed_pairs} | {
        p.field_b for p in config.computed_pairs
    }
    fields_by_name = {f.name: f for f in config.fields}

    row_of_field: dict[str, int] = {}
    for row_index, row in enumerate(config.form_rows):
        for name in row.field_names:
            row_of_field[name] = row_index

    emitted_rows: set[int] = set()
    layout: list[dict] = []

    for f in config.fields:
        if not f.in_form:
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
                if name in fields_by_name and fields_by_name[name].in_form
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
        "fields": [
            {
                "name": f.name,
                "label": f.label,
                "isNumeric": f.is_numeric,
                "default": f.default,
                "required": f.required,
                "virtual": f.virtual,
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


def render_table_page(config: TableConfig, jinja_env) -> str:
    """Рендерит HTML-страницу списка+модалки для таблицы. jinja_env
    должен быть окружением Jinja2Templates.env приложения (то же,
    что использует base.html) — это позволяет {% extends "base.html" %}
    сработать корректно, так как шаблон ищется через тот же loader,
    что и остальные файловые шаблоны приложения.

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
        config_json = json.dumps(_serialize_level_config(config) | {"hierarchyRoot": False}, ensure_ascii=False)

    form_layout = _build_form_layout(config)
    toggleable_search_fields = config.toggleable_search_fields() if config.enable_search_toggles else []

    template = jinja_env.from_string(_PAGE_TEMPLATE_SOURCE)
    return template.render(
        config=config,
        config_json=config_json,
        form_layout=form_layout,
        computed_field_names=computed_field_names,
        toggleable_search_fields=toggleable_search_fields,
    )
