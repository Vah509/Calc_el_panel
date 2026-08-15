# scripts/lib/staging.py
# ============================================================
# Управляет "песочницей" (staging) — временной копией репозитория,
# куда применяется ZIP-архив и где происходит тестовая сборка.
# Реальный репозиторий НЕ меняется, пока сборка не подтвердит успех.
#
# create_staging()          — копирует текущее состояние репозитория в staging
# apply_archive_to_staging()— распаковывает ZIP поверх staging
# promote_to_repo()         — переносит staging обратно в реальный репозиторий
#                              (вызывается ТОЛЬКО после успешной сборки)
# cleanup_staging()         — убирает временную директорию
#
# Все вызовы обёрнуты в try/except и бросают понятные ошибки — чтобы
# process_update.py мог их перехватить в своём try/finally и
# ГАРАНТИРОВАННО убрать ZIP и staging, даже если что-то из этого упадёт.
# ============================================================

import os
import shutil
import subprocess
import zipfile

STAGING_DIR = "/tmp/em-staging"

# Что не переносим при promote — служебные/генерируемые директории.
# Аналог исключения dist/ и node_modules/ в оригинальной Astro-версии.
EXCLUDE_ON_PROMOTE = {".venv", "__pycache__", ".pytest_cache", "local.db", "test.db"}


def create_staging(repo_root: str) -> str:
    """
    Копирует текущий репозиторий (без .git — он не нужен в staging,
    тестовая сборка его не использует) во временную директорию.
    """
    if os.path.exists(STAGING_DIR):
        shutil.rmtree(STAGING_DIR, ignore_errors=True)
    os.makedirs(STAGING_DIR, exist_ok=True)

    try:
        subprocess.run(
            ["cp", "-a", f"{repo_root}/.", f"{STAGING_DIR}/"],
            check=True,
        )
    except subprocess.CalledProcessError as err:
        raise RuntimeError(f"Не удалось создать staging-копию репозитория: {err}") from err

    staging_git_dir = os.path.join(STAGING_DIR, ".git")
    if os.path.exists(staging_git_dir):
        shutil.rmtree(staging_git_dir, ignore_errors=True)

    return STAGING_DIR


def apply_archive_to_staging(staging_dir: str, zip_path: str) -> None:
    """Распаковывает ZIP-архив поверх staging-директории."""
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(staging_dir)
    except Exception as err:
        raise RuntimeError(f"Не удалось распаковать архив в staging: {err}") from err


def promote_to_repo(staging_dir: str, repo_root: str) -> None:
    """
    Переносит содержимое staging обратно в реальный репозиторий.
    Вызывать ТОЛЬКО после успешной тестовой сборки.

    Служебные директории (.venv, __pycache__, тестовые *.db) временно
    отодвигаются в сторону перед копированием и не возвращаются —
    они не должны попасть в реальный репозиторий.
    """
    aside_paths = []
    for name in EXCLUDE_ON_PROMOTE:
        src = os.path.join(staging_dir, name)
        if os.path.exists(src):
            dst = os.path.join("/tmp", f"em-staging-aside-{name.replace('/', '_')}")
            if os.path.exists(dst):
                shutil.rmtree(dst, ignore_errors=True) if os.path.isdir(dst) else os.remove(dst)
            shutil.move(src, dst)
            aside_paths.append((src, dst))

    try:
        subprocess.run(
            ["cp", "-a", f"{staging_dir}/.", f"{repo_root}/"],
            check=True,
        )
    except subprocess.CalledProcessError as err:
        raise RuntimeError(f"Не удалось перенести staging в реальный репозиторий: {err}") from err
    finally:
        # Отложенные директории НЕ возвращаем обратно в staging —
        # cleanup_staging() всё равно снесёт всю папку целиком следом.
        for _src, dst in aside_paths:
            if os.path.isdir(dst):
                shutil.rmtree(dst, ignore_errors=True)
            elif os.path.exists(dst):
                os.remove(dst)


def cleanup_staging() -> None:
    """Убирает временную staging-директорию."""
    if os.path.exists(STAGING_DIR):
        shutil.rmtree(STAGING_DIR, ignore_errors=True)
