# Используем lightweight базовый образ Python
FROM python:3.11.8-slim

# Устанавливаем системные зависимости
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Устанавливаем рабочую директорию
WORKDIR /app

# Копируем и устанавливаем системные зависимости поэтапно для кэширования
COPY requirements.txt ./requirements.txt

# Устанавливаем зависимости с использованием кэша
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Копируем весь проект
COPY . .

# Добавляем переменные окружения
ENV PYTHONUNBUFFERED=1

# Открываем порт
EXPOSE 5000

# Запускаем приложение
CMD ["python", "main.py"]