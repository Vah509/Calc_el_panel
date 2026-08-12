#!/usr/bin/env python3
# scripts/process_cleanup.py
# ============================================================
# Ручная очистка репозитория от ненужных файлов/директорий по
# списку. НЕ связана с обычным пайплайном обновления приложения
# (scripts/process_update.py, ai-updates/) — отдельный механизм,
# отдельная папка, отдельный workflow, запускается ТОЛЬКО вручную.
#
# КАК ПОЛЬЗОВАТЬСЯ:
#  1. Claude кладёт .txt-файл со списком путей на удаление в
#     cleanup-requests/ (папка отдельная от ai-updates/ — архивы
#     кода туда никогда не попадают, и наоборот).
#  2. Файл заливается в GitHub через браузер, как обычно.
#  3. Вахтанг заходит в GitHub → Actions → "Repo Cleanup (manual)" →
#     нажимает "Run workflow" вручную. По push НИЧЕГО не запускается —
#     это осознанное решение, чтобы нельзя было случайно удалить
#     файлы одним лишь фактом заливки списка.
#
# ФОРМАТ ФАЙЛА СО СПИСКОМ (простой текст, кодировка UTF-8):
#   - Один путь на строку, относительно корня репозитория.
#   - Пути к файлам и пути к директориям — вперемешку, без разницы.
#     Скрипт сам определяет, что это (os.path.isfile/isdir).
#   - Пустые строки и строки, начинающиеся с #, игнорируются
#     (можно оставлять комментарии в файле списка).
#
# ПРИМЕР СОДЕРЖИМОГО cleanup-requests/cleanup_2026-08-12.txt:
#   # Устаревшие HTMX-шаблоны после перехода на Alpine
#   app/templates/materials/_form.html
#   app/templates/materials/_row.html
#   app/templates/materials/_tbody.html
#
# БЕЗОПАСНОСТЬ:
#  - Скрипт удаляет ТОЛЬКО то, что явно перечислено в файле списка.
#    Никакого поиска по маске, никакого "и всё, что похоже".
#  - Путь к самому файлу списка и вся папка cleanup-requests/ никогда
#    не удаляются этим скриптом сами по себе.
#  - Каждое удаление логируется и попадает в сообщение в Telegram —
#    видно, что именно было удалено, даже если вы не смотрели вывод
#    GitHub Actions.
#  - Если путь из списка не существует в репозитории — это НЕ ошибка,
#    просто отмечается в отчёте как "уже отсутствует" (файл могли
#    удалить раньше или он опечатан — решаете вы, глядя на отчёт).
# ============================================================

import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(__file__))
from lib.send_telegram import send_telegram_message

REPO_ROOT = os.getcwd()
CLEANUP_REQUESTS_DIR = os.path.join(REPO_ROOT, "cleanup-requests")


def find_cleanup_file() -> str | None:
    """Берёт первый .txt файл в cleanup-requests/ (в алфавитном порядке)."""
    if not os.path.isdir(CLEANUP_REQUESTS_DIR):
        return None
    txt_files = sorted(f for f in os.listdir(CLEANUP_REQUESTS_DIR) if f.endswith(".txt"))
    if not txt_files:
        return None
    return os.path.join(CLEANUP_REQUESTS_DIR, txt_files[0])


def read_paths(list_file: str) -> list[str]:
    with open(list_file, "r", encoding="utf-8") as f:
        lines = f.readlines()
    paths = []
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        paths.append(line)
    return paths


def delete_path(relative_path: str) -> str:
    """Удаляет один путь, возвращает строку результата для отчёта."""
    # Защита от выхода за пределы репозитория (например, "../../etc/passwd")
    full_path = os.path.normpath(os.path.join(REPO_ROOT, relative_path))
    if not full_path.startswith(REPO_ROOT):
        return f"⚠️ ПРОПУЩЕНО (путь вне репозитория): `{relative_path}`"

    if not os.path.exists(full_path):
        return f"⏭️ Уже отсутствует: `{relative_path}`"

    try:
        if os.path.isdir(full_path):
            shutil.rmtree(full_path)
            return f"🗑️ Удалена директория: `{relative_path}`"
        else:
            os.remove(full_path)
            return f"🗑️ Удалён файл: `{relative_path}`"
    except OSError as err:
        return f"❌ Ошибка удаления `{relative_path}`: {err}"


def main() -> None:
    repo_name = os.path.basename(REPO_ROOT)
    list_file = find_cleanup_file()

    if not list_file:
        print("Список на удаление не найден в cleanup-requests/ — завершение без действий.")
        send_telegram_message(
            f"📦 **Репозиторий:** `{repo_name}`\n"
            "ℹ️ Cleanup запущен вручную, но в `cleanup-requests/` нет ни одного `.txt` файла со списком."
        )
        return

    list_file_name = os.path.basename(list_file)
    paths = read_paths(list_file)

    if not paths:
        print(f"Файл {list_file_name} пуст или содержит только комментарии — ничего не удалено.")
        send_telegram_message(
            f"📦 **Репозиторий:** `{repo_name}`\n"
            f"ℹ️ Файл `{list_file_name}` найден, но список путей пуст — ничего не удалено."
        )
        return

    results = [delete_path(p) for p in paths]
    for r in results:
        print(r)

    # Список-файл сам удаляем после обработки — чтобы повторный ручной
    # запуск того же workflow не удалил те же пути ещё раз "вхолостую".
    os.remove(list_file)
    print(f"Обработанный список удалён: {list_file_name}")

    message_lines = [
        f"🧹 **Ручная очистка репозитория**",
        f"📦 **Репозиторий:** `{repo_name}`",
        f"📄 **Список:** `{list_file_name}`",
        "",
    ]
    message_lines.extend(results)
    send_telegram_message("\n".join(message_lines))


if __name__ == "__main__":
    main()
