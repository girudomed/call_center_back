import logging
from db_connection import create_connection, execute_query, close_connection

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger()

def test_db_connection():
    # Создание подключения
    connection = create_connection()
    
    # Проверка успешного подключения
    if connection:
        logger.info("Подключение успешно!")
        
        try:
            # Выполнение тестового запроса
            query = "SELECT COUNT(*) AS count FROM call_history;"  # Используем таблицу call_history
            result = execute_query(connection, query)
            
            if result:
                logger.info(f"Тестовый запрос выполнен успешно: {result}")
            else:
                logger.error("Ошибка при выполнении тестового запроса.")
        except Exception as e:
            logger.exception(f"Произошла ошибка при выполнении тестового запроса: {e}")
        finally:
            # Закрытие подключения
            close_connection(connection)
    else:
        logger.error("Не удалось подключиться к базе данных.")

if __name__ == "__main__":
    test_db_connection()
