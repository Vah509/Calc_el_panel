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

from app.engine.config import TableConfig


_PAGE_TEMPLATE_SOURCE = r"""
{% extends "base.html" %}
{% block content %}
<div x-data="enginePage()" x-init="init()">

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
            @click="activeFilters['{{ rel.field }}'] = opt.id; page=1; load()" x-text="opt.name"></span>
    </template>
    {% endfor %}
    {% endif %}

  </div>

  <div class="table-wrap">
    <table>
      <thead>
        <tr>
          {% if config.soft_delete %}
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
            {% if config.soft_delete %}
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
          <td colspan="{{ config.fields | selectattr('in_list') | list | length + 1 + (1 if config.soft_delete else 0) }}" style="text-align:center; color:var(--ink-soft); padding:24px;">Ничего не найдено</td>
        </tr>
      </tbody>
    </table>
  </div>

  <div class="pagination" x-show="totalPages > 1">
    <button type="button" @click="prevPage()" :disabled="page <= 1">‹ Назад</button>
    <span x-text="'Стр. ' + page + ' из ' + totalPages"></span>
    <button type="button" @click="nextPage()" :disabled="page >= totalPages">Далее ›</button>
  </div>

  <div class="modal-backdrop" x-show="modalOpen" x-cloak>
    <div class="modal">
      <div class="modal-header">
        <div>
          <h2 x-text="editing.id ? 'Редактирование' : 'Новая запись'"></h2>
        </div>
      </div>

      <div id="js-error-banner" style="display:none; background:#f3e6e3; border:1px solid #9c3b2e; color:#9c3b2e; padding:10px 16px; margin:0 20px 14px; border-radius:6px; font-family:monospace; font-size:12px; white-space:pre-wrap;"></div>

      <div class="modal-body">
        {% for row in form_layout %}
        <div{% if row.is_computed_pair %} class="price-pair"{% elif row.fields | length > 1 %} class="field-row"{% endif %}>
          {% for f in row.fields %}
          {% set rel = config.relations | selectattr("field", "equalto", f.name) | first %}
          <div class="field"{% if f.form_width %} style="flex: 0 0 {{ f.form_width }};"{% endif %}>
            <label>{{ f.label }}</label>
            {% if rel %}
            <select x-model.number="editing.{{ f.name }}">
              <option :value="null">—</option>
              <template x-for="opt in relationOptions['{{ f.name }}']" :key="opt.id">
                <option :value="opt.id" x-text="opt.name"></option>
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
      </div>

      <div class="modal-footer">
        {% if config.allow_delete %}
        <button type="button" class="btn btn-danger-ghost" x-show="editing.id" @click="remove()">
          {% if config.soft_delete %}
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

    async init() {
      try {
        for (const f of CONFIG.toggleableSearchFields) {
          // состояние чекбокса при первой загрузке — берётся из
          // search_default конкретного поля (см. FieldConfig); дальше
          // человек может переключать вручную, выбор держится, пока
          // страница открыта (не сбрасывается при новом поиске/фильтре).
          this.searchFields[f.name] = f.default;
        }
        for (const rel of CONFIG.relations) {
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
        const needsConstants = CONFIG.fields.some(f => f.virtual) ||
          CONFIG.computedPairs.some(p => p.rateConstantKey);
        if (needsConstants) {
          const res = await fetch('/api/constant?page_size=1000');
          const data = await res.json();
          for (const row of data.items) { this.constants[row.key] = row.value; }
        }
        await this.load();
      } catch (err) { showJsError(err); }
    },

    relationName(fieldName, id) {
      const rel = CONFIG.relations.find(r => r.field === fieldName);
      if (!rel) return '';
      const opts = this.relationOptions[fieldName] || [];
      const found = opts.find(o => o.id === id);
      return found ? found.name : '';
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
        const params = new URLSearchParams();
        if (this.q) params.set('q', this.q);
        if (CONFIG.toggleableSearchFields.length > 0) {
          // Явно передаём набор активных полей поиска — какие из
          // toggleable-полей отмечены галочкой + всегда-искомые поля
          // (searchable=True, search_toggle=False, например артикул).
          for (const f of CONFIG.toggleableSearchFields) {
            if (this.searchFields[f.name]) params.append('search_fields', f.name);
          }
          for (const name of CONFIG.alwaysSearchedFields) {
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
        params.set('page', this.page);
        const res = await fetch('/api/' + CONFIG.key + '?' + params.toString());
        const data = await res.json();
        this.items = data.items;
        this.page = data.page;
        this.totalPages = data.total_pages;
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
        const blank = {};
        for (const f of CONFIG.fields) {
          if (f.default !== null && f.default !== undefined) {
            blank[f.name] = f.default;
          } else {
            blank[f.name] = f.isNumeric ? 0 : '';
          }
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
      } catch (err) { showJsError(err); }
    },

    onComputedChange(changedField) {
      try {
        for (const pair of CONFIG.computedPairs) {
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
      const missing = [];
      for (const f of CONFIG.fields) {
        if (!f.required || f.virtual) continue;
        const value = this.editing[f.name];
        if (value === null || value === undefined || (typeof value === 'string' && value.trim() === '')) {
          missing.push(f.label);
        }
      }
      if (missing.length) {
        return 'Не заполнено обязательное поле: ' + missing.join(', ');
      }
      for (const pair of CONFIG.computedPairs) {
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

        const isEdit = !!this.editing.id;
        const url = isEdit ? '/api/' + CONFIG.key + '/' + this.editing.id : '/api/' + CONFIG.key;
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
        const res = await fetch('/api/' + CONFIG.key + '/' + this.editing.id, { method: 'DELETE' });
        if (!res.ok) {
          showJsError('Не удалось удалить. ' + await extractErrorMessage(res));
          return;
        }
        this.modalOpen = false;
        await this.load();
      } catch (err) { showJsError(err); }
    },

    close() {
      try { hideJsError(); this.modalOpen = false; } catch (err) { showJsError(err); }
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


def render_table_page(config: TableConfig, jinja_env) -> str:
    """Рендерит HTML-страницу списка+модалки для таблицы. jinja_env
    должен быть окружением Jinja2Templates.env приложения (то же,
    что использует base.html) — это позволяет {% extends "base.html" %}
    сработать корректно, так как шаблон ищется через тот же loader,
    что и остальные файловые шаблоны приложения."""

    computed_field_names = {p.field_a for p in config.computed_pairs} | {
        p.field_b for p in config.computed_pairs
    }

    config_json = json.dumps({
        "key": config.key,
        "softDelete": config.soft_delete,
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
    }, ensure_ascii=False)

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
