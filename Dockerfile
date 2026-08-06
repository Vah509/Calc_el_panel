FROM python:3.11-slim

# Системные библиотеки:
# - для WeasyPrint (генерация PDF): pango, cairo, gdk-pixbuf и т.д.
# - для Tesseract OCR (чтение PDF-счетов поставщиков): tesseract-ocr
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libcairo2 \
    libgdk-pixbuf-2.0-0 \
    libffi-dev \
    shared-mime-info \
    fonts-liberation \
    tesseract-ocr \
    tesseract-ocr-rus \
    tesseract-ocr-ukr \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Railway передаёт порт через переменную окружения PORT
# Точка входа: app/main.py -> модуль app.main, объект app
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
