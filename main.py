#main.py
import asyncio
import logging
import signal
import threading  # noqa: F401
import aiohttp
import openai
from datetime import datetime  # noqa: F401
import aiomysql
from async_db_connection import ConnectionPool, execute_async_query
from async_db_connection import restart_program
from db_setup import create_tables, get_checklists_and_criteria
from gpt_config import analyze_call_with_gpt, save_call_score
from logging_config import setup_logging, check_and_clear_logs
from result_logging import log_analysis_result
from quart import Quart, jsonify, render_template, send_from_directory
import datetime as dt
import json
import os
import socket
from logging.handlers import RotatingFileHandler
import hypercorn.asyncio
import hypercorn.config
from app import setup_routes
from dotenv import load_dotenv

load_dotenv()

# Настройка логирования с ротацией
db_logger = logging.getLogger('db_logger')
db_logger.setLevel(logging.INFO)

# Ротация: до 10,000 строк (~10 MB) с перезаписью
db_file_handler = RotatingFileHandler(
    'logging_mysql.log', 
    maxBytes=10 * 1024 * 1024,  # Размер файла ~10 MB
    backupCount=0  # Без резервных копий, перезапись текущего файла
)
db_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
db_file_handler.setFormatter(db_formatter)
db_logger.addHandler(db_file_handler)

# Инициализация глобальных переменных
app = Quart(__name__)
logger = logging.getLogger(__name__)
loop = asyncio.get_event_loop()
lock = asyncio.Lock()

# Параметры конфигурации
CONFIG = {
    'LIMIT': 5,
    'RETRIES': 3,
    'START_DATE': '2024-12-01 00:00:00',
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
# Инициализация пула соединений
pool = ConnectionPool()

async def initialize_db_pool():
    """Инициализация пула соединений MySQL."""
    await pool.initialize(
        host=CONFIG['DB_HOST'],
        user=CONFIG['DB_USER'],
        password=CONFIG['DB_PASSWORD'],
        db=CONFIG['DB_NAME'],
        port=CONFIG['DB_PORT'],
        maxsize=10
    )

async def close_db_pool():
    """Закрытие пула соединений."""
    await pool.close()

#Логируем состояние БДшки
async def log_db_state():
    """Логирование состояния базы данных."""
    queries = {
        "Threads_connected": "SHOW STATUS LIKE 'Threads_connected';",
        "Threads_running": "SHOW STATUS LIKE 'Threads_running';",
        "Connections": "SHOW STATUS LIKE 'Connections';",
        "Questions": "SHOW STATUS LIKE 'Questions';",
        "Queries": "SHOW STATUS LIKE 'Queries';",
        "Slow_queries": "SHOW STATUS LIKE 'Slow_queries';",
        "Qcache_hits": "SHOW STATUS LIKE 'Qcache_hits';",
        "Qcache_inserts": "SHOW STATUS LIKE 'Qcache_inserts';",
        "Qcache_not_cached": "SHOW STATUS LIKE 'Qcache_not_cached';",
        "Open_tables": "SHOW STATUS LIKE 'Open_tables';",
        "Opened_tables": "SHOW STATUS LIKE 'Opened_tables';",
        "Table_locks_waited": "SHOW STATUS LIKE 'Table_locks_waited';",
        "Table_locks_immediate": "SHOW STATUS LIKE 'Table_locks_immediate';",
        "Handler_read_key": "SHOW STATUS LIKE 'Handler_read_key';",
        "Handler_read_rnd_next": "SHOW STATUS LIKE 'Handler_read_rnd_next';",
        "Max_used_connections": "SHOW STATUS LIKE 'Max_used_connections';",
        "Aborted_clients": "SHOW STATUS LIKE 'Aborted_clients';",
        "Aborted_connects": "SHOW STATUS LIKE 'Aborted_connects';",
        "Innodb_buffer_pool_reads": "SHOW STATUS LIKE 'Innodb_buffer_pool_reads';",
        "Innodb_buffer_pool_write_requests": "SHOW STATUS LIKE 'Innodb_buffer_pool_write_requests';",
        "Innodb_rows_read": "SHOW STATUS LIKE 'Innodb_rows_read';",
        "Innodb_rows_inserted": "SHOW STATUS LIKE 'Innodb_rows_inserted';",
        "Innodb_rows_updated": "SHOW STATUS LIKE 'Innodb_rows_updated';",
        "Innodb_rows_deleted": "SHOW STATUS LIKE 'Innodb_rows_deleted';",
        "Uptime": "SHOW STATUS LIKE 'Uptime';",
        "PROCESSLIST": "SHOW STATUS LIKE 'PROCESSLIST'"
    }

    for metric, query in queries.items():
        try:
            result = await execute_async_query(pool, query)
            if result:
                for row in result:
                    db_logger.info(f"{row['Variable_name']}: {row['Value']}")
        except Exception as e:
            db_logger.error(f"Ошибка при выполнении запроса '{metric}': {e}")

async def schedule_db_state_logging(logging_interval=200):
    while True:
        try:
            await log_db_state()
        except Exception as e:
            db_logger.error(f"Ошибка при логировании состояния БД: {e}")
        await asyncio.sleep(logging_interval)

# Преобразование START_DATE в таймстемп для запросов
START_DATE_TIMESTAMP = int(dt.datetime.strptime(CONFIG['START_DATE'], '%Y-%m-%d %H:%M:%S').timestamp())


def datetime_to_timestamp(dt_object):
    """Преобразование объекта datetime в таймстемп."""
    return int(dt_object.timestamp())

def timestamp_to_datetime(timestamp):
    """Преобразование таймстемпа в объект datetime."""
    return dt.datetime.fromtimestamp(timestamp)

async def process_calls(calls, pool, checklists, lock):
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
                    pool, transcript, checklists, call_id, call_date, called_info, caller_info, talk_duration, lock))
        try:
            await asyncio.gather(*tasks)
        except Exception as e:
            logger.exception(f"Ошибка при обработке звонков: {e}")

