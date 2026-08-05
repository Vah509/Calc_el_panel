// scripts/lib/test-build.js
// ============================================================
// Запускає тестову збірку Astro (npm run build) усередині
// staging-директорії. Повертає результат — успіх/провал і
// текст помилки (якщо є), для Telegram-повідомлення.
//
// npm install тут НЕ виконується — очікується, що node_modules
// вже присутній (або переданий разом зі staging, або встановлений
// окремим кроком workflow ДО виклику цього модуля).
// ============================================================

import { execSync } from 'node:child_process';

/**
 * @param {string} stagingDir
 * @returns {{ success: boolean, errorSummary: string | null }}
 */
export function testBuild(stagingDir) {
  try {
    execSync('npm run build', {
      cwd: stagingDir,
      encoding: 'utf-8',
      stdio: ['ignore', 'pipe', 'pipe'],
    });
    return { success: true, errorSummary: null };
  } catch (err) {
    // err.stderr / err.stdout містять вивід команди, що впала
    const output = `${err.stdout || ''}\n${err.stderr || ''}`.trim();

    // Беремо останні кілька рядків — зазвичай там суть помилки,
    // а не весь довгий стек-трейс Vite/Rollup
    const lines = output.split('\n').filter((l) => l.trim());
    const tail = lines.slice(-8).join('\n');

    return {
      success: false,
      errorSummary: tail || 'Невідома помилка збірки (порожній вивід)',
    };
  }
}
