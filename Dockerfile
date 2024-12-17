# Используем amd64-образ Python для совместимости с Ubuntu
FROM --platform=linux/amd64 python:3.11.8-slim

# Устанавливаем рабочую директорию
WORKDIR /app

# Копируем файл зависимостей
COPY requirements.txt .

# Обновляем pip и устанавливаем зависимости
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Копируем исходный код проекта
COPY . .

# Открываем порт для приложения
EXPOSE 5000

# Команда для запуска приложения
CMD ["python", "main.py"]
