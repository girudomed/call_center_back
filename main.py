#main.py
import asyncio
import logging  # noqa: F401
import aiohttp
import openai
from datetime import datetime  # noqa: F401
import aiomysql
from async_db_connection import create_async_connection, execute_async_query  # noqa: F401
from db_setup import create_tables, get_checklists_and_criteria
from gpt_config import analyze_call_with_gpt, save_call_score
from logging_config import setup_logging, check_and_clear_logs
from result_logging import log_analysis_result
from quart import Quart, jsonify, send_from_directory
import datetime as dt
import threading
import json
import os

# Создание экземпляра приложения Quart
app = Quart(__name__)
# Создайте экземпляр Lock
lock = asyncio.Lock()

# Параметры
CONFIG = {
    'LIMIT': 5,
    'RETRIES': 3,
    'START_DATE': '2024-10-01 00:00:00',
    'BATCH_SIZE': 30,
    'ENABLE_LOGGING': True,
    'DB_HOST': os.getenv('DB_HOST'),
    'DB_PORT': int(os.getenv('DB_PORT', 3306)),
    'DB_USER': os.getenv('DB_USER'),
    'DB_PASSWORD': os.getenv('DB_PASSWORD'),
    'DB_NAME': os.getenv('DB_NAME')
}

# Настройка логирования
logger = setup_logging(CONFIG['ENABLE_LOGGING'])

# Преобразование START_DATE в таймстемп для запросов
START_DATE_TIMESTAMP = int(dt.datetime.strptime(CONFIG['START_DATE'], '%Y-%m-%d %H:%M:%S').timestamp())

def datetime_to_timestamp(dt_object):
    """Преобразование объекта datetime в таймстемп."""
    return int(dt_object.timestamp())

def timestamp_to_datetime(timestamp):
    """Преобразование таймстемпа в объект datetime."""
    return dt.datetime.fromtimestamp(timestamp)

async def get_db_connection():
    """Получение асинхронного соединения с базой данных MySQL."""
    try:
        conn = await aiomysql.connect(
            host=CONFIG['DB_HOST'],
            port=CONFIG['DB_PORT'],
            user=CONFIG['DB_USER'],
            password=CONFIG['DB_PASSWORD'],
            db=CONFIG['DB_NAME'],
            autocommit=True,
            cursorclass=aiomysql.DictCursor  # Используем DictCursor
        )
        return conn
    except Exception as e:
        logger.exception(f"Ошибка при подключении к базе данных: {e}")
        return None

async def execute_async_query(connection, query, params=None):  # noqa: F811
    """Выполнение асинхронного SQL-запроса."""
    async with connection.cursor(aiomysql.DictCursor) as cursor:
        await cursor.execute(query, params)
        if cursor.description:
            result = await cursor.fetchall()
            return result
        return None

async def process_calls(calls, connection, checklists, lock):
    async with lock:
        """Обработка списка звонков."""
    tasks = []
    for call in calls:
        call_id = call['history_id']
        called_info = call['called_info']
        caller_info = call['caller_info']
        talk_duration = str(call['talk_duration'])
        transcript = call['transcript']
        context_start_time = call['context_start_time']
        call_date = timestamp_to_datetime(context_start_time).strftime('%Y-%m-%d %H:%M:%S') if context_start_time else None
        if transcript:
            tasks.append(analyze_and_save_call(
                connection, transcript, checklists, call_id, call_date, called_info, caller_info, talk_duration, lock))
    try:
        await asyncio.gather(*tasks)
    except Exception as e:
        logger.exception(f"Ошибка при обработке звонков: {e}")

async def analyze_and_save_call(connection, transcript, checklists, call_id, call_date, called_info, caller_info, talk_duration, lock):
    """Анализ и сохранение результатов звонка."""
    if isinstance(checklists, str):
        checklists = json.loads(checklists)  # Преобразование из JSON-строки в список
    elif isinstance(checklists, tuple):
        checklists = list(checklists)  # Преобразование кортежа в список

    # Цикл для повторных попыток анализа
    for attempt in range(CONFIG['RETRIES']):
        try:
            # Выполняем анализ звонка с помощью GPT
            score, result, call_category, category_number, checklist_result = await analyze_call_with_gpt(transcript, checklists)
            
            if result is None:
                logger.error(f"Ошибка при анализе звонка {call_id}, пропуск сохранения результатов")
                return

            logger.info(f"Анализ звонка {call_id}: результат={result}, категория={call_category}, чек-лист={checklist_result}")
            checklist_number = category_number
            checklist_category = checklist_result

            # Блокировка для безопасного сохранения результатов в базе данных
            async with lock:
                await save_call_score(
                    connection, call_id, score, call_category, call_date, called_info, caller_info,
                    talk_duration, transcript, result, category_number, checklist_number, checklist_category
                )
            logger.info(f"Звонок {call_id} сохранен с результатом: {result}")

            log_analysis_result(call_id, result)
            break  # Успешное завершение, выходим из цикла
        except openai.RateLimitError as e:
            logger.warning(f"Превышен лимит запросов для звонка {call_id}: {e}")
            if attempt < CONFIG['RETRIES'] - 1:
                await asyncio.sleep(2 ** attempt)  # Экспоненциальная задержка между попытками
                continue
            else:
                logger.error(f"Превышен лимит попыток для звонка {call_id}")
                break
        except aiohttp.ClientError as e:
            logger.error(f"Сетевая ошибка для звонка {call_id}: {e}")
            break
        except Exception as e:
            logger.exception(f"Ошибка при анализе звонка {call_id}: {e}")
            break

