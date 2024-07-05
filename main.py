import logging
import asyncio
import aiohttp
import openai
from datetime import datetime
from async_db_connection import create_async_connection, execute_async_query
from db_setup import create_tables, get_checklists_and_criteria
from gpt_config import analyze_call_with_gpt, save_call_score
from logging_config import setup_logging, check_and_clear_logs
from result_logging import log_analysis_result
from quart import Quart, jsonify, render_template, send_from_directory
import aiosqlite
import threading
import datetime as dt

app = Quart(__name__)

# Параметры
LIMIT = 5
RETRIES = 3
START_DATE = '2024-06-26 00:00:00'
BATCH_SIZE = 30
ENABLE_LOGGING = True
# date_timeA = timestamp('')
# SELECT `id`, `call_...` WHERE `context_call` BETWEEN 'date_timeA' AND 'date_timeB' LIMIT LIMIT
# можно попробовать через - код перед работой просит чтоб я указал дату и будет ее читать в любом формате через терминал

# Настройка логирования
logger = setup_logging(ENABLE_LOGGING)

# Функция для подключения к базе данных SQLite
async def get_db_connection():
    try:
        conn = await aiosqlite.connect('database.db')
        conn.row_factory = aiosqlite.Row
        return conn
    except Exception as e:
        logger.exception(f"Ошибка при подключении к базе данных: {e}")
        return None

async def process_calls(calls, connection, checklists, lock):
    tasks = []
    for call in calls:
        call_id = call['history_id']
        called_info = call['called_info']
        caller_info = call['caller_info']
        talk_duration = str(call['talk_duration'])
        transcript = call['transcript']
        context_start_time = call['context_start_time']
        call_date = datetime.fromtimestamp(context_start_time).strftime('%Y-%m-%d %H:%M:%S') if context_start_time else None  # Преобразование даты
        if transcript:
            tasks.append(analyze_and_save_call(transcript, checklists, connection, call_id, call_date, called_info, caller_info, talk_duration, lock))
    try:
        await asyncio.gather(*tasks)
    except Exception as e:
        logger.exception(f"Ошибка при обработке звонков: {e}")

async def analyze_and_save_call(transcript, checklists, connection, call_id, call_date, called_info, caller_info, talk_duration, lock):
    for attempt in range(RETRIES):
        try:
            score, result, call_category, category_number, checklist_result = await analyze_call_with_gpt(transcript, checklists)
            if result is None:
                logger.error(f"Ошибка при анализе звонка {call_id}, пропуск сохранения результатов")
                return
            logger.info(f"Анализ звонка {call_id}: результат={result}, категория={call_category}, чек-лист={checklist_result}")
            checklist_number = category_number
            checklist_category = checklist_result
            
            async with lock:
                await save_call_score(connection, call_id, score, call_category, call_date, called_info, caller_info, talk_duration, transcript, result, category_number, checklist_number, checklist_category)
            logger.info(f"Звонок {call_id} сохранен с результатом: {result}")

            log_analysis_result(call_id, result)
            break
        except openai.error.RateLimitError as e:
            logger.warning(f"Превышен лимит запросов для звонка {call_id}: {e}")
            if attempt < RETRIES - 1:
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
    query = "SELECT history_id FROM call_history WHERE context_start_time >= %s"
    return await execute_async_query(connection, query, (START_DATE,))

async def get_history_ids_from_call_scores(connection):
    query = "SELECT history_id FROM call_scores"
    return await execute_async_query(connection, query)

async def get_call_data_by_history_ids(connection, history_ids):
    placeholders = ','.join(['%s'] * len(history_ids))  # Используем %s для плейсхолдеров
    query = f"""
    SELECT history_id, called_info, caller_info, talk_duration, transcript, context_start_time
    FROM call_history
    WHERE history_id IN ({placeholders}) AND context_start_time >= %s
    """
    return await execute_async_query(connection, query, tuple(history_ids) + (START_DATE,))

async def process_missing_calls(missing_ids, connection, checklists, lock):
    while missing_ids:
        batch_ids = missing_ids[:BATCH_SIZE]
        missing_ids = missing_ids[BATCH_SIZE:]

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
            call_date = datetime.fromtimestamp(context_start_time).strftime('%Y-%m-%d %H:%M:%S') if context_start_time else None  # Преобразование даты
            if transcript:
                tasks.append(analyze_and_save_call(transcript, checklists, connection, call_id, call_date, called_info, caller_info, talk_duration, lock))
        
        try:
            await asyncio.gather(*tasks)
        except Exception as e:
            logger.exception(f"Ошибка при обработке недостающих звонков: {e}")

        logger.info(f"Осталось выгрузить {len(missing_ids)} записей для анализа")

async def main():
    logger.info("Начало выполнения скрипта")
    try:
        connection = await create_async_connection()
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
                try:
                    last_calls = await execute_async_query(connection, query, (START_DATE, BATCH_SIZE, offset))
                    if not last_calls:
                        break

                    await process_calls(last_calls, connection, checklists, lock)
                    offset += BATCH_SIZE
                except Exception as e:
                    logger.exception(f"Ошибка при выполнении запроса или обработке звонков: {e}")
                    break

            await connection.ensure_closed()
            logger.info("Подключение к базе данных закрыто")
    except Exception as e:
        logger.exception(f"Ошибка при инициализации: {e}")

@app.route('/api/calls', methods=['GET'])
async def get_calls():
    conn = await get_db_connection()
    if conn is None:
        return jsonify({'error': 'Ошибка подключения к базе данных'}), 500

    try:
        async with conn.execute('SELECT * FROM calls') as cursor:
            calls = await cursor.fetchall()
            return jsonify([dict(ix) for ix in calls])
    except Exception as e:
        logger.exception(f"Ошибка при выполнении запроса к базе данных: {e}")
        return jsonify({'error': 'Ошибка при выполнении запроса к базе данных'}), 500
    finally:
        await conn.close()

@app.route('/')
async def index():
    return await render_template('index.html')

@app.route('/call_history')
async def call_history():
    return await render_template('call_history.html')

@app.route('/frontend/styles.css')
async def styles():
    return await send_from_directory('static/frontend', 'styles.css')

@app.route('/frontend/scripts.js')
async def scripts():
    return await send_from_directory('static/frontend', 'scripts.js')

def run_flask():
    app.run(host='0.0.0.0', port=5005, debug=True)

if __name__ == '__main__':
    check_and_clear_logs()
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.start()
    asyncio.run(main())