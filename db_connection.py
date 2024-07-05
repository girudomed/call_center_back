import aiomysql
import logging
from dotenv import load_dotenv
import os

# Загрузка переменных окружения
load_dotenv()

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

async def create_async_connection():
    logger.info("Попытка асинхронного подключения к базе данных MySQL...")
    try:
        connection = await aiomysql.connect(
            host=os.getenv("DB_HOST"),
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASSWORD"),
            db=os.getenv("DB_NAME"),
            port=int(os.getenv("DB_PORT")),
            cursorclass=aiomysql.DictCursor,
            autocommit=True  # Это может помочь избежать проблем с потерей соединения
        )
        logger.info(f"Подключено к серверу MySQL")
        return connection
    except aiomysql.Error as e:
        logger.error(f"Произошла ошибка '{e}' при подключении к базе данных.")
        return None

async def execute_async_query(connection, query, params=None, retries=3):
    for attempt in range(retries):
        try:
            async with connection.cursor() as cursor:
                await cursor.execute(query, params)
                result = await cursor.fetchall()
                logger.info(f"Запрос успешно выполнен, получено {len(result)} записей")
                return result
        except aiomysql.Error as e:
            logger.error(f"Произошла ошибка '{e}' при выполнении запроса: {query}")
            if e.args[0] in (2013, 2006):  # MySQL server has gone away, Lost connection to MySQL server during query
                logger.info(f"Попытка повторного подключения...")
                await connection.ensure_closed()
                connection = await create_async_connection()
                if connection is None:
                    return None
            else:
                return None
    return None

async def main():
    connection = await create_async_connection()
    if connection is None:
        logger.error("Не удалось подключиться к базе данных.")
        return

    try:
        query = "SELECT COUNT(*) AS count FROM call_history;"
        result = await execute_async_query(connection, query)
        if result:
            logger.info(f"Тестовый запрос выполнен успешно: {result}")
        else:
            logger.error("Тестовый запрос вернул пустой результат или произошла ошибка.")
    
    finally:
        await connection.ensure_closed()

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
