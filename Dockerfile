FROM python:3.10-slim

# Установка системных зависимостей
RUN apt-get update \
    && apt-get install -y --no-install-recommends ghostscript gcc libmagic1 \
    && rm -rf /var/lib/apt/lists/*

# Копирование зависимостей и исходников
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

# Запуск бот-приложения
CMD ["python", "bot.py"]
