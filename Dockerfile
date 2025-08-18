# Используем официальный образ Python 3.9 в slim-версии
FROM python:3.9-slim

# Устанавливаем рабочую директорию внутри контейнера
WORKDIR /app

# Устанавливаем системные зависимости:
# ghostscript - для конвертации PDF в TIFF
# poppler-utils - для надежного анализа PDF (подсчет страниц и т.д.)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ghostscript \
    && rm -rf /var/lib/apt/lists/*

# Копируем файл с Python-зависимостями
COPY requirements.txt .

# Устанавливаем Python-зависимости
RUN pip install --no-cache-dir -r requirements.txt

# Копируем все остальные файлы проекта (bot.py, pdf_to_tiff.py и т.д.)
COPY . .

# Указываем команду для запуска бота при старте контейнера
CMD ["python", "bot.py"]