async def get_history_ids_from_call_history(connection):
    """Получение идентификаторов истории звонков."""
    query = "SELECT history_id FROM call_history WHERE context_start_time >= %s"
    return await execute_async_query(connection, query, (START_DATE_TIMESTAMP,))

async def get_history_ids_from_call_scores(connection):
    """Получение идентификаторов истории звонков."""
    query = "SELECT history_id FROM call_history WHERE context_start_time >= %s"
    return await execute_async_query(connection, query, (START_DATE_TIMESTAMP,))

async def get_call_data_by_history_ids(connection, history_ids):
    """Получение данных о звонках по идентификаторам."""
    placeholders = ','.join(['%s'] * len(history_ids))  # Используем %s для плейсхолдеров
    query = f"""
    SELECT history_id, called_info, caller_info, talk_duration, transcript, context_start_time
    FROM call_history
    WHERE history_id IN ({placeholders}) AND context_start_time >= %s
    """
    return await execute_async_query(connection, query, tuple(history_ids) + (START_DATE_TIMESTAMP,))

async def process_missing_calls(missing_ids, connection, checklists, lock):
    """Обработка недостающих звонков."""
    while missing_ids:
        batch_ids = missing_ids[:CONFIG['BATCH_SIZE']]
        missing_ids = missing_ids[CONFIG['BATCH_SIZE']:]

        call_data = await get_call_data_by_history_ids(connection, batch_ids)
        if call_data is None:
            logger.error("Не удалось получить данные о звонках для следующих history_ids: %s", batch_ids)
            continue
        
        tasks = []
        for call in call_data:
            call_id = call['history_id']
            called_info = call['called_info']
            caller_info = call['caller_info']
            talk_duration = str(call['talk_duration'])
            transcript = call['transcript']
            context_start_time = call['context_start_time']
            call_date = timestamp_to_datetime(context_start_time).strftime('%Y-%m-%d %H:%M:%S') if context_start_time else None
            if transcript:
                tasks.append(analyze_and_save_call(
                    connection, transcript, checklists, call_id, call_date, called_info, caller_info, talk_duration, lock))
        
        try:
            await asyncio.gather(*tasks)
        except Exception as e:
            logger.exception(f"Ошибка при обработке недостающих звонков: {e}")

        logger.info(f"Осталось выгрузить {len(missing_ids)} записей для анализа")

async def main():
    """Основная асинхронная функция."""
    logger.info("Начало выполнения скрипта")
    connection = None
    lock = asyncio.Lock()  # Добавляем инициализацию
    try:
        connection = await get_db_connection()
        if connection is None:
            logger.error("Подключение к базе данных не удалось, завершение программы.")
            return

        logger.info("Подключение к базе данных успешно")
        await create_tables(connection)

        checklists = await get_checklists_and_criteria(connection)
        logger.info(f"Получены чек-листы: {checklists}")

        call_history_ids = await get_history_ids_from_call_history(connection)
        if call_history_ids is None:
            logger.error("Не удалось получить идентификаторы истории звонков")
            return
            
        call_scores_ids = await get_history_ids_from_call_scores(connection)
        if call_scores_ids is None:
            logger.error("Не удалось получить идентификаторы оценок звонков")
            return

        # Теперь получаем идентификаторы по ключу 'history_id'
        call_history_ids_set = set(row['history_id'] for row in call_history_ids)
        call_scores_ids_set = set(row['history_id'] for row in call_scores_ids)

        missing_ids = list(call_history_ids_set - call_scores_ids_set)
        logger.info(f"Отсутствующие ID: {missing_ids}")

        if missing_ids:
            lock = asyncio.Lock()
            await process_missing_calls(missing_ids, connection, checklists, lock)

            offset = 0
            while True:
                query = """
                SELECT history_id, called_info, caller_info, talk_duration, transcript, context_start_time
                FROM call_history 
                WHERE context_start_time >= %s
                ORDER BY history_id DESC
                LIMIT %s OFFSET %s
                """
                call_data = await execute_async_query(connection, query, (START_DATE_TIMESTAMP, CONFIG['LIMIT'], offset))
                if not call_data:
                    break
                await process_calls(call_data, connection, checklists, lock)
                offset += CONFIG['LIMIT']
    except Exception as e:
        logger.exception(f"Ошибка при выполнении основного цикла: {e}")
    finally:
        if connection:
            connection.close()
            logger.info("Соединение с базой данных закрыто")


@app.route('/api/call_history')
async def get_call_history():
    """API для получения истории звонков."""
    conn = await get_db_connection()
    if not conn:
        return jsonify({"error": "Не удалось подключиться к базе данных"}), 500
    
    query = "SELECT * FROM call_history WHERE context_start_time >= %s"
    async with conn.cursor() as cursor:
        await cursor.execute(query, (START_DATE_TIMESTAMP,))
        rows = await cursor.fetchall()
        calls = [dict(zip([col[0] for col in cursor.description], row)) for row in rows]
    conn.close()
    return jsonify(calls)

@app.route('/<path:filename>')
async def serve_static(filename):
    """Обслуживание статических файлов."""
    return await send_from_directory('static', filename)

if __name__ == '__main__':
    check_and_clear_logs()
    flask_thread = threading.Thread(target=app.run, kwargs={"host": "0.0.0.0", "port": 5005, "debug": True})
    flask_thread.start()
    asyncio.run(main())