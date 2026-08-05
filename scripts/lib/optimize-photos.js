// scripts/lib/optimize-photos.js
// ============================================================
// Перевіряє та за потреби оптимізує фото (.jpg/.jpeg) усередині
// staging-директорії. Логіка та сама, що була раніше:
//   - ширина <= 1200px  → вважається вже оптимізованим, лишаємо як є
//   - ширина > 1200px   → стискаємо до 1200px, якість 85
//
// Повертає масив звітів по кожному файлу — для Telegram-повідомлення.
// ============================================================

import fs from 'node:fs';
import path from 'node:path';
import sharp from 'sharp';

const MAX_WIDTH = 1200;
const JPEG_QUALITY = 85;

function formatSize(bytes) {
  const kb = Math.round(bytes / 1024);
  return kb >= 1024 ? `${(kb / 1024).toFixed(1)} MB` : `${kb} KB`;
}

/**
 * @param {string} stagingDir - корінь staging-директорії
 * @param {string[]} archiveFiles - список шляхів файлів з архіву (з read-archive.js)
 * @returns {Promise<{lines: string[], hasPhotos: boolean}>}
 */
export async function optimizePhotos(stagingDir, archiveFiles) {
  const photoFiles = archiveFiles.filter(
    (f) => f.toLowerCase().endsWith('.jpg') || f.toLowerCase().endsWith('.jpeg'),
  );

  if (photoFiles.length === 0) {
    return { lines: [], hasPhotos: false };
  }

  const lines = [];

  for (const relPath of photoFiles) {
    const fullPath = path.join(stagingDir, relPath);

    if (!fs.existsSync(fullPath)) {
      lines.push(`\`${relPath}\` — файл не знайдено після розпакування`);
      continue;
    }

    try {
      const origStat = fs.statSync(fullPath);
      const origSizeStr = formatSize(origStat.size);

      const image = sharp(fullPath);
      const meta = await image.metadata();

      if (meta.width && meta.width <= MAX_WIDTH) {
        lines.push(`\`${relPath}\` — ${origSizeStr} — ОК`);
      } else {
        const buffer = await image
          .resize({ width: MAX_WIDTH, withoutEnlargement: true })
          .jpeg({ quality: JPEG_QUALITY })
          .toBuffer();
        fs.writeFileSync(fullPath, buffer);

        const newSizeStr = formatSize(buffer.length);
        lines.push(`\`${relPath}\` — ${origSizeStr} → ${newSizeStr} — ОПТ`);
      }
    } catch (err) {
      lines.push(`\`${relPath}\` — помилка аналізу (${err.message})`);
    }
  }

  return { lines, hasPhotos: true };
}
