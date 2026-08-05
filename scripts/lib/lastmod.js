// scripts/lib/lastmod.js
// ============================================================
// Рахує дату останнього оновлення для кожної сторінки/картки
// портфоліо і повертає готову карту для запису у
// src/data/lastmod-map.json.
//
// ЧОМУ ЦЕ ОКРЕМИЙ МОДУЛЬ, А НЕ ПРЯМИЙ git log УСЕРЕДИНІ
// sitemap.xml.ts:
// Cloudflare Pages клонує репозиторій НЕ повною історією —
// лише один коміт (shallow fetch конкретного SHA). "git log"
// усередині sitemap.xml.ts на Cloudflare нічого не знайде і
// мовчки впаде на фолбек-дату для ВСІХ сторінок.
// Тому дати рахуються тут, у GitHub Actions (де є повна історія,
// fetch-depth: 0), і зберігаються у готовий JSON-файл. Cloudflare
// при своєму білді просто ЧИТАЄ цей файл — git там більше не
// потрібен.
//
// ЧОМУ РАХУЄМО ДО STAGING, А НЕ ПІСЛЯ КОМІТУ:
// На момент запуску process-update.js архів ще НЕ закомічений
// у git — коміт відбувається пізніше, окремим кроком workflow.
// Якщо рахувати git log ПІСЛЯ перенесення файлів у реальний
// репозиторій, але ДО коміту — для зміненого (вже існуючого)
// файлу git log поверне ПОПЕРЕДНЮ дату, а не сьогоднішню, бо
// сьогоднішнього коміту ще не існує.
//
// РІШЕННЯ: рахуємо git log по РЕАЛЬНОМУ репозиторію (REPO_ROOT,
// з повною історією) ДО будь-яких змін від архіву — це дає
// коректні дати для всіх файлів, які архів не чіпає. Потім
// примусово підставляємо СЬОГОДНІШНЮ дату для файлів, які Є
// у списку архіву (readArchiveFileList) — вони так чи інакше
// оновлюються прямо зараз, дата відома наперед, git тут не
// потрібен і не може дати правильну відповідь.
//
// Результат: src/data/lastmod-map.json
// Формат: { "src/pages/kontakty.astro": "2026-07-23", ... }
// ============================================================

import fs from 'node:fs';
import path from 'node:path';
import { execSync } from 'node:child_process';

// Директорії, які скануємо на .astro сторінки
const PAGE_DIRS = [
  'src/pages',                              // верхній рівень
  'src/pages/posluhy-ta-produktsiia',       // продукція UA
  'src/pages/ru',                           // всі RU-сторінки (рекурсивно нижче)
];

// Директорії з контентом Content Collections
const CONTENT_DIRS = [
  'src/content/vykonani-roboty',
];

// Рекурсивно збирає всі файли з розширенням .astro або .md у директорії
function collectFiles(repoRoot, dir, ext) {
  const fullDir = path.join(repoRoot, dir);
  if (!fs.existsSync(fullDir)) return [];

  const results = [];
  const entries = fs.readdirSync(fullDir, { withFileTypes: true });

  for (const entry of entries) {
    const entryRelPath = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      results.push(...collectFiles(repoRoot, entryRelPath, ext));
    } else if (entry.isFile() && entry.name.endsWith(ext)) {
      // Пропускаємо динамічні роути на кшталт [slug].astro —
      // для них немає сенсу рахувати lastmod окремо
      if (entry.name.startsWith('[')) continue;
      results.push(entryRelPath.split(path.sep).join('/')); // нормалізація слешів
    }
  }
  return results;
}

// Повертає дату останнього коміту для файлу, або null якщо історії немає
function getGitDate(repoRoot, relFilePath) {
  try {
    const out = execSync(`git log -1 --format=%cs -- "${relFilePath}"`, {
      cwd: repoRoot,
      encoding: 'utf-8',
      stdio: ['ignore', 'pipe', 'pipe'],
    }).trim();
    return out || null;
  } catch {
    return null;
  }
}

/**
 * Рахує карту дат по РЕАЛЬНОМУ репозиторію (до staging, до будь-яких
 * змін від архіву). Для файлів без git-історії (нові файли, яких
 * git log ще не бачив) — підставляє сьогоднішню дату як фолбек.
 * @param {string} repoRoot - корінь реального репозиторію (з .git)
 * @returns {{ map: Record<string,string>, gitFailures: number }}
 */
export function computeLastmodMap(repoRoot) {
  const fallbackDate = new Date().toISOString().split('T')[0];
  const allFiles = [];

  for (const dir of PAGE_DIRS) {
    allFiles.push(...collectFiles(repoRoot, dir, '.astro'));
  }
  for (const dir of CONTENT_DIRS) {
    allFiles.push(...collectFiles(repoRoot, dir, '.md'));
  }

  const uniqueFiles = Array.from(new Set(allFiles));

  const map = {};
  let gitFailures = 0;

  for (const file of uniqueFiles) {
    const date = getGitDate(repoRoot, file);
    map[file] = date || fallbackDate;
    if (!date) gitFailures++;
  }

  return { map, gitFailures };
}

/**
 * Оновлює карту дат: для кожного шляху зі списку файлів архіву
 * (якщо це .astro чи .md сторінка, що потрапляє під схему карти)
 * примусово ставить СЬОГОДНІШНЮ дату — незалежно від того, що
 * показав git log (адже ці файли якраз зараз і оновлюються).
 * @param {Record<string,string>} map
 * @param {string[]} archiveFiles - список шляхів з readArchiveFileList
 * @returns {{ map: Record<string,string>, updatedCount: number }}
 */
export function applyArchiveDatesOverride(map, archiveFiles) {
  const today = new Date().toISOString().split('T')[0];
  const updated = { ...map };
  let updatedCount = 0;

  for (const relPath of archiveFiles) {
    const normalized = relPath.split(path.sep).join('/');
    const isTracked = normalized.endsWith('.astro') || normalized.endsWith('.md');
    if (!isTracked) continue;
    // Пропускаємо динамічні роути — вони так чи інакше не входять у map
    const baseName = path.basename(normalized);
    if (baseName.startsWith('[')) continue;

    updated[normalized] = today;
    updatedCount++;
  }

  return { map: updated, updatedCount };
}

/**
 * Записує готову карту дат у файл усередині staging-директорії
 * (звідки вона потім поїде у реальний репозиторій разом з рештою
 * файлів через promoteToRepo — одним набором змін, без окремого
 * коміту).
 * @param {string} stagingDir
 * @param {Record<string,string>} map
 */
export function writeLastmodMap(stagingDir, map) {
  const outputPath = path.join(stagingDir, 'src/data/lastmod-map.json');
  fs.mkdirSync(path.dirname(outputPath), { recursive: true });
  fs.writeFileSync(outputPath, JSON.stringify(map, null, 2) + '\n', 'utf-8');
  return outputPath;
}
