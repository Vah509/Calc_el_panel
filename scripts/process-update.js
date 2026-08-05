// scripts/process-update.js
// ============================================================
// Головний сценарій обробки оновлення сайту.
// Викликається одним рядком з .github/workflows/unzip-and-update.yml:
//   node scripts/process-update.js
//
// ЩО РОБИТЬ, ПО КРОКАХ:
//  1. Знаходить ZIP-архів у ai-updates/
//  2. Читає список файлів усередині архіву (для звіту та для дат)
//  3. Рахує карту дат оновлення (lastmod-map) ПО РЕАЛЬНОМУ репозиторію,
//     ДО будь-яких змін від архіву — git log тут ще бачить справжню,
//     незайману історію. Потім примусово підставляє СЬОГОДНІШНЮ дату
//     для файлів, які є у списку архіву (бо для них git log через
//     відсутність ще не зробленого коміту дав би СТАРУ дату, а не
//     сьогоднішню — детально у scripts/lib/lastmod.js).
//  4. Створює staging-копію репозиторію (БЕЗ .git)
//  5. Розпаковує архів поверх staging
//  6. Перевіряє/оптимізує фото — усередині staging
//  7. Надсилає ПЕРШЕ повідомлення в Telegram (файли + фото)
//  8. Пробує зібрати Astro (npm run build) — усередині staging
//  9. Якщо білд ОК:
//       - записує вже готову карту дат у staging (src/data/lastmod-map.json),
//         щоб вона поїхала в реальний репозиторій РАЗОМ з рештою файлів
//         архіву, одним набором змін, без окремого коміту
//       - переносить staging → реальний репозиторій
//     Якщо білд НЕ ОК:
//       - нічого не переносить, реальний репозиторій лишається як був
// 10. Надсилає ДРУГЕ повідомлення в Telegram (статус збірки)
// 11. Видаляє оригінальний ZIP з ai-updates/ (В БУДЬ-ЯКОМУ ВИПАДКУ —
//     і при успіху, і при провалі, і навіть якщо якийсь із кроків
//     вище кине несподіваний виняток — це гарантується структурою
//     try/finally нижче, а не просто порядком рядків коду)
// 12. Прибирає staging-директорію (так само гарантовано, у finally)
//
// Далі (ПОЗА цим скриптом, окремим кроком у workflow, лише якщо
// білд був успішним) — одразу йде git add/commit/push. Окремого
// кроку "Generate lastmod map" у workflow більше НЕМАЄ — карта дат
// вважається тут і їде разом з іншими файлами.
//
// Скрипт завершується з кодом виходу 0 при успіху, 1 при провалі
// білду АБО при будь-якій несподіваній помилці — щоб workflow міг
// через `if: success()` коректно розгалужити подальші кроки (коміт)
// без потреби парсити вивід.
// ============================================================

import fs from 'node:fs';
import path from 'node:path';

import { readArchiveFileList } from './lib/read-archive.js';
import { optimizePhotos } from './lib/optimize-photos.js';
import { createStaging, applyArchiveToStaging, promoteToRepo, cleanupStaging } from './lib/staging.js';
import { testBuild } from './lib/test-build.js';
import { sendTelegramMessage, buildInfoMessage, buildResultMessage } from './lib/send-telegram.js';
import { computeLastmodMap, applyArchiveDatesOverride, writeLastmodMap } from './lib/lastmod.js';

const REPO_ROOT = process.cwd();
const AI_UPDATES_DIR = path.join(REPO_ROOT, 'ai-updates');

function getCurrentTime() {
  // Той самий часовий пояс, що й раніше — Europe/Bratislava
  return new Date().toLocaleTimeString('uk-UA', {
    timeZone: 'Europe/Bratislava',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });
}

function findZipFile() {
  if (!fs.existsSync(AI_UPDATES_DIR)) return null;
  const zipFiles = fs.readdirSync(AI_UPDATES_DIR).filter((f) => f.endsWith('.zip'));
  if (zipFiles.length === 0) return null;
  return path.join(AI_UPDATES_DIR, zipFiles[0]);
}

