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

# Разделяем зависимости на этапы для максимального кэширования
RUN pip install --no-cache-dir --upgrade pip
RUN pip install --no-cache-dir aiohttp aiosignal aiomysql Flask Flask-SQLAlchemy
RUN pip install --no-cache-dir google-api-python-client openai pandas
RUN pip install --no-cache-dir scikit-learn spacy tqdm typer
RUN pip install --no-cache-dir rich weasel langcodes thinc cryptography
RUN pip install --no-cache-dir python-dotenv APScheduler

# Копируем весь проект
COPY . .

# Добавляем переменные окружения
ENV PYTHONUNBUFFERED=1

# Открываем порт
EXPOSE 5000

# Запускаем приложение
CMD ["python", "main.py"]