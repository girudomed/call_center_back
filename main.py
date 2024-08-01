import asyncio
import logging
import aiohttp
import openai
from datetime import datetime
import aiomysql
from async_db_connection import create_async_connection, execute_async_query
from db_setup import create_tables, get_checklists_and_criteria
from gpt_config import analyze_call_with_gpt, save_call_score
from logging_config import setup_logging, check_and_clear_logs
from result_logging import log_analysis_result
from quart import Quart, jsonify, send_from_directory
import datetime as dt
import threading

# Создание экземпляра приложения Quart
app = Quart(__name__)

# Параметры
CONFIG = {
    'LIMIT': 5,
    'RETRIES': 3,
    'START_DATE': '2024-06-26 00:00:00',
    'BATCH_SIZE': 30,
    'ENABLE_LOGGING': True,
    'DB_HOST': '82.97.254.49',
    'DB_PORT': 3306,
    'DB_USER': 'gen_user',
    'DB_PASSWORD': '_7*sA:J_urBLo<p4:K2fOlQdb_ds',
    'DB_NAME': 'mangoapi_db'
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
            autocommit=True
        )
        return conn
    except Exception as e:
        logger.exception(f"Ошибка при подключении к базе данных: {e}")
        return None

async def execute_async_query(connection, query, params=None):
    """Выполнение асинхронного SQL-запроса."""
    async with connection.cursor() as cursor:
        await cursor.execute(query, params)
        if cursor.description:
            result = await cursor.fetchall()
            return result
        return None

async def process_calls(calls, connection, checklists, lock):
    """Обработка списка звонков."""
    tasks = []
    for row in calls:
        call = {
            'history_id': row[0],
            'called_info': row[1],
            'caller_info': row[2],
            'talk_duration': row[3],
            'transcript': row[4],
            'context_start_time': row[5]
        }
        call_id = call['history_id']
        called_info = call['called_info']
        caller_info = call['caller_info']
        talk_duration = str(call['talk_duration'])
        transcript = call['transcript']
        context_start_time = call['context_start_time']
        call_date = timestamp_to_datetime(context_start_time).strftime('%Y-%m-%d %H:%M:%S') if context_start_time else None
        if transcript:
            tasks.append(analyze_and_save_call(
                transcript, checklists, connection, call_id, call_date, called_info, caller_info, talk_duration, lock))
    try:
        await asyncio.gather(*tasks)
    except Exception as e:
        logger.exception(f"Ошибка при обработке звонков: {e}")

async def analyze_and_save_call(transcript, checklists, connection, call_id, call_date, called_info, caller_info, talk_duration, lock):
    """Анализ и сохранение результатов звонка."""
    for attempt in range(CONFIG['RETRIES']):
        try:
            score, result, call_category, category_number, checklist_result = await analyze_call_with_gpt(transcript, checklists)
            if result is None:
                logger.error(f"Ошибка при анализе звонка {call_id}, пропуск сохранения результатов")
                return
            logger.info(f"Анализ звонка {call_id}: результат={result}, категория={call_category}, чек-лист={checklist_result}")
            checklist_number = category_number
            checklist_category = checklist_result

            async with lock:
                await save_call_score(
                    connection, call_id, score, call_category, call_date, called_info, caller_info, talk_duration, transcript, result, category_number, checklist_number, checklist_category)
            logger.info(f"Звонок {call_id} сохранен с результатом: {result}")

            log_analysis_result(call_id, result)
            break
        except openai.error.RateLimitError as e:
            logger.warning(f"Превышен лимит запросов для звонка {call_id}: {e}")
            if attempt < CONFIG['RETRIES'] - 1:
                await asyncio.sleep(2 ** attempt)  # Динамическая задержка между попытками
                continue
            else:
                logger.error(f"Превышен лимит попыток для звонка {call_id}")
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
    """Получение идентификаторов оценок звонков."""
    query = "SELECT history_id FROM call_scores"
    return await execute_async_query(connection, query)

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
        for row in call_data:
            call = {
                'history_id': row[0],
                'called_info': row[1],
                'caller_info': row[2],
                'talk_duration': row[3],
                'transcript': row[4],
                'context_start_time': row[5]
            }
            call_id = call['history_id']
            called_info = call['called_info']
            caller_info = call['caller_info']
            talk_duration = str(call['talk_duration'])
            transcript = call['transcript']
            context_start_time = call['context_start_time']
            call_date = timestamp_to_datetime(context_start_time).strftime('%Y-%m-%d %H:%M:%S') if context_start_time else None
            if transcript:
                tasks.append(analyze_and_save_call(
                    transcript, checklists, connection, call_id, call_date, called_info, caller_info, talk_duration, lock))
        
        try:
            await asyncio.gather(*tasks)
        except Exception as e:
            logger.exception(f"Ошибка при обработке недостающих звонков: {e}")

        logger.info(f"Осталось выгрузить {len(missing_ids)} записей для анализа")

async def main():
    """Основная асинхронная функция."""
    logger.info("Начало выполнения скрипта")
    connection = None
    try:
        connection = await get_db_connection()
        if connection:
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

            call_history_ids_set = set(row[0] for row in call_history_ids)
            call_scores_ids_set = set(row[0] for row in call_scores_ids)

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