async def analyze_and_save_call(pool, transcript, checklists, call_id, call_date, called_info, caller_info, talk_duration, lock):
    """Анализ и сохранение результатов звонка."""
    if isinstance(checklists, str):
        checklists = json.loads(checklists)  # Преобразование из JSON-строки в список
    elif isinstance(checklists, tuple):
        checklists = list(checklists)  # Преобразование кортежа в список

    # Цикл для повторных попыток анализа
    for attempt in range(CONFIG['RETRIES']):
        try:
            # Выполняем анализ звонка с помощью GPT
            score, result, call_category_clean, category_number, checklist_result = await analyze_call_with_gpt(transcript, checklists)
            
            if result is None:
                logger.error(f"Ошибка при анализе звонка {call_id}, пропуск сохранения результатов")
                return

            logger.info(f"Анализ звонка {call_id}: результат={result}, категория={call_category_clean}, чек-лист={checklist_result}")
            checklist_number = category_number
            checklist_category = checklist_result

            # Блокировка для безопасного сохранения результатов в базе данных
            async with lock:
                connection = await pool.get_connection()
                try:
                    await save_call_score(
                        connection, call_id, score, call_category_clean, call_date, called_info, caller_info,
                        talk_duration, transcript, result, category_number, checklist_number, checklist_category
                    )
                finally:
                    await pool.release_connection(connection)
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

async def get_history_ids_from_call_history(pool):
    query = "SELECT history_id FROM call_history WHERE context_start_time >= %s"
    return await execute_async_query(pool, query, (START_DATE_TIMESTAMP,))

async def get_history_ids_from_call_scores(pool):
    """Получение идентификаторов истории звонков."""
    query = "SELECT history_id FROM call_scores WHERE call_date >= %s"
    return await execute_async_query(pool, query, (CONFIG['START_DATE'],))

async def get_call_data_by_history_ids(pool, history_ids):
    """Получение данных о звонках по идентификаторам."""
    placeholders = ','.join(['%s'] * len(history_ids))  # Используем %s для плейсхолдеров
    query = f"""
    SELECT history_id, called_info, caller_info, talk_duration, transcript, context_start_time
    FROM call_history
    WHERE history_id IN ({placeholders}) AND context_start_time >= %s
    """
    return await execute_async_query(pool, query, tuple(history_ids) + (START_DATE_TIMESTAMP,))

async def process_missing_calls(missing_ids, pool, checklists, lock):
    """Обработка недостающих звонков."""
    while missing_ids:
        batch_ids = missing_ids[:CONFIG['BATCH_SIZE']]
        missing_ids = missing_ids[CONFIG['BATCH_SIZE']:]

        call_data = await get_call_data_by_history_ids(pool, batch_ids)
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
                    pool, transcript, checklists, call_id, call_date, called_info, caller_info, talk_duration, lock))
        
        try:
            await asyncio.gather(*tasks)
        except Exception as e:
            logger.exception(f"Ошибка при обработке недостающих звонков: {e}")

        logger.info(f"Осталось выгрузить {len(missing_ids)} записей для анализа")

