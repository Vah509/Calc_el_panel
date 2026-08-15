# app/processors/page.py
# ============================================================
# Рендер HTML-страницы /processors. Тот же паттерн, что
# engine/page.py: jinja_env.from_string(...).render(...), а не
# TemplateResponse — так base.html не нуждается в объекте Request
# в контексте, страница простая (список радио-кнопок + кнопка).
# ============================================================

import json

from app.processors.registry import PROCESSORS


_PAGE_TEMPLATE_SOURCE = """
{% extends "base.html" %}
{% block content %}
<div x-data="processorsPage()" x-init="init()">

  <div class="topbar">
    <div class="topbar-title">
      <h1>Обработки</h1>
    </div>
  </div>

  <div style="padding: 20px; max-width: 640px;">
    <div id="js-error-banner" style="display:none; background:#f3e6e3; border:1px solid #9c3b2e; color:#9c3b2e; padding:10px 16px; margin-bottom:14px; border-radius:6px; font-family:monospace; font-size:12px; white-space:pre-wrap;"></div>
    <div id="js-result-banner" style="display:none; background:#e6f0e6; border:1px solid #2e6b3b; color:#2e6b3b; padding:10px 16px; margin-bottom:14px; border-radius:6px; font-size:13px;"></div>

    <div class="field" style="margin-bottom:16px;">
      <label>Таблица</label>
      <select x-model="selectedTable">
        <template x-for="t in tables" :key="t">
          <option :value="t" x-text="t"></option>
        </template>
      </select>
    </div>

    <div class="field" style="margin-bottom:16px;">
      <label>Функция</label>
      <div style="display:flex; flex-direction:column; gap:8px; margin-top:6px;">
        <template x-for="p in filteredProcessors" :key="p.key">
          <label style="display:flex; align-items:center; gap:8px; font-size:13.5px; font-weight:400; cursor:pointer;">
            <input type="radio" name="processor" :value="p.key" x-model="selectedProcessor">
            <span x-text="p.label"></span>
          </label>
        </template>
        <span x-show="filteredProcessors.length === 0" style="color:var(--ink-soft); font-size:13px;">Для этой таблицы пока нет функций.</span>
      </div>
    </div>

    <button type="button" class="btn btn-primary" :disabled="!selectedProcessor || running" @click="runSelected()">
      <span x-show="!running">Выполнить</span>
      <span x-show="running">Выполняется…</span>
    </button>
  </div>

</div>
<script>
function processorsPage() {
  const PROCESSORS = {{ processors_json | safe }};

  return {
    tables: [...new Set(PROCESSORS.map(p => p.tableKey))],
    selectedTable: PROCESSORS.length ? PROCESSORS[0].tableKey : null,
    selectedProcessor: null,
    running: false,

    get filteredProcessors() {
      return PROCESSORS.filter(p => p.tableKey === this.selectedTable);
    },

    init() {
      if (this.filteredProcessors.length) {
        this.selectedProcessor = this.filteredProcessors[0].key;
      }
    },

    async runSelected() {
      const banner = document.getElementById('js-error-banner');
      const result = document.getElementById('js-result-banner');
      banner.style.display = 'none';
      result.style.display = 'none';
      this.running = true;
      try {
        const res = await fetch('/api/processors/' + this.selectedProcessor + '/run', { method: 'POST' });
        const data = await res.json();
        if (!res.ok) {
          banner.textContent = data.detail || 'Ошибка выполнения';
          banner.style.display = 'block';
        } else {
          result.textContent = data.message;
          result.style.display = 'block';
        }
      } catch (err) {
        banner.textContent = String(err);
        banner.style.display = 'block';
      } finally {
        this.running = false;
      }
    },
  };
}
</script>
{% endblock %}
"""


def render_processors_page(jinja_env) -> str:
    processors_json = json.dumps([
        {"key": p.key, "tableKey": p.table_key, "label": p.label}
        for p in PROCESSORS
    ], ensure_ascii=False)
    template = jinja_env.from_string(_PAGE_TEMPLATE_SOURCE)
    return template.render(processors_json=processors_json)
