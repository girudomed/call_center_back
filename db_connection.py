#db_connection.py
import aiomysql
import logging
from dotenv import load_dotenv
import os
import asyncio
from typing import Optional, Tuple

# Загрузка переменных окружения
load_dotenv()

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

async def create_async_connection() -> Optional[aiomysql.Connection]:
    logger.info("Попытка асинхронного подключения к базе данных MySQL...")
    try:
        # Получение переменных окружения
        host_env = os.getenv("DB_HOST")
        user_env = os.getenv("DB_USER")
        password_env = os.getenv("DB_PASSWORD")
        db_name_env = os.getenv("DB_NAME")
        db_port_env = os.getenv("DB_PORT")

        # Проверяем, что все переменные окружения установлены
        missing_vars = []
        if not host_env:
            missing_vars.append("DB_HOST")
        if not user_env:
            missing_vars.append("DB_USER")
        if not password_env:
            missing_vars.append("DB_PASSWORD")
        if not db_name_env:
            missing_vars.append("DB_NAME")
        if not db_port_env:
            missing_vars.append("DB_PORT")

        if missing_vars:
            logger.error(f"Отсутствуют или пусты следующие переменные окружения: {', '.join(missing_vars)}")
            return None

        # Теперь мы можем безопасно утверждать, что переменные не равны None
        # Используем typing.cast, чтобы помочь анализатору типов
        from typing import cast

        host = cast(str, host_env)
        user = cast(str, user_env)
        password = cast(str, password_env)
        db_name = cast(str, db_name_env)
        db_port_str = cast(str, db_port_env)

        # Преобразование порта в int
        try:
            db_port_int = int(db_port_str)
        except ValueError:
            logger.error("Переменная окружения DB_PORT должна быть числом.")
            return None
        
        # Создание соединения
        connection = await aiomysql.connect(
            host=host,
            user=user,
            password=password,
            db=db_name,
            port=db_port_int,
            cursorclass=aiomysql.DictCursor,
            autocommit=True
        )
        logger.info("Подключено к серверу MySQL")
        return connection
    except aiomysql.Error as e:
        logger.error(f"Ошибка при подключении к базе данных: {e}")
        return None
    except Exception as e:
        logger.error(f"Неизвестная ошибка при подключении к базе данных: {e}")
        return None

async def execute_async_query(
    connection: Optional[aiomysql.Connection],
    query: str,
    params: Optional[Tuple] = None,
    retries: int = 3
) -> Tuple[Optional[list], Optional[aiomysql.Connection]]:
    if connection is None:
        logger.error("Соединение с базой данных не установлено.")
        return None, None

    for attempt in range(1, retries + 1):
        try:
            async with connection.cursor() as cursor:
                await cursor.execute(query, params)
                result = await cursor.fetchall()
                logger.info(f"Запрос успешно выполнен, получено {len(result)} записей.")
                return result, connection
        except aiomysql.Error as e:
            logger.error(f"Ошибка '{e}' при выполнении запроса.")
            if e.args[0] in (2013, 2006):  # Потеря соединения с сервером MySQL
                logger.warning(f"Попытка {attempt} из {retries} переподключения...")
                if not connection.closed:
                    connection.close()
                connection = await create_async_connection()
                if connection is None:
                    logger.error("Не удалось переподключиться к базе данных.")
                    break
                await asyncio.sleep(1)  # Задержка перед повторной попыткой
            else:
                break
        except Exception as e:
            logger.error(f"Неизвестная ошибка при выполнении запроса: {e}")
            break
    return None, connection

async def main():
    connection = await create_async_connection()
    if connection is None:
        logger.error("Не удалось подключиться к базе данных.")
        return

    try:
        query = "SELECT COUNT(*) AS count FROM call_history;"
        result, connection = await execute_async_query(connection, query)
        if result:
            logger.info(f"Тестовый запрос выполнен успешно: {result}")
        else:
            logger.error("Тестовый запрос вернул пустой результат или произошла ошибка.")
    finally:
        if connection and not connection.closed:
            connection.close()

if __name__ == "__main__":
    asyncio.run(main())
