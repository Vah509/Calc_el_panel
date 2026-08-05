// scripts/lib/send-telegram.js
// ============================================================
// Надсилає повідомлення у Telegram напряму через Bot API
// (без appleboy/telegram-action — простіше викликати з
// того самого Node-скрипта, де вже є весь контекст).
//
// Токен та chat_id беруться зі змінних оточення
// TELEGRAM_TOKEN та TELEGRAM_TO (ті самі GitHub Secrets,
// що вже використовуються у workflow).
//
// sendTelegramMessage НІКОЛИ не кидає виняток назовні — збій
// мережі/Telegram API лише логується у консоль. Раніше голий
// fetch без try/catch міг обірвати весь process-update.js ще
// до кроку видалення ZIP.
// ============================================================

const TELEGRAM_API = 'https://api.telegram.org';

/**
 * Надсилає одне текстове повідомлення у Telegram.
 * Помилки мережі/API не кидаються далі — лише логуються.
 * @param {string} text - текст повідомлення (Markdown)
 */
export async function sendTelegramMessage(text) {
  const token = process.env.TELEGRAM_TOKEN;
  const chatId = process.env.TELEGRAM_TO;

  if (!token || !chatId) {
    console.error('⚠️  TELEGRAM_TOKEN або TELEGRAM_TO не задані — повідомлення не надіслано');
    console.error('Текст, який мав бути надісланий:\n' + text);
    return;
  }

  const url = `${TELEGRAM_API}/bot${token}/sendMessage`;

  try {
    const res = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        chat_id: chatId,
        text,
        parse_mode: 'Markdown',
      }),
    });

    if (!res.ok) {
      const body = await res.text();
      console.error(`⚠️  Помилка надсилання у Telegram: ${res.status} ${body}`);
    }
  } catch (err) {
    console.error(`⚠️  Не вдалося звернутись до Telegram API: ${err.message}`);
  }
}

/**
 * Формує ПЕРШЕ повідомлення: інформація про архів + список файлів
 * + звіт по фото.
 * @param {{ repoName: string, time: string, zipName: string, files: string[], photoLines: string[] }} data
 */
export function buildInfoMessage({ repoName, time, zipName, files, photoLines }) {
  const lines = [];

  // Виключаємо фото зі загального списку — вони вже перелічені
  // нижче, у розділі "Перевірка фото", з розмірами та статусом.
  const codeFiles = files.filter(
    (f) => !f.toLowerCase().endsWith('.jpg') && !f.toLowerCase().endsWith('.jpeg'),
  );

  lines.push(`📦 **Репозиторій:** \`${repoName}\``);
  lines.push(`⏱️ **Час:** *${time}*`);
  lines.push(`📄 **Файл архіву:** \`${zipName}\``);
  lines.push('');
  lines.push('⚡ **Оновлення проекту та перевірка фото**');
  lines.push('');

  lines.push('🔄 **Файли оновлені:**');
  if (codeFiles.length > 0) {
    for (const f of codeFiles) {
      lines.push(`\`${f}\``);
    }
  } else {
    lines.push('----');
  }
  lines.push('');

  if (photoLines.length > 0) {
    lines.push('📸 **Перевірка фото:**');
    for (const line of photoLines) {
      lines.push(line);
    }
  } else {
    lines.push('📸 Нових зображень в архіві немає.');
  }

  return lines.join('\n');
}

/**
 * Формує ДРУГЕ повідомлення: результат тестової збірки.
 * Статус — ПЕРШИМ рядком (щоб у прев'ю сповіщення одразу було
 * видно зелений/червоний індикатор).
 * @param {{ success: boolean, repoName: string, time: string, errorSummary?: string | null }} data
 */
export function buildResultMessage({ success, repoName, time, errorSummary }) {
  const lines = [];

  if (success) {
    lines.push('🟢 **Оновлення успішне (Astro Build розгорнуто)**');
  } else {
    lines.push('🔴 **Помилка збірки (Astro Build не пройшов)**');
  }

  lines.push(`📦 **Репозиторій:** \`${repoName}\``);
  lines.push(`⏱️ **Час:** *${time}*`);

  if (!success && errorSummary) {
    lines.push('');
    lines.push('```');
    lines.push(errorSummary.slice(0, 2000)); // захист від перевищення ліміту Telegram
    lines.push('```');
  }

  return lines.join('\n');
}
