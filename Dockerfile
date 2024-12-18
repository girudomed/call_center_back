# Используем базовый образ Python
FROM python:3.11.8-slim

# Устанавливаем системные зависимости (для сборки пакетов)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential && \
    rm -rf /var/lib/apt/lists/*

# Устанавливаем рабочую директорию
WORKDIR /app

# Копируем только requirements.txt (для кэширования зависимостей)
COPY requirements.txt .

# Устанавливаем Python-зависимости с использованием кэша
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Копируем весь исходный код проекта
COPY . .

# Открываем порт для приложения
EXPOSE 5000

# Запуск приложения
CMD ["python", "main.py"]
