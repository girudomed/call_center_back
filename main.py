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
from hypercorn.asyncio import serve
from hypercorn.config import Config
from app import setup_routes
from dotenv import load_dotenv
from aiomysql import DatabaseError

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
    'START_DATE_TIMESTAMP': '1733004000',
    'BATCH_SIZE': 30,
    'ENABLE_LOGGING': True,
    'DB_HOST': os.getenv('DB_HOST'),
    'DB_PORT': int(os.getenv('DB_PORT', 3306)),
    'DB_USER': os.getenv('DB_USER'),
    'DB_PASSWORD': os.getenv('DB_PASSWORD'),
    'DB_NAME': os.getenv('DB_NAME'),
    'MAX_ATTEMPTS': 3
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

async def get_call_data_by_history_ids(pool, history_ids):
    placeholders = ','.join(['%s'] * len(history_ids))
    query = f"""
    SELECT history_id, called_info, caller_info, talk_duration, transcript, context_start_time
    FROM call_history
    WHERE history_id IN ({placeholders}) AND context_start_time >= %s
    """
    rows = await execute_async_query(pool, query, tuple(history_ids) + (START_DATE_TIMESTAMP,))
    if rows is None:
        print("Получили None вместо списка, возвращаем пустой список")  # Лучше logger.warning
        return []
    columns = ['history_id', 'called_info', 'caller_info', 'talk_duration', 'transcript', 'context_start_time']
    return [dict(zip(columns, row)) for row in rows]

async def process_missing_calls(missing_ids, pool, checklists, lock):
    """Обработка недостающих звонков.
    Каждый history_id обрабатывается ровно один раз. Если звонок уже в call_scores, пропускаем.
    """
    failed_ids = {}  # Словарь для неудачных попыток
    batch_size = CONFIG.get('BATCH_SIZE', 100)  # Берем из конфига, дефолт 100
    start_date = CONFIG.get('START_DATE', '2024-12-01 00:00:00')  # Фильтр по дате из конфига

    # Вытаскиваем все history_id из call_scores один раз с фильтром по дате
    call_scores_ids = set(await get_history_ids_from_call_scores(pool, start_date=start_date))

    while missing_ids:
        # Извлекаем батч идентификаторов
        batch_ids = missing_ids[:batch_size]
        missing_ids = missing_ids[batch_size:]

        for call_id in batch_ids:
            failed_ids.setdefault(call_id, 0)
            try:
                logger.info(f"Пытаюсь обработать пропущенный history_id: {call_id}")

                # Проверяем, есть ли звонок уже в call_scores через set
                if call_id in call_scores_ids:
                    logger.info(f"history_id {call_id} уже обработан, пропускаю")
                    continue

                # Получаем данные для звонка
                logger.info(f"Запрашиваю данные для history_id: {call_id}")
                call_data = await get_call_data_by_history_ids(pool, [call_id])
                logger.info(f"Получено call_data: {call_data}, тип: {type(call_data)}")

                if call_data is None:
                    logger.error(f"Проблема с данными для history_id {call_id}: {call_data}")
                    failed_ids[call_id] += 1
                    continue
                if not isinstance(call_data, list):
                    logger.warning(f"call_data не список для history_id {call_id}, оборачиваю")
                    call_data = [call_data]
                if not call_data:
                    logger.warning(f"Для history_id {call_id} не найдено данных")
                    continue

                tasks = []
                for call in call_data:
                    if isinstance(call, tuple):
                        logger.warning(f"call_data для {call_id} вернул кортеж, ожидался словарь: {call}")
                        continue  # Пропускаем, если формат не тот, или можно добавить преобразование
                    call_id_inner = call.get('history_id')
                    if call_id_inner is None:
                        logger.error(f"Пропущен звонок без history_id: {call}")
                        continue
                    logger.info(f"Начинаю обработку звонка ID: {call_id_inner}")

                    # Извлекаем данные с дефолтами
                    called_info = call.get('called_info', 'Неизвестно')
                    caller_info = call.get('caller_info', 'Неизвестно')
                    talk_duration = call.get('talk_duration', 0) or 0
                    talk_duration = str(talk_duration)  # Оставляем как varchar(50)
                    transcript = call.get('transcript')
                    context_start_time = call.get('context_start_time')

                    if context_start_time is None:
                        logger.error(f"Нет context_start_time для history_id {call_id_inner}, пропускаю")
                        continue

                    # Преобразуем дату
                    try:
                        if isinstance(context_start_time, (int, float)):
                            call_date = timestamp_to_datetime(context_start_time).strftime('%Y-%m-%d %H:%M:%S')
                        else:
                            call_date = context_start_time  # Если уже строка, оставляем
                    except Exception as e:
                        logger.error(f"Ошибка преобразования context_start_time для ID {call_id_inner}: {e}")
                        call_date = None

                    if not call_date:
                        logger.error(f"Звонок ID {call_id_inner} пропущен: нет call_date")
                        continue

                    if not transcript or not transcript.strip():
                        logger.warning(f"Звонок ID {call_id_inner} пропущен: нет transcript или пустой")
                        continue

                    # Формируем задачу
                    tasks.append(analyze_and_save_call(
                        pool, transcript, checklists, call_id_inner, call_date,
                        called_info, caller_info, talk_duration, lock
                    ))

                # Выполняем задачи
                if tasks:
                    try:
                        results = await asyncio.gather(*tasks, return_exceptions=True)
                        for result in results:
                            if isinstance(result, Exception):
                                logger.error(f"Ошибка в задаче: {result}")
                                failed_ids[call_id] += 1
                            elif isinstance(result, dict) and 'history_id' in result:
                                logger.info(f"Успешно обработан ID {result['history_id']}")
                                if call_id in failed_ids:
                                    del failed_ids[call_id]  # Убираем из failed_ids при успехе
                                call_scores_ids.add(call_id)  # Добавляем в set, чтобы не повторять
                            else:
                                logger.warning(f"Неожиданный результат: {type(result)}, значение: {result}")
                    except Exception as e:
                        logger.exception(f"Критическая ошибка в батче для history_id {call_id}: {e}")
                        failed_ids[call_id] += 1

            except Exception as e:
                logger.exception(f"Ошибка при обработке history_id={call_id}: {e}")
                failed_ids[call_id] += 1

    logger.info(f"Осталось выгрузить {len(missing_ids)} записей для анализа")
    logger.info(f"Обработка завершена. Итоговый словарь ошибок: {failed_ids}")
    return failed_ids

