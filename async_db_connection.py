import aiomysql
import logging
from dotenv import load_dotenv
import os

# Загрузка переменных окружения
load_dotenv()

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def create_async_connection():
    """Создание асинхронного подключения к базе данных MySQL."""
    logger.info("Попытка асинхронного подключения к базе данных MySQL...")
    try:
        connection = await aiomysql.connect(
            host=os.getenv("DB_HOST"),
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASSWORD"),
            db=os.getenv("DB_NAME"),
            port=int(os.getenv("DB_PORT")),
            cursorclass=aiomysql.DictCursor,
            autocommit=True
        )
        logger.info("Подключение к серверу MySQL успешно установлено")
        return connection
    except aiomysql.Error as e:
        logger.error(f"Произошла ошибка '{e}' при подключении к базе данных.")
        return None

async def execute_async_query(connection, query, params=None, retries=3):
    """Выполнение асинхронного SQL-запроса с поддержкой повторных попыток."""
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
                logger.info("Попытка повторного подключения...")
                await connection.close()  # Исправлено: закрываем соединение
                connection = await create_async_connection()
                if connection is None:
                    logger.error("Не удалось установить новое соединение с базой данных.")
                    return None
            else:
                logger.error("Ошибка не связана с потерей соединения, повторное подключение не предпринято.")
                return None
        except Exception as e:
            logger.exception(f"Неизвестная ошибка при выполнении запроса: {e}")
            return None

    logger.error(f"Не удалось выполнить запрос после {retries} попыток")
    return None

async def main():
    """Тестирование подключения и выполнения запроса."""
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
        if connection is not None:
            await connection.close()  # Исправлено: корректное закрытие соединения
            logger.info("Соединение с базой данных закрыто")

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