async def main():
    logger.info("Начало выполнения скрипта")
    try:
        await initialize_db_pool()
        logger.info("Пул соединений MySQL успешно инициализирован.")

        asyncio.create_task(schedule_db_state_logging(logging_interval=200))

        # Вызываем create_tables и get_checklists_and_criteria без получения connection
        # так как они будут использовать execute_async_query(pool, ...) внутри
        await create_tables(pool)
        checklists = await get_checklists_and_criteria(pool)
        logger.info(f"Получены чек-листы: {checklists}")
        # Передаём app и pool в setup_routes
        setup_routes(app, pool)

        # Чтение последнего состояния из БД при старте
        state_query = "SELECT last_processed_timestamp, last_processed_history_id FROM processing_state WHERE id = 1"
        state_result = await execute_async_query(pool, state_query)


        if state_result and state_result[0]['last_processed_timestamp']:
            last_processed_timestamp = state_result[0]['last_processed_timestamp']
            last_processed_history_id = state_result[0]['last_processed_history_id']
            logger.info(f"Загружено состояние из базы: timestamp={last_processed_timestamp}, history_id={last_processed_history_id}")
        else:
            # Инициализируем переменные для отслеживания последней обработанной записи.
            # Используем композитный ключ: (context_start_time, history_id)
            last_processed_timestamp = START_DATE_TIMESTAMP  # Последняя обработанная дата
            last_processed_history_id = 0  # Изначально нет обработанного history_id
            logger.info("Используются начальные значения состояния")

        call_history_ids = await get_history_ids_from_call_history(pool)
        if call_history_ids is None:
            logger.error("Не удалось получить идентификаторы истории звонков")
            return

        call_scores_ids = await get_history_ids_from_call_scores(pool)
        if call_scores_ids is None:
            logger.error("Не удалось получить идентификаторы оценок звонков")
            return

        call_history_ids_set = set(row['history_id'] for row in call_history_ids)
        call_scores_ids_set = set(row['history_id'] for row in call_scores_ids)
        missing_ids = list(call_history_ids_set - call_scores_ids_set)
        logger.info(f"Отсутствующие ID: {missing_ids}")

        if missing_ids:
            await process_missing_calls(missing_ids, pool, checklists, lock)

        # Основной цикл обработки новых звонков
        while True:
            # Запрос изменен: вместо offset используется фильтрация по композитному ключу (context_start_time, history_id)
            query = """
            SELECT history_id, called_info, caller_info, talk_duration, transcript, context_start_time
            FROM call_history 
            WHERE (context_start_time, history_id) > (%s, %s)
            ORDER BY context_start_time ASC, history_id ASC
            LIMIT %s
            """
            call_data = await execute_async_query(pool, query, (last_processed_timestamp, last_processed_history_id, CONFIG['LIMIT']))
            if call_data:
                await process_calls(call_data, pool, checklists, lock)
                # Обновляем последнюю обработанную дату
                last_call = call_data[-1]
                last_processed_timestamp = last_call["context_start_time"]
                last_processed_history_id = last_call["history_id"]
                
                logger.info(f"Состояние обновлено до timestamp={last_processed_timestamp}, history_id={last_processed_history_id}")
            else:
                logger.info("Новых звонков нет, ожидаю...")

            # ⬇️ ВСЕГДА СОХРАНЯЙ СОСТОЯНИЕ В БАЗУ ДАННЫХ
            await execute_async_query(pool,
                "REPLACE INTO processing_state (id, last_processed_timestamp, last_processed_history_id) VALUES (1, %s, %s)",
                (last_processed_timestamp, last_processed_history_id)
            )

            await asyncio.sleep(10800)  # Ожидание следующей проверки

    except asyncio.CancelledError:
        logger.info("Основная задача отменена.")
        raise
    except Exception as e:
        logger.exception(f"Критическая ошибка: {e}")
        restart_program()
    finally:
        await close_db_pool()  # <— ВАЖНО! Теперь пул соединений будет закрыт корректно
        logger.info("Соединение с базой данных закрыто")

def run_flask():
    hypercorn_config = hypercorn.config.Config()
    hypercorn_config.bind = ["0.0.0.0:5005"]  # Настройка привязки порта
    loop = asyncio.new_event_loop()  # Создаем новый event loop
    asyncio.set_event_loop(loop)  # Устанавливаем его как текущий loop
    loop.run_until_complete(hypercorn.asyncio.serve(app, hypercorn_config))

if __name__ == '__main__':
    check_and_clear_logs()
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.start()
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Получен сигнал прерывания от пользователя (Ctrl+C). Завершение программы.")
    except Exception as e:
        logger.critical(f"Необработанная ошибка: {e}. Программа будет перезапущена.")
        restart_program()  # Перезапуск при ошибке в '__main__'
    finally:
        logger.info("Программа завершена.")