// scripts/lib/read-archive.js
// ============================================================
// Читає список файлів усередині ZIP-архіву ДО розпакування.
// Потрібно для Telegram-звіту "що взагалі змінювалось" — навіть
// якщо білд впаде і нічого не потрапить у реальний репозиторій,
// ми все одно знаємо, що було в архіві. Також цей список
// використовується lastmod.js, щоб знати, яким файлам примусово
// проставити сьогоднішню дату.
// ============================================================

import { execSync } from 'node:child_process';

/**
 * Повертає список файлів усередині ZIP-архіву (без папок).
 * Якщо unzip з якоїсь причини впаде (пошкоджений архів, немає прав
 * тощо) — кидає зрозумілу помилку, а не мовчки валить весь процес
 * з незрозумілим стеком.
 * @param {string} zipPath - шлях до ZIP-файлу
 * @returns {string[]} - список шляхів файлів усередині архіву
 */
export function readArchiveFileList(zipPath) {
  let raw;
  try {
    raw = execSync(`unzip -l "${zipPath}"`, { encoding: 'utf-8', stdio: ['ignore', 'pipe', 'pipe'] });
  } catch (err) {
    throw new Error(`Не вдалося прочитати список файлів архіву (${zipPath}): ${err.message}`);
  }

  const lines = raw.split('\n');
  const files = [];

  for (const line of lines) {
    // Формат рядка unzip -l:
    //   довжина   дата   час   шлях
    // Останнє поле — шлях. Пропускаємо заголовки/підвал/папки.
    const match = line.match(/^\s*\d+\s+[\d-]+\s+[\d:]+\s+(.+)$/);
    if (!match) continue;

    const filePath = match[1].trim();
    if (!filePath) continue;
    if (filePath.endsWith('/')) continue; // це папка, не файл

    files.push(filePath);
  }

  return files;
}
