# app/documents_chain/page.py
# ============================================================
# HTML-страница /documents-chain/{request_id} — "Показать
# подчинённые документы": полноэкранный журнал, в который можно
# попасть ТОЛЬКО с экрана заявок, выделив ровно одну заявку и нажав
# соответствующую кнопку (child_document_actions[1] у request_table,
# см. tables.py) — своей ссылки в верхнем меню (NAV_MENU) страница
# сознательно не имеет.
#
# Данные приходят одним запросом с GET /api/documents-chain/{id}
# (app/documents_chain/api.py) — уже сгруппированные по типу
# документа (заявка первой, дальше calculation, дальше будущие
# specification/invoice, когда появятся в реестре). Разметка/JS
# ничего не знает про конкретные типы документов — колонки, relations,
# подпись группы приходят из ответа API (config.fields/relations того
# же вида, что использует движок), поэтому добавление нового уровня
# цепочки не требует правок этого файла.
#
# Действия над выделенными документами — ПЛОСКОЕ выделение across
# всех групп сразу (selectedIds — Set строк "{tableKey}:{id}", не
# просто id, т.к. id пересекаются между разными таблицами). Копирование
# и пометка на удаление группируют выделенные id по typeKey и
# вызывают уже существующие per-table эндпоинты движка
# (POST /api/{key} для копии, POST /api/{key}/bulk-mark-delete) —
# без дублирования этой логики здесь.
# ============================================================

import json