# Вспомогательная функция для вытаскивания history_id
async def get_history_ids_from_call_scores(pool, start_date=None):
    query = "SELECT history_id FROM call_scores"
    params = []
    if start_date:
        query += " WHERE call_date >= %s"
        params.append(start_date)
    
    rows = await execute_async_query(pool, query, tuple(params))
    if rows is None:
        print("Получили None вместо списка, возвращаем пустой список")  # Лучше logger.warning
        return []
    return [row['history_id'] for row in rows if row.get('history_id') is not None]

async def main():
    global pool
    logger.info("Начало выполнения скрипта")
    try:
        await initialize_db_pool()  # Ошибки пул кидает сам
        logger.info("Пул соединений MySQL успешно инициализирован.")

        asyncio.create_task(schedule_db_state_logging(logging_interval=10800))

        await create_tables(pool)
        checklists = await get_checklists_and_criteria(pool)
        if not checklists:
            logger.warning("Чек-листы не загружены или пусты, продолжаем с пустым набором")
            checklists = []
        logger.info(f"Получено {len(checklists)} чек-листов")
        setup_routes(app, pool)

        # Чтение состояния из БД
        state_query = "SELECT last_processed_timestamp, last_processed_history_id FROM processing_state WHERE id = 1"
        state_result = await execute_async_query(pool, state_query)
        if state_result and state_result[0].get('last_processed_timestamp') is not None:
            last_processed_timestamp = state_result[0]['last_processed_timestamp']
            last_processed_history_id = state_result[0]['last_processed_history_id']
            logger.info(f"Состояние из базы: timestamp={last_processed_timestamp}, history_id={last_processed_history_id}")
        else:
            last_processed_timestamp = START_DATE_TIMESTAMP
            query = "SELECT MAX(history_id) AS max_id FROM call_scores WHERE call_date >= %s"
            result = await execute_async_query(pool, query, (CONFIG['START_DATE'],))
            last_processed_history_id = result[0]['max_id'] if result and result[0].get('max_id') is not None else 0
            logger.info(f"Начальное состояние: timestamp={last_processed_timestamp}, history_id={last_processed_history_id}")

        # Пропущенные ID одним запросом
        missing_ids_query = """
        SELECT ch.history_id
        FROM call_history ch
        LEFT JOIN call_scores cs ON ch.history_id = cs.history_id
        WHERE cs.history_id IS NULL AND ch.context_start_time >= %s
        """
        missing_ids_result = await execute_async_query(pool, missing_ids_query, (CONFIG['START_DATE'],))
        if missing_ids_result is not None:
            missing_ids = [row['history_id'] for row in missing_ids_result if row.get('history_id') is not None]
            logger.info(f"Пропущенные ID: {len(missing_ids)} шт.")
        else:    
            missing_ids = []
            logger.error("Не удалось получить пропущенные ID, missing_ids_result is None")
        logger.info(f"Пропущенные ID: {len(missing_ids)} шт.")
        
        if missing_ids:
            await process_missing_calls(missing_ids, pool, checklists, lock)

        # Основной цикл
        while True:
            try:
                logger.info(f"Фильтрую звонки: timestamp > {last_processed_timestamp}, history_id > {last_processed_history_id}")
                query = """
                SELECT history_id, called_info, caller_info, talk_duration, transcript, context_start_time
                FROM call_history 
                WHERE context_start_time IS NOT NULL
                AND history_id IS NOT NULL 
                AND (context_start_time, history_id) > (%s, %s)
                ORDER BY context_start_time ASC, history_id ASC
                LIMIT %s
                """
                call_data = await execute_async_query(pool, query, (last_processed_timestamp, last_processed_history_id, CONFIG['LIMIT']))
                if call_data:
                    logger.info(f"Найдено {len(call_data)} звонков для обработки")
                    await process_calls(call_data, pool, checklists, lock)
                    call = call_data[-1]
                    last_processed_timestamp = call["context_start_time"]
                    last_processed_history_id = call["history_id"]
                    await execute_async_query(pool,
                        "REPLACE INTO processing_state (id, last_processed_timestamp, last_processed_history_id) VALUES (1, %s, %s)",
                        (last_processed_timestamp, last_processed_history_id)
                    )
                    logger.info(f"Звонок ID {last_processed_history_id} обработан, состояние обновлено")
                else:
                    logger.info("Новых звонков нет, жду...")
                await asyncio.sleep(10800)
            except DatabaseError as e:
                logger.error(f"Ошибка базы: {e}, пытаюсь переподключиться")
                await initialize_db_pool()
            except Exception as e:
                logger.exception(f"Неизвестная хуйня: {e}")
                await asyncio.sleep(3600)
    except asyncio.CancelledError:
        logger.info("Задача отменена")
        raise
    except Exception as e:
        logger.exception(f"Критическая хуйня: {e}")
        restart_program()
    finally:
        await close_db_pool()
        logger.info("База закрыта")

async def run_app():
    hypercorn_config = hypercorn.config.Config()
    hypercorn_config.bind = ["0.0.0.0:5005"]  # Настройка привязки порта
    
    # Добавляем shutdown_trigger для graceful завершения
    shutdown_event = asyncio.Event()
    
    async def shutdown_trigger():
        await shutdown_event.wait()
    
    try:
        await asyncio.gather(
            hypercorn.asyncio.serve(app, hypercorn_config, shutdown_trigger=shutdown_trigger),
            main()
        )
    except Exception as e:
        logger.error(f"Ошибка в run_app: {e}")
        shutdown_event.set()  # Сигнализируем Hypercorn завершиться
        raise

if __name__ == '__main__':
    check_and_clear_logs()
    try:
        asyncio.run(run_app())
    except KeyboardInterrupt:
        logger.info("Получен сигнал прерывания от пользователя (Ctrl+C). Завершение программы.")
    except Exception as e:
        logger.critical(f"Необработанная ошибка: {e}. Программа завершена.")
    finally:
        logger.info("Программа завершена.")