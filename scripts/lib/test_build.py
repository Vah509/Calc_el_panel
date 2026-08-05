# scripts/lib/test_build.py
# ============================================================
# Аналог "npm run build" из Astro-версии, но для FastAPI-проекта
# компиляции в статику нет — вместо неё "сборка считается успешной",
# если:
#   1. pip install зависимостей проходит чисто
#   2. uvicorn поднимается на тестовой SQLite-базе
#   3. GET /health отвечает 200 в разумное время
#
# Никаких внешних сервисов (Postgres и т.п.) не поднимается —
# раннер полностью самодостаточен, тестовая БД — файл SQLite
# внутри staging, который просто исчезает вместе с staging.
# ============================================================

import os
import signal
import subprocess
import sys
import time
import urllib.request
import urllib.error

HEALTH_URL = "http://127.0.0.1:8000/health"
STARTUP_TIMEOUT_SECONDS = 15
POLL_INTERVAL_SECONDS = 0.5


def _pip_install(staging_dir: str) -> tuple[bool, str | None]:
    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", "--quiet", "-r", "requirements.txt"],
        cwd=staging_dir,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        output = f"{result.stdout}\n{result.stderr}".strip()
        return False, _tail(output)
    return True, None


def _wait_for_health(proc: subprocess.Popen) -> tuple[bool, str | None]:
    deadline = time.time() + STARTUP_TIMEOUT_SECONDS
    last_error = None

    while time.time() < deadline:
        if proc.poll() is not None:
            # процесс уже умер сам — сборка точно не удалась
            out, err = proc.communicate()
            return False, _tail(f"{out}\n{err}".strip())

        try:
            with urllib.request.urlopen(HEALTH_URL, timeout=2) as resp:
                if resp.status == 200:
                    return True, None
                last_error = f"/health вернул статус {resp.status}"
        except urllib.error.URLError as err:
            last_error = str(err)

        time.sleep(POLL_INTERVAL_SECONDS)

    return False, f"/health не ответил за {STARTUP_TIMEOUT_SECONDS}с. Последняя ошибка: {last_error}"


def _tail(text: str, lines: int = 8) -> str:
    parts = [line for line in text.split("\n") if line.strip()]
    return "\n".join(parts[-lines:]) or "Пустой вывод"


def test_build(staging_dir: str) -> dict:
    """
    Возвращает {"success": bool, "error_summary": str | None}.

    Порядок:
      1. pip install -r requirements.txt
      2. запуск uvicorn в фоне с тестовой SQLite базой (test.db внутри staging)
      3. опрос /health до успеха или таймаута
      4. гарантированное завершение процесса uvicorn в любом случае
    """
    ok, err = _pip_install(staging_dir)
    if not ok:
        return {"success": False, "error_summary": f"pip install провалился:\n{err}"}

    env = os.environ.copy()
    env["DATABASE_URL"] = f"sqlite:///{os.path.join(staging_dir, 'test.db')}"

    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000"],
        cwd=staging_dir,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    try:
        success, error_summary = _wait_for_health(proc)
        return {"success": success, "error_summary": error_summary}
    finally:
        # Гарантированно гасим процесс, даже если проверка упала
        # с неожиданным исключением выше.
        if proc.poll() is None:
            proc.send_signal(signal.SIGTERM)
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