_PAGE_TEMPLATE_SOURCE = r"""
{% extends "base.html" %}
{% block content %}
<div x-data="documentsChainPage()" x-init="init()">

  <div class="topbar">
    <div class="topbar-title">
      <h1>Цепочка документов</h1>
      <span class="count" x-show="!loading" x-text="totalCount + ' документов'"></span>
    </div>
    <div style="display:flex; gap:8px;">
      <button type="button" class="btn" @click="goBack()">← К заявкам</button>
    </div>
  </div>

  <div id="js-error-banner" style="display:none; margin:14px 20px 0; background:#f3e6e3; border:1px solid #9c3b2e; color:#9c3b2e; padding:10px 16px; border-radius:6px; font-family:monospace; font-size:12px; white-space:pre-wrap;"></div>

  <div class="selection-bar" x-show="selectedKeys.length > 0" x-cloak>
    <span x-text="selectedKeys.length + ' выделено'"></span>
    <button type="button" class="btn" :disabled="selectedKeys.length !== 1" @click="copySelected()">Копировать</button>
    <button type="button" class="btn" :disabled="!canBulkDelete" @click="bulkMarkDelete(true)">Пометить на удаление</button>
    <button type="button" class="btn" :disabled="!canBulkDelete" @click="bulkMarkDelete(false)">Снять пометку</button>
    <button type="button" class="selection-clear" @click="selectedKeys = []">Снять выделение</button>
  </div>

  <div style="padding: 0 20px 40px;">
    <template x-if="loading">
      <div style="padding:40px 0; text-align:center; color:var(--ink-soft);">Загрузка…</div>
    </template>

    <template x-for="group in groups" :key="group.key">
      <div style="margin-top:22px;">
        <h2 style="font-size:13px; font-weight:600; text-transform:uppercase; letter-spacing:0.04em; color:var(--ink-soft); margin:0 0 8px;">
          <span x-text="group.title"></span>
          <span style="font-weight:400; text-transform:none; letter-spacing:0;" x-text="'(' + group.items.length + ')'"></span>
        </h2>

        <template x-if="group.items.length === 0">
          <div style="padding:14px; background:var(--panel); border:1px solid var(--line); border-radius:8px; color:var(--ink-soft); font-size:13px;">
            Нет документов этого типа.
          </div>
        </template>

        <table x-show="group.items.length > 0">
          <thead>
            <tr>
              <th style="width:36px;"></th>
              <template x-for="f in group.fields" :key="f.name">
                <th x-text="f.label"></th>
              </template>
            </tr>
          </thead>
          <tbody>
            <template x-for="item in group.items" :key="group.key + ':' + item.id">
              <tr @click="toggleSelect(group.key, item.id)">
                <td @click.stop>
                  <input type="checkbox" :checked="isSelected(group.key, item.id)" @change="toggleSelect(group.key, item.id)">
                </td>
                <template x-for="f in group.fields" :key="f.name">
                  <td x-text="displayValue(group, item, f)"></td>
                </template>
              </tr>
            </template>
          </tbody>
        </table>
      </div>
    </template>
  </div>

</div>
<script>
function documentsChainPage() {
  return {
    requestId: null,
    groups: [],
    relationOptions: {},   // { target_table: { id: displayName } } — подтягивается лениво
                            // по мере встречи новых relations в группах (см. loadRelationOptions).
    selectedKeys: [],       // строки "{tableKey}:{id}" — плоское выделение across групп
    loading: true,

    get totalCount() {
      return this.groups.reduce((sum, g) => sum + g.items.length, 0);
    },

    get canBulkDelete() {
      // Пометка на удаление активна, только если ВСЕ выделенные
      // документы принадлежат soft-delete таблицам (та же защита,
      // что и в обычном журнале движка, где кнопка вообще не
      // рисуется для не-soft таблиц — здесь типы разные внутри
      // одного выделения, поэтому проверяем явно).
      if (this.selectedKeys.length === 0) return false;
      return this.selectedKeys.every(k => {
        const [tableKey] = k.split(':');
        const g = this.groups.find(g => g.key === tableKey);
        return g && g.delete_mode === 'soft';
      });
    },

    init() {
      const params = new URLSearchParams(window.location.search);
      this.requestId = params.get('request_id');
      if (!this.requestId) {
        this.showError('Не передан идентификатор заявки.');
        this.loading = false;
        return;
      }
      this.load();
    },

    async load() {
      this.loading = true;
      this.hideError();
      try {
        const res = await fetch('/api/documents-chain/' + encodeURIComponent(this.requestId));
        if (!res.ok) {
          this.showError('Не удалось загрузить цепочку документов. ' + await this.extractErrorMessage(res));
          this.groups = [];
          return;
        }
        const data = await res.json();
        this.groups = data.groups;
        this.selectedKeys = [];
        await this.loadRelationOptions();
      } catch (err) {
        this.showError(String(err));
      } finally {
        this.loading = false;
      }
    },

    async loadRelationOptions() {
      // Собираем набор ("target_table") из relations всех групп и
      // подгружаем каждую целиком (page_size большой — тот же приём,
      // что и обычные страницы движка для relationOptions), чтобы
      // резолвить id -> читаемое имя (клиент/бренд) в displayValue().
      const targets = new Set();
      for (const g of this.groups) {
        for (const r of (g.relations || [])) targets.add(r.target_table);
      }
      await Promise.all([...targets].map(async (table) => {
        if (this.relationOptions[table]) return;
        try {
          const res = await fetch('/api/' + table + '?page_size=1000');
          if (!res.ok) return;
          const data = await res.json();
          const map = {};
          for (const item of (data.items || [])) map[item.id] = item;
          this.relationOptions[table] = map;
        } catch (e) { /* не критично — поле просто покажет ID вместо имени */ }
      }));
    },

    displayValue(group, item, field) {
      const rel = (group.relations || []).find(r => r.field === field.name);
      if (rel) {
        const rawId = item[field.name];
        if (rawId === null || rawId === undefined || rawId === '') return '—';
        const options = this.relationOptions[rel.target_table];
        const match = options && options[rawId];
        return match ? match[rel.display_field] : ('#' + rawId);
      }
      const value = item[field.name];
      if (value === null || value === undefined || value === '') return '—';
      if (field.widget === 'select' && field.name === 'is_deleted') return value ? 'Помечена' : '';
      return value;
    },

    selectionKey(tableKey, id) {
      return tableKey + ':' + id;
    },

    isSelected(tableKey, id) {
      return this.selectedKeys.includes(this.selectionKey(tableKey, id));
    },

    toggleSelect(tableKey, id) {
      const key = this.selectionKey(tableKey, id);
      const idx = this.selectedKeys.indexOf(key);
      if (idx === -1) this.selectedKeys.push(key);
      else this.selectedKeys.splice(idx, 1);
    },

    groupedSelection() {
      // { tableKey: [id, id, ...] } — группировка плоского
      // selectedKeys по типу документа, нужна и для копирования (там
      // требуется ровно 1 выделенный элемент любого типа), и для
      // групповой пометки на удаление (может быть несколько типов
      // сразу — по одному bulk-запросу на каждый встретившийся тип).
      const byTable = {};
      for (const key of this.selectedKeys) {
        const [tableKey, idStr] = key.split(':');
        (byTable[tableKey] = byTable[tableKey] || []).push(Number(idStr));
      }
      return byTable;
    },

    async copySelected() {
      // Копирование — только при ровно одном выделенном документе
      // (тот же принцип, что и copySelected() в обычных плоских
      // таблицах движка, см. engine/page.py). Реализовано так же:
      // забираем данные уже загруженной строки, убираем id/is_deleted,
      // POST на обычный /api/{key} этого типа документа — сервер
      // сам присвоит новый номер по своему счётчику префикса.
      if (this.selectedKeys.length !== 1) return;
      const [tableKey, idStr] = this.selectedKeys[0].split(':');
      const id = Number(idStr);
      const group = this.groups.find(g => g.key === tableKey);
      const item = group && group.items.find(i => i.id === id);
      if (!item) return;
      this.hideError();
      try {
        const payload = { ...item };
        delete payload.id;
        delete payload.is_deleted;
        const res = await fetch('/api/' + tableKey, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
        });
        if (!res.ok) {
          this.showError('Не удалось скопировать. ' + await this.extractErrorMessage(res));
          return;
        }
        await this.load();
      } catch (err) {
        this.showError(String(err));
      }
    },

    async bulkMarkDelete(value) {
      if (!this.canBulkDelete) return;
      this.hideError();
      const byTable = this.groupedSelection();
      try {
        for (const [tableKey, ids] of Object.entries(byTable)) {
          const res = await fetch('/api/' + tableKey + '/bulk-mark-delete', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ ids, value }),
          });
          if (!res.ok) {
            this.showError('Не удалось обновить пометку. ' + await this.extractErrorMessage(res));
            return;
          }
        }
        this.selectedKeys = [];
        await this.load();
      } catch (err) {
        this.showError(String(err));
      }
    },

    goBack() {
      window.location.href = '/request-v2';
    },

    async extractErrorMessage(res) {
      try {
        const data = await res.json();
        return data.detail || res.statusText;
      } catch (e) {
        return res.statusText;
      }
    },

    showError(message) {
      const banner = document.getElementById('js-error-banner');
      if (!banner) return;
      banner.textContent = message;
      banner.style.display = 'block';
    },

    hideError() {
      const banner = document.getElementById('js-error-banner');
      if (!banner) return;
      banner.style.display = 'none';
    },
  };
}
</script>
{% endblock %}
"""


def render_documents_chain_page(jinja_env) -> str:
    template = jinja_env.from_string(_PAGE_TEMPLATE_SOURCE)
    return template.render()
