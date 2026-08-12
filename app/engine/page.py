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

  <div id="js-error-banner" style="display:none; background:#f3e6e3; border:1px solid #9c3b2e; color:#9c3b2e; padding:10px 16px; margin:0 0 12px; font-family:monospace; font-size:12px; white-space:pre-wrap;"></div>

  <div class="topbar">
    <div class="topbar-title">
      <h1>{{ config.title }}</h1>
      <span class="count" x-text="items.length + ' позиций'"></span>
    </div>
    <div style="display:flex; gap:8px;">
      <button class="btn btn-primary" @click="openCreate()">+ {{ config.title_singular|capitalize }}</button>
    </div>
  </div>

  <div class="filterbar">
    <div class="search-wrap">
      <input class="search-input" type="text" placeholder="{{ config.search_placeholder }}"
             x-model="q" @input.debounce.300ms="load()">
      <button type="button" class="search-clear" title="Сбросить поиск" @click="q=''; load()">✕</button>
    </div>
    {% if config.relations %}
    {% for rel in config.relations %}
    <span style="width:1px;height:20px;background:var(--line);margin:0 4px;"></span>
    <span class="chip" :class="{active: !activeFilters['{{ rel.field }}']}" @click="activeFilters['{{ rel.field }}']=null; load()">Все</span>
    <template x-for="opt in relationOptions['{{ rel.field }}']" :key="opt.id">
      <span class="chip" :class="{active: activeFilters['{{ rel.field }}'] === opt.id}"
            @click="activeFilters['{{ rel.field }}'] = opt.id; load()" x-text="opt.name"></span>
    </template>
    {% endfor %}
    {% endif %}
  </div>

  <div class="table-wrap">
    <table>
      <thead>
        <tr>
          {% for f in config.fields %}{% if f.in_list %}
          <th{% if f.list_width %} style="width:{{ f.list_width }}"{% endif %}{% if f.is_numeric %} class="col-num"{% endif %}>{{ f.label }}</th>
          {% endif %}{% endfor %}
          <th style="width:70px"></th>
        </tr>
      </thead>
      <tbody>
        <template x-for="item in items" :key="item.id">
          <tr @click="openEdit(item)">
            {% for f in config.fields %}{% if f.in_list %}
            {% set rel = config.relations | selectattr("field", "equalto", f.name) | first %}
            <td{% if f.is_numeric %} class="col-num"{% endif %}>
              {% if rel %}
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
          <td colspan="{{ config.fields | selectattr('in_list') | list | length + 1 }}" style="text-align:center; color:var(--ink-soft); padding:24px;">Ничего не найдено</td>
        </tr>
      </tbody>
    </table>
  </div>

  <div class="modal-backdrop" x-show="modalOpen" x-cloak>
    <div class="modal">
      <div class="modal-header">
        <div>
          <h2 x-text="editing.id ? 'Редактирование' : 'Новая запись'"></h2>
        </div>
      </div>

      <div class="modal-body">
        {% for f in config.fields %}
        {% set rel = config.relations | selectattr("field", "equalto", f.name) | first %}
        {% set pair = config.computed_pairs | selectattr("field_a", "equalto", f.name) | first %}
        {% set pair_b = config.computed_pairs | selectattr("field_b", "equalto", f.name) | first %}
        {% if not pair_b %}
        <div class="field">
          <label>{{ f.label }}</label>
          {% if rel %}
          <select x-model.number="editing.{{ f.name }}">
            <option :value="null">—</option>
            <template x-for="opt in relationOptions['{{ f.name }}']" :key="opt.id">
              <option :value="opt.id" x-text="opt.name"></option>
            </template>
          </select>
          {% elif pair %}
          <input type="number" step="0.01" x-model.number="editing.{{ f.name }}" @input="onComputedChange('{{ f.name }}')">
          {% elif f.widget == "number" %}
          <input type="number" step="0.01"{% if f.required %} required{% endif %} placeholder="{{ f.placeholder }}" x-model.number="editing.{{ f.name }}">
          {% else %}
          <input type="text"{% if f.required %} required{% endif %} placeholder="{{ f.placeholder }}" x-model="editing.{{ f.name }}">
          {% endif %}
        </div>
        {% endif %}
        {% endfor %}
        {% if config.computed_pairs %}
        <div class="vat-note">↻ Пересчитывается автоматически при изменении одного из полей — можно переопределить вручную.</div>
        {% endif %}
      </div>

      <div class="modal-footer">
        <button type="button" class="btn btn-danger-ghost" x-show="editing.id" @click="remove()">Удалить</button>
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
    banner.textContent = 'JS-ошибка: ' + (err && err.message ? err.message : err);
  }
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
    activeFilters: {},
    q: '',
    modalOpen: false,
    editing: {},

    async init() {
      try {
        for (const rel of CONFIG.relations) {
          const res = await fetch('/api/' + rel.target_table);
          this.relationOptions[rel.field] = await res.json();
          this.activeFilters[rel.field] = null;
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

    async load() {
      try {
        const params = new URLSearchParams();
        if (this.q) params.set('q', this.q);
        for (const [field, value] of Object.entries(this.activeFilters)) {
          if (value !== null && value !== undefined) params.set(field, value);
        }
        const res = await fetch('/api/' + CONFIG.key + '?' + params.toString());
        this.items = await res.json();
      } catch (err) { showJsError(err); }
    },

    openCreate() {
      try {
        const blank = {};
        for (const f of CONFIG.fields) blank[f.name] = f.isNumeric ? 0 : '';
        this.editing = blank;
        this.modalOpen = true;
      } catch (err) { showJsError(err); }
    },

    openEdit(item) {
      try {
        this.editing = { ...item };
        this.modalOpen = true;
      } catch (err) { showJsError(err); }
    },

    onComputedChange(changedField) {
      try {
        for (const pair of CONFIG.computedPairs) {
          if (changedField !== pair.fieldA && changedField !== pair.fieldB) continue;
          const rate = this.editing[pair.rateField] || 0;
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

    async save() {
      try {
        const isEdit = !!this.editing.id;
        const url = isEdit ? '/api/' + CONFIG.key + '/' + this.editing.id : '/api/' + CONFIG.key;
        const method = isEdit ? 'PUT' : 'POST';

        const res = await fetch(url, {
          method,
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(this.editing)
        });
        if (!res.ok) {
          const text = await res.text();
          showJsError('Сервер ответил ' + res.status + ': ' + text);
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
          const text = await res.text();
          showJsError('Не удалось удалить. Сервер ответил ' + res.status + ': ' + text);
          return;
        }
        this.modalOpen = false;
        await this.load();
      } catch (err) { showJsError(err); }
    },

    close() {
      try { this.modalOpen = false; } catch (err) { showJsError(err); }
    }
  };
}
</script>
{% endblock %}
"""


def render_table_page(config: TableConfig, jinja_env) -> str:
    """Рендерит HTML-страницу списка+модалки для таблицы. jinja_env
    должен быть окружением Jinja2Templates.env приложения (то же,
    что использует base.html) — это позволяет {% extends "base.html" %}
    сработать корректно, так как шаблон ищется через тот же loader,
    что и остальные файловые шаблоны приложения."""

    config_json = json.dumps({
        "key": config.key,
        "fields": [{"name": f.name, "isNumeric": f.is_numeric} for f in config.fields],
        "relations": [
            {"field": r.field, "target_table": r.target_table, "display_field": r.display_field}
            for r in config.relations
        ],
        "computedPairs": [
            {
                "fieldA": p.field_a,
                "fieldB": p.field_b,
                "rateField": p.rate_field,
                "formula": p.formula,
            }
            for p in config.computed_pairs
        ],
    }, ensure_ascii=False)

    template = jinja_env.from_string(_PAGE_TEMPLATE_SOURCE)
    return template.render(config=config, config_json=config_json)
