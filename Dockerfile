# Используем базовый образ Python
FROM python:3.11.8-slim

# Устанавливаем рабочую директорию
WORKDIR /app

# Устанавливаем зависимости по частям для снижения нагрузки
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip

# Разделяем requirements.txt на несколько частей
RUN pip install --no-cache-dir aiohttp aiosignal aiomysql Flask Flask-SQLAlchemy
RUN pip install --no-cache-dir google-api-python-client openai pandas
RUN pip install --no-cache-dir scikit-learn spacy tqdm typer

# Копируем исходный код проекта
COPY . .

# Открываем порт для приложения
EXPOSE 5000

# Запуск приложения
CMD ["python", "main.py"]