async function main() {
  const repoName = path.basename(REPO_ROOT);
  const zipPath = findZipFile();

  if (!zipPath) {
    console.log('Архів не знайдено в ai-updates/ — завершення без дій.');
    return;
  }

  const zipName = path.basename(zipPath);
  const timeAtStart = getCurrentTime();

  // Прапорець фінального стану — використовується лише для коду виходу
  let buildSucceeded = false;

  // --- Усе, що може впасти, огорнуте в try/finally: ZIP і staging
  // мають бути прибрані ЗАВЖДИ, незалежно від того, на якому кроці
  // стався збій (мережа, розпакування, білд, перенесення файлів).
  try {
    // --- Крок 2: список файлів з архіву ---
    const archiveFiles = readArchiveFileList(zipPath);

    // --- Крок 3: карта дат — рахуємо ПО РЕАЛЬНОМУ репозиторію,
    // ДО будь-яких змін від staging/архіву ---
    console.log('Розрахунок дат останнього оновлення сторінок...');
    const { map: baseLastmodMap, gitFailures } = computeLastmodMap(REPO_ROOT);
    const { map: lastmodMap, updatedCount } = applyArchiveDatesOverride(baseLastmodMap, archiveFiles);
    console.log(
      `Карта дат: ${Object.keys(lastmodMap).length} файлів, ${updatedCount} оновлено на сьогодні, ${gitFailures} без git-історії (фолбек).`,
    );

    // --- Крок 4-5: staging + застосування архіву ---
    console.log('Створення staging-копії репозиторію...');
    const stagingDir = createStaging(REPO_ROOT);
    console.log('Розпакування архіву поверх staging...');
    applyArchiveToStaging(stagingDir, zipPath);

    // --- Крок 6: перевірка/оптимізація фото ---
    console.log('Перевірка фото...');
    const photoReport = await optimizePhotos(stagingDir, archiveFiles);

    // --- Крок 7: перше повідомлення в Telegram ---
    const infoMessage = buildInfoMessage({
      repoName,
      time: timeAtStart,
      zipName,
      files: archiveFiles,
      photoLines: photoReport.lines,
    });
    await sendTelegramMessage(infoMessage);

    // --- Крок 8: тестова збірка ---
    console.log('Тестова збірка Astro у staging...');
    const buildResult = testBuild(stagingDir);
    buildSucceeded = buildResult.success;

    const timeAtEnd = getCurrentTime();

    // --- Крок 9: запис карти дат + перенос у реальний репозиторій,
    // ЛИШЕ якщо білд ОК ---
    if (buildResult.success) {
      console.log('Білд успішний — запис карти дат у staging...');
      writeLastmodMap(stagingDir, lastmodMap);
      console.log('Перенесення файлів у реальний репозиторій...');
      promoteToRepo(stagingDir, REPO_ROOT);
    } else {
      console.log('Білд провалився — реальний репозиторій НЕ змінено, дати НЕ записано.');
    }

    // --- Крок 10: друге повідомлення в Telegram ---
    const resultMessage = buildResultMessage({
      success: buildResult.success,
      repoName,
      time: timeAtEnd,
      errorSummary: buildResult.errorSummary,
    });
    await sendTelegramMessage(resultMessage);
  } catch (err) {
    // Несподівана помилка на будь-якому з кроків вище (мережа, диск,
    // права доступу тощо) — логуємо, а видалення ZIP і staging усе
    // одно відбудеться нижче, у finally.
    console.error('Неочікувана помилка під час обробки оновлення:', err);
    buildSucceeded = false;
  } finally {
    // --- Крок 11: видалення ZIP з ai-updates/ (ЗАВЖДИ) ---
    console.log('Видалення оригінального архіву з ai-updates/...');
    try {
      fs.rmSync(zipPath, { force: true });
    } catch (err) {
      console.error('Не вдалося видалити ZIP-архів:', err.message);
    }

    // --- Крок 12: прибирання staging (ЗАВЖДИ) ---
    try {
      cleanupStaging();
    } catch (err) {
      console.error('Не вдалося прибрати staging-директорію:', err.message);
    }
  }

  if (!buildSucceeded) {
    // Ненульовий код виходу — щоб workflow міг через `if: success()`
    // пропустити коміт/пуш, якщо білд не пройшов або стався збій.
    process.exit(1);
  }
}

main().catch((err) => {
  // Останній рубіж захисту — якщо навіть сам main() з його
  // внутрішнім try/finally щось не врахував. ZIP до цього моменту
  // вже мав би бути видалений усередині finally вище.
  console.error('Критична помилка у process-update.js:', err);
  process.exit(1);
});
