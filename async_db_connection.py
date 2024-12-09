#async_db_connection.py
import asyncio
import aiomysql
import logging
from dotenv import load_dotenv
import os
import sys  # Для выхода из программы

# Загрузка переменных окружения
load_dotenv()

#**Тут тестовый запрос как у нас будет загружаться база данных и что выдавать какие значения, используем в отладках и тестах**
# Загрузка файла .env
#if load_dotenv():
    #print("Файл .env успешно загружен")
#else:
#    print("Файл .env не найден или не загружен")

# Проверка значений переменных
#print("DB_HOST:", os.getenv("DB_HOST"))
#print("DB_PORT:", os.getenv("DB_PORT"))
#print("DB_USER:", os.getenv("DB_USER"))
#print("DB_PASSWORD:", os.getenv("DB_PASSWORD"))
#print("DB_NAME:", os.getenv("DB_NAME"))

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)



class ConnectionPool:
    """Класс для управления пулом соединений MySQL."""
    def __init__(self):
        self._pool = None

    async def initialize(self, host, user, password, db, port, minsize=1, maxsize=10):
        """Инициализация пула соединений."""
        logger.info("Инициализация пула соединений MySQL...")
        self._pool = await aiomysql.create_pool(
            host=host,
            user=user,
            password=password,
            db=db,
            port=port,
            minsize=minsize,
            maxsize=maxsize,
            cursorclass=aiomysql.DictCursor,
            autocommit=True
        )
        logger.info("Пул соединений MySQL успешно создан.")

    async def get_connection(self):
        """Получение соединения из пула.
        
        Возвращает объект подключения (connection) из пула.
        """
        if not self._pool:
            raise RuntimeError("Пул соединений не инициализирован.")
        return await self._pool.acquire()

    async def release_connection(self, connection):
        """Возврат соединения в пул."""
        if self._pool and connection:
            self._pool.release(connection)

    async def close(self):
        """Закрытие пула соединений."""
        if self._pool:
            self._pool.close()
            await self._pool.wait_closed()
            logger.info("Пул соединений MySQL закрыт.")

async def execute_async_query(pool, query, params=None, retries=3):
    """
    Выполнение асинхронного SQL-запроса с поддержкой пула соединений.

    Внимание:
    - Аргумент `pool` должен быть экземпляром класса ConnectionPool.
    Нельзя передавать сюда объект типа `connection` или любые другие объекты.
    Если вы получили ошибку 'Connection' object has no attribute 'get_connection',
    значит вместо пула был передан объект подключения или что-то иное.

    Параметры:
    - pool: объект класса ConnectionPool, через который получаем соединение
    - query: SQL-запрос (строка)
    - params: параметры для подстановки в запрос (по умолчанию None)
    - retries: число повторных попыток (по умолчанию 3)

    Возвращает:
    - список словарей с результатами запроса или None, если запрос не удался.
    """
    # Дополнительная защита от неправильного использования:
    if not isinstance(pool, ConnectionPool):
        raise TypeError("Параметр 'pool' должен быть экземпляром ConnectionPool.")

    connection = None
    for attempt in range(retries):
        try:
            # Получаем соединение из пула
            connection = await pool.get_connection()
            async with connection.cursor() as cursor:
                await cursor.execute(query, params)
                result = await cursor.fetchall()
                logger.info(f"Запрос выполнен успешно, получено {len(result)} записей.")
                return result
        except aiomysql.Error as e:
            logger.error(f"Ошибка при выполнении запроса: {e}")
            # Если соединение пропало, попробуем повторить
            if e.args and e.args[0] in (2013, 2006):
                logger.info("Повторное подключение...")
                await asyncio.sleep(2 ** attempt)  # Экспоненциальная задержка
                continue
        except Exception as e:
            logger.exception(f"Неизвестная ошибка при выполнении запроса: {e}. Попытка {attempt + 1} из {retries}.")
            await asyncio.sleep(2 ** attempt)  # Задержка перед повтором
            continue
        finally:
            # Возврат соединения в пул
            if connection:
                await pool.release_connection(connection)

    logger.critical(f"Не удалось выполнить запрос после {retries} попыток. Завершение программы.")
    restart_program()  # Если все попытки исчерпаны, перезапускаем приложение

def restart_program():
    """Перезапуск программы."""
    logger.info("Перезапуск программы из-за критической ошибки.")
    os.execv(sys.executable, ['python'] + sys.argv)