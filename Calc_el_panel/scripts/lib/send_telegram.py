# scripts/lib/send_telegram.py
# ============================================================
# Отправляет сообщение в Telegram напрямую через Bot API.
#
# Токен и chat_id берутся из переменных окружения TELEGRAM_TOKEN
# и TELEGRAM_TO (те же GitHub Secrets, что и в оригинальной схеме).
#
# send_telegram_message НИКОГДА не бросает исключение наружу —
# сбой сети/Telegram API только логируется в консоль. Так голый
# запрос без try/except не оборвёт весь process_update.py раньше
# шага удаления ZIP.
# ============================================================

import json
import os
import urllib.request
import urllib.error

TELEGRAM_API = "https://api.telegram.org"


def send_telegram_message(text: str) -> None:
    token = os.environ.get("TELEGRAM_TOKEN")
    chat_id = os.environ.get("TELEGRAM_TO")

    if not token or not chat_id:
        print("⚠️  TELEGRAM_TOKEN или TELEGRAM_TO не заданы — сообщение не отправлено")
        print("Текст, который должен был быть отправлен:\n" + text)
        return

    url = f"{TELEGRAM_API}/bot{token}/sendMessage"
    payload = json.dumps({
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown",
    }).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status >= 300:
                print(f"⚠️  Ошибка отправки в Telegram: {resp.status} {resp.read().decode('utf-8', 'ignore')}")
    except urllib.error.URLError as err:
        print(f"⚠️  Не удалось обратиться к Telegram API: {err}")


def build_info_message(repo_name: str, time_str: str, zip_name: str, files: list[str]) -> str:
    """Первое сообщение: информация об архиве + список файлов."""
    lines = [
        f"📦 **Репозиторий:** `{repo_name}`",
        f"⏱️ **Время:** *{time_str}*",
        f"📄 **Файл архива:** `{zip_name}`",
        "",
        "⚡ **Обновление проекта — тестовая сборка запущена**",
        "",
        "🔄 **Файлы обновлены:**",
    ]

    if files:
        lines.extend(f"`{f}`" for f in files)
    else:
        lines.append("----")

    return "\n".join(lines)


def build_result_message(success: bool, repo_name: str, time_str: str, error_summary: str | None) -> str:
    """Второе сообщение: результат тестовой сборки."""
    lines = []

    if success:
        lines.append("🟢 **Обновление успешно (приложение поднялось, /health отвечает)**")
    else:
        lines.append("🔴 **Ошибка сборки (/health не ответил или упал pip install)**")

    lines.append(f"📦 **Репозиторий:** `{repo_name}`")
    lines.append(f"⏱️ **Время:** *{time_str}*")

    if not success and error_summary:
        lines.append("")
        lines.append("```")
        lines.append(error_summary[:2000])  # защита от превышения лимита Telegram
        lines.append("```")

    return "\n".join(lines)
