#!/usr/bin/env python3
# scripts/process_update.py
# ============================================================
# Главный сценарий обработки обновления проекта.
# Вызывается одной строкой из .github/workflows/unzip-and-update.yml:
#   python scripts/process_update.py
#
# ЧТО ДЕЛАЕТ, ПО ШАГАМ:
#  1. Находит ZIP-архив в ai-updates/
#  2. Читает список файлов внутри архива (для отчёта в Telegram)
#  3. Создаёт staging-копию репозитория (БЕЗ .git)
#  4. Распаковывает архив поверх staging
#  5. Отправляет ПЕРВОЕ сообщение в Telegram (какие файлы пришли)
#  6. Пробует тестовую сборку: pip install + запуск uvicorn на
#     тестовой SQLite + проверка GET /health — внутри staging
#  7. Если сборка ОК:
#       - переносит staging → реальный репозиторий
#     Если сборка НЕ ОК:
#       - ничего не переносит, реальный репозиторий остаётся как был
#  8. Отправляет ВТОРОЕ сообщение в Telegram (результат сборки)
#  9. Удаляет оригинальный ZIP из ai-updates/ (В ЛЮБОМ СЛУЧАЕ — и при
#     успехе, и при провале, и даже если какой-то из шагов выше
#     бросит неожиданное исключение — это гарантируется структурой
#     try/finally ниже, а не просто порядком строк кода)
# 10. Убирает staging-директорию (так же гарантированно, в finally)
#
# Далее (ВНЕ этого скрипта, отдельным шагом в workflow, только если
# сборка была успешной) — сразу идёт git add/commit/push.
#
# Скрипт завершается с кодом выхода 0 при успехе, 1 при провале
# сборки ИЛИ при любой неожиданной ошибке — чтобы workflow мог через
# `if: success()` корректно разветвить дальнейшие шаги (коммит) без
# необходимости парсить вывод.
# ============================================================

import os
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

# Позволяет запускать скрипт и как `python scripts/process_update.py`,
# и как модуль — импорты внутри lib/ остаются относительными к пакету.
sys.path.insert(0, os.path.dirname(__file__))

from lib.read_archive import read_archive_file_list
from lib.staging import create_staging, apply_archive_to_staging, promote_to_repo, cleanup_staging
from lib.test_build import test_build
from lib.send_telegram import send_telegram_message, build_info_message, build_result_message

REPO_ROOT = os.getcwd()
AI_UPDATES_DIR = os.path.join(REPO_ROOT, "ai-updates")
TIMEZONE = "Europe/Bratislava"  # тот же часовой пояс, что был в исходной схеме


def get_current_time() -> str:
    return datetime.now(ZoneInfo(TIMEZONE)).strftime("%H:%M:%S")


def find_zip_file() -> str | None:
    if not os.path.isdir(AI_UPDATES_DIR):
        return None
    zip_files = [f for f in os.listdir(AI_UPDATES_DIR) if f.endswith(".zip")]
    if not zip_files:
        return None
    return os.path.join(AI_UPDATES_DIR, zip_files[0])


def main() -> None:
    repo_name = os.path.basename(REPO_ROOT)
    zip_path = find_zip_file()

    if not zip_path:
        print("Архив не найден в ai-updates/ — завершение без действий.")
        return

    zip_name = os.path.basename(zip_path)
    time_at_start = get_current_time()

    build_succeeded = False

    # --- Всё, что может упасть, обёрнуто в try/finally: ZIP и staging
    # должны быть убраны ВСЕГДА, независимо от того, на каком шаге
    # произошёл сбой (сеть, распаковка, сборка, перенос файлов).
    try:
        # --- Шаг 2: список файлов из архива ---
        archive_files = read_archive_file_list(zip_path)

        # --- Шаг 3-4: staging + применение архива ---
        print("Создание staging-копии репозитория...")
        staging_dir = create_staging(REPO_ROOT)
        print("Распаковка архива поверх staging...")
        apply_archive_to_staging(staging_dir, zip_path)

        # --- Шаг 5: первое сообщение в Telegram ---
        info_message = build_info_message(repo_name, time_at_start, zip_name, archive_files)
        send_telegram_message(info_message)

        # --- Шаг 6: тестовая сборка ---
        print("Тестовая сборка (pip install + uvicorn + /health) в staging...")
        build_result = test_build(staging_dir)
        build_succeeded = build_result["success"]

        time_at_end = get_current_time()

        # --- Шаг 7: перенос в реальный репозиторий, ТОЛЬКО если сборка ОК ---
        if build_result["success"]:
            print("Сборка успешна — перенос файлов в реальный репозиторий...")
            promote_to_repo(staging_dir, REPO_ROOT)
        else:
            print("Сборка провалилась — реальный репозиторий НЕ изменён.")

        # --- Шаг 8: второе сообщение в Telegram ---
        result_message = build_result_message(
            success=build_result["success"],
            repo_name=repo_name,
            time_str=time_at_end,
            error_summary=build_result["error_summary"],
        )
        send_telegram_message(result_message)

    except Exception as err:
        # Неожиданная ошибка на любом из шагов выше (сеть, диск, права
        # доступа и т.п.) — логируем, а удаление ZIP и staging всё
        # равно произойдёт ниже, в finally.
        print(f"Неожиданная ошибка при обработке обновления: {err}")
        build_succeeded = False

    finally:
        # --- Шаг 9: удаление ZIP из ai-updates/ (ВСЕГДА) ---
        print("Удаление оригинального архива из ai-updates/...")
        try:
            if os.path.exists(zip_path):
                os.remove(zip_path)
        except OSError as err:
            print(f"Не удалось удалить ZIP-архив: {err}")

        # --- Шаг 10: уборка staging (ВСЕГДА) ---
        try:
            cleanup_staging()
        except OSError as err:
            print(f"Не удалось убрать staging-директорию: {err}")

    if not build_succeeded:
        # Ненулевой код выхода — чтобы workflow мог через `if: success()`
        # пропустить коммит/пуш, если сборка не прошла или произошёл сбой.
        sys.exit(1)


if __name__ == "__main__":
    try:
        main()
    except Exception as err:
        # Последний рубеж защиты — если даже сам main() с его
        # внутренним try/finally что-то не учёл. ZIP к этому моменту
        # уже должен быть удалён внутри finally выше.
        print(f"Критическая ошибка в process_update.py: {err}")
        sys.exit(1)
