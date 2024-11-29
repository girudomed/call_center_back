###Этот модуль работает с чек-листами. Но тут настройка БД идет, конфигурация
#Метод за чек-листы async def get_checklists_and_criteria
### weight_criteria удалили отсюда как сам параметр, к нему не обращаемся

import logging
import aiomysql
from async_db_connection import execute_async_query

logger = logging.getLogger()

async def create_async_connection():
    logger.info("Попытка асинхронного подключения к базе данных MySQL...")
    try:
        connection = await aiomysql.connect(
            host="82.97.254.49",
            user="gen_user",
            password="_7*sA:J_urBLo<p4:K2fOlQdb_ds",
            db="mangoapi_db",
            port=3306,
            cursorclass=aiomysql.DictCursor,
            autocommit=True  # Это может помочь избежать проблем с потерей соединения
        )
        logger.info("Подключено к серверу MySQL")
        return connection
    except aiomysql.Error as e:
        logger.error(f"Произошла ошибка '{e}' при подключении к базе данных.")
        return None

async def create_tables(connection):
    logger.info("Создание необходимых таблиц, если они не существуют...")
    async with connection.cursor() as cursor:
        try:
            await cursor.execute("""
            CREATE TABLE IF NOT EXISTS call_history (
                history_id INT AUTO_INCREMENT PRIMARY KEY,
                called_info VARCHAR(255),
                caller_info VARCHAR(255),
                talk_duration INT,
                transcript TEXT,
                context_start_time DATETIME,
                created_at DATETIME
            )
            """)

            await cursor.execute("""
            CREATE TABLE IF NOT EXISTS call_scores (
                id INT AUTO_INCREMENT PRIMARY KEY,
                history_id INT,
                call_score FLOAT,
                score_date DATETIME,
                call_date DATETIME,
                call_category VARCHAR(255),
                called_info VARCHAR(255),
                caller_info VARCHAR(255),
                talk_duration INT,
                transcript TEXT,
                result TEXT,
                number_checklist INT,
                category_checklist TEXT,
                FOREIGN KEY (history_id) REFERENCES call_history(history_id)
            )
            """)

            await cursor.execute("""
            CREATE TABLE IF NOT EXISTS check_list (
                Number_check_list INT AUTO_INCREMENT PRIMARY KEY,
                Check_list_categories VARCHAR(255) NOT NULL,
                description TEXT NOT NULL,
                criteria_check_list TEXT NOT NULL,
                type_criteria VARCHAR(255),
                criterion_category VARCHAR(255)
            )
            """)

            await connection.commit()
            logger.info("Все таблицы успешно созданы или уже существуют.")
        except Exception as e:
            logger.error(f"Произошла ошибка '{e}' при создании таблиц.")
            await connection.rollback()

async def get_checklists_and_criteria(connection):
    logger.info("Получение чек-листов и критериев из базы данных...")
    query = """
    SELECT Number_check_list, Check_list_categories, description, criteria_check_list, type_criteria, criterion_category, scoring_method, fatal_error, max_score
    FROM check_list
    """
    checklists = await execute_async_query(connection, query)
    return checklists if checklists else []

async def main():
    connection = await create_async_connection()
    if connection is None:
        logger.error("Не удалось установить соединение с базой данных.")
        return
    try:
        await create_tables(connection)
    finally:
        connection.close()

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())