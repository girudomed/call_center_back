###fine_tune_model.py
import re
import mysql.connector
import aiomysql # используем для асинхронного подключения к базе
import asyncio  # асинхронная библиотека для запуска
import json
import openai
from openai import File
import subprocess
import logging
from datetime import datetime
import os
from dotenv import load_dotenv
import time
import pexpect

# Загрузка переменных окружения
load_dotenv()

# Настраиваем логирование
logging.basicConfig(
    filename="fine_tuning_log.log",
    level=logging.DEBUG,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

logger = logging.getLogger()

# Проверка наличия API-ключа
api_key = os.getenv('OPENAI_API_KEY')
if not api_key:
    logger.error("API ключ OpenAI отсутствует. Установите его в .env файле.")
    raise ValueError("API ключ OpenAI отсутствует.")
else:
    openai.api_key = api_key

# Подключение к базе данных с использованием aiomysql
async def get_db_connection():
    logger.info("5% - Подключение к базе данных.")
    try:
        connection = await aiomysql.connect(
            host=os.getenv('DB_HOST', 'localhost'),
            user=os.getenv('DB_USER', 'your_user'),
            password=os.getenv('DB_PASSWORD', 'your_password'),
            db=os.getenv('DB_NAME', 'your_database'),
            port=int(os.getenv('DB_PORT', 3306))
        )
        logger.info("10% - Подключение к базе данных выполнено успешно.")
        return connection
    except aiomysql.Error as e:
        logger.error(f"Ошибка подключения к базе данных: {e}")
        return None

# Функция для получения данных чек-листа и критериев
async def fetch_training_data(connection):
    logger.info("Извлечение данных для fine-tuning...")
    try:
        async with connection.cursor(aiomysql.DictCursor) as cursor:
            await cursor.execute("SELECT prompt, completion FROM training_model")
            data = await cursor.fetchall()
            if not data:
                logger.warning("Нет данных для fine-tuning в таблице training_model.")
            return data
    except Exception as e:
        logger.error(f"Ошибка при получении данных: {e}")
        return []
    
# Функция для экспорта данных в JSONL
async def export_data_to_jsonl(file_path):
    logger.info("15% - Начало экспорта данных в JSONL.")
    connection = await get_db_connection()
    if not connection:
        logger.error("Не удалось подключиться к базе данных. Экспорт данных прерван.")
        return
    try:
        
        # Запрос данных из таблицы training_model
        async with connection.cursor(aiomysql.DictCursor) as cursor:
            logger.info("20% - Запрос данных из таблицы training_model.")
            await cursor.execute("SELECT prompt, completion FROM training_model")
            rows = await cursor.fetchall()
        
        # Экспорт данных в JSONL формат
        with open(file_path, "w", encoding="utf-8") as f:
            for i, row in enumerate(rows):
                # Подготовка данных и прогресс на каждый 10%
                if len(rows) > 10 and i % (len(rows) // 10) == 0:
                    progress = 25 + (i // (len(rows) // 10)) * 5
                    logger.info(f"{progress}% - Экспортировано {i+1} из {len(rows)} записей.")
                # Подготовка prompt: убираем лишние точки, добавляем единственную точку в конце
                prompt = row.get('prompt', '').strip()
                if not prompt:
                    logger.error("Пустой 'prompt' обнаружен, запись пропущена.")
                    continue

                completion = row.get('completion', '').strip()
                if not completion:
                    logger.error("Пустой 'completion' обнаружен, запись пропущена.")
                    continue

                # Очистка данных и добавление формата
                prompt = prompt if prompt.endswith(".") else prompt + "."
                completion = " " + re.sub(r"^\d+\.\s*[^:]*:\s*", "", completion) + "\n\n###"
                
                # Запись в JSONL
                data = {"prompt": prompt, "completion": completion}
                f.write(json.dumps(data, ensure_ascii=False) + "\n")
        
        logger.info(f"50% - Данные успешно экспортированы в файл: {file_path}")
    except Exception as e:
        logger.error(f"Ошибка при записи данных в JSONL файл: {e}")
    finally:
        await connection.ensure_closed()
    
# Функция для проверки файла JSONL с помощью openai tools
def check_data_file(file_path):
    logger.info("55% - Начало проверки формата JSONL файла.")
    if not os.path.exists(file_path):
        logger.error(f"Файл {file_path} не найден.")
        return False
    try:
        logger.info("Проверка формата данных начата...")

        # Используем pexpect для автоматической отправки ответа 'Y'
        command = f"openai tools fine_tunes.prepare_data -f {file_path}"
        child = pexpect.spawn(command, timeout=60)  # Увеличен timeout до 60 секунд

        # Ожидаем запрос подтверждения и отправляем 'Y'
        try:
            child.expect(["[Y/n]", pexpect.EOF])
            child.sendline("Y")
        except pexpect.exceptions.TIMEOUT:
            logger.error("Время ожидания подтверждения истекло.")
            return False

        # Захватываем вывод для проверки успешности выполнения
        child.expect(pexpect.EOF)
        output = child.before
        if output:
            output = output.decode("utf-8")
        else:
            logger.error("Ошибка: данные для вывода отсутствуют.")
            return False

        if "Validation successful" in output:
            logger.info("60% - Проверка завершена: файл готов для загрузки.")
            return True
        else:
            logger.error(f"Ошибка валидации JSONL файла: {output}")
            return False

    except Exception as e:
        logger.error(f"Ошибка при выполнении проверки файла: {e}")
        return False
    
def upload_data_file(file_path):
    logger.info("65% - Начало загрузки файла JSONL на сервер OpenAI.")
    try:
        with open(file_path, "rb") as f:
            response = File.create(
                file=f,
                purpose="fine-tune"
            )
        training_file_id = response["id"]
        logger.info(f"70% - Файл успешно загружен на OpenAI с ID: {training_file_id}")
        return training_file_id
    except openai.OpenAIError as e:
        logger.error(f"Ошибка загрузки файла: {e}")
    except Exception as e:
        logger.error(f"Неожиданная ошибка загрузки файла JSONL: {e}")


# Функция для получения имени модели после завершения fine-tuning
def get_fine_tuned_model_name(fine_tune_job_id):
    try:
        # Извлекаем информацию о fine-tuning задаче
        fine_tune_job = openai.FineTune.retrieve(id=fine_tune_job_id)
        # Если задача завершена, получаем имя модели
        if fine_tune_job['status'] == 'succeeded':
            model_name = fine_tune_job['fine_tuned_model']
            logger.info(f"Fine-tuning завершен. Имя модели: {model_name}")
            return model_name
        else:
            logger.error("Fine-tuning завершен с ошибкой.")
            return None
    except openai.OpenAIError as e:
        logger.error(f"Ошибка при получении имени fine-tuned модели: {e}")
        return None
    except Exception as e:
        logger.error(f"Неожиданная ошибка при получении имени модели: {e}")
        return None

# Обновленная функция отслеживания состояния fine-tuning задачи
def track_fine_tune_status(fine_tune_job_id):
    logger.info("85% - Начало отслеживания состояния fine-tuning задачи.")
    try:
        while True:
            fine_tune_job = openai.FineTune.retrieve(id=fine_tune_job_id)
            status = fine_tune_job['status']
            logger.info(f"Текущий статус задачи fine-tuning: {status}")
            if status == "pending":
                logger.info("90% - Ожидание начала fine-tuning.")
            elif status == "running":
                logger.info("95% - Fine-tuning в процессе.")
            elif status == "succeeded":
                logger.info("100% - Fine-tuning завершен успешно.")
                # Получаем и логируем имя модели после успешного завершения
                model_name = get_fine_tuned_model_name(fine_tune_job_id)
                if model_name:
                    logger.info(f"Fine-tuned модель успешно создана с именем: {model_name}")
                break
            elif status == "failed":
                logger.info("Fine-tuning завершен с ошибкой.")
                break
            time.sleep(15)
    except openai.OpenAIError as e:
        logger.error(f"Ошибка отслеживания статуса: {e}")
    except Exception as e:
        logger.error(f"Неожиданная ошибка при отслеживании статуса: {e}")
        
# Основной асинхронный процесс
def main():
    file_path = "check_list_data.jsonl"
    
    asyncio.run(export_data_to_jsonl(file_path))
    
    if not check_data_file(file_path):
        logger.error("Проверка не пройдена, процесс fine-tuning остановлен.")
        return
    
    training_file_id = upload_data_file(file_path)
    if not training_file_id:
        logger.error("Загрузка файла завершилась ошибкой, процесс fine-tuning остановлен.")
        return
    
    fine_tune_job_id = create_fine_tune_model(training_file_id)
    if fine_tune_job_id:
        track_fine_tune_status(fine_tune_job_id)
    logger.info("100% - Fine-tuning процесс завершен.")

if __name__ == "__main__":
    logger.info("Старт процесса fine-tuning.")
    main()
    logger.info("Завершение процесса fine-tuning.")
