#db_setup.py
###Этот модуль работает с чек-листами. Но тут настройка БД идет, конфигурация
#Метод за чек-листы async def get_checklists_and_criteria
### weight_criteria удалили отсюда как сам параметр, к нему не обращаемся

import logging
from async_db_connection import execute_async_query

logger = logging.getLogger()

async def create_tables(pool):
    """Создание необходимых таблиц, если они не существуют."""
    logger.info("Создание необходимых таблиц, если они не существуют...")
    queries = [
        """CREATE TABLE IF NOT EXISTS call_history (
            history_id INT AUTO_INCREMENT PRIMARY KEY,
            called_info VARCHAR(255),
            caller_info VARCHAR(255),
            talk_duration INT,
            transcript TEXT,
            context_start_time DATETIME,
            created_at DATETIME
        )""",
        """CREATE TABLE IF NOT EXISTS call_scores (
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
        )""",
        """CREATE TABLE IF NOT EXISTS check_list (
            Number_check_list INT AUTO_INCREMENT PRIMARY KEY,
            Check_list_categories VARCHAR(255) NOT NULL,
            description TEXT NOT NULL,
            criteria_check_list TEXT NOT NULL,
            type_criteria VARCHAR(255),
            criterion_category VARCHAR(255)
        )"""
    ]

    for query in queries:
        try:
            await execute_async_query(pool, query)
        except Exception as e:
            logger.error(f"Ошибка при выполнении запроса на создание таблиц: {e}")
            raise  # Прекращаем выполнение, если запрос не удался

    logger.info("Все таблицы успешно созданы или уже существуют.")

async def get_checklists_and_criteria(pool):
    """Получение чек-листов и критериев из базы данных."""
    logger.info("Получение чек-листов и критериев из базы данных...")
    query = """
    SELECT Number_check_list, Check_list_categories, description, criteria_check_list, 
           type_criteria, criterion_category, scoring_method, fatal_error, max_score
    FROM check_list
    """
    try:
        checklists = await execute_async_query(pool, query)
        return checklists if checklists else []
    except Exception as e:
        logger.error(f"Ошибка при получении чек-листов: {e}")
        return []